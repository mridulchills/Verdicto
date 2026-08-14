"""
Fit the scheduler's convergence threshold on the DEV split. Never on test.

Why this exists
---------------
The evaluator's confidence is a weighted sum of post-retrieval QPP signals. Those signals
are collection-specific and none of them saturates at 1.0 in practice: on this corpus
channel agreement medians ~0.45 and score dispersion tops out ~0.42. A threshold picked a
priori (0.85 was the first guess) is therefore unreachable by construction — every query
would iterate to the cap and none would ever converge, which is exactly the failure the
earlier 0.80-cap coverage bug produced.

So the threshold has to be an OPERATING POINT read off the dev distribution, and it has
to be reported as one.

Method:
  1. Rewrite dev judgment-spans into natural-language questions with the pipeline's own
     model, so the calibration set matches the style of the natural test regime. These are
     LM-generated and used only to fit a threshold — the 30 test questions are authored
     separately by hand.
  2. Run retriever -> weighter -> evaluator on each (no debate: it costs 7 LM calls a
     query and only affects debate_consensus, which is projected to its best case).
  3. Report the confidence distribution and what each candidate threshold would do.

Usage (from Backend/):
    python -m scripts.eval.fit_confidence_threshold --n 40
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
from pathlib import Path

from app.agents.evaluator import SIGNAL_WEIGHTS, EvaluatorAgent
from app.agents.precedent_weighter import PrecedentWeighterAgent
from app.agents.retriever import RetrieverAgent
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.faiss_index import get_faiss_index
from scripts.lib.report import Report

REWRITE_PROMPT = """You are a litigation lawyer searching a database of Supreme Court of
India judgments. Below is a passage from a judgment. Write the ONE question you would type
into the search box to find this precedent, as a practising lawyer would phrase it.

Rules:
- 20 to 35 words, one sentence, ending in a question mark.
- Plain professional English. Do NOT copy distinctive phrases from the passage.
- Ask about the legal principle, not about the specific parties.
- Output ONLY the question, nothing else.

Passage:
{passage}

Question:"""


async def _rewrite(text: str) -> str | None:
    from app.core.gemini_client import get_gemini_client
    try:
        out = await get_gemini_client().generate_text(
            REWRITE_PROMPT.format(passage=text[:1200]), temperature=0.3)
    except Exception:
        return None
    q = " ".join((out or "").split())
    # The model occasionally prefixes "Question:" or wraps in quotes.
    for prefix in ("Question:", "question:"):
        if q.startswith(prefix):
            q = q[len(prefix):].strip()
    q = q.strip('"').strip()
    return q if 8 <= len(q.split()) <= 60 else None


async def _signals(db, text: str) -> dict:
    plan = {"original_query": text, "reformulated_queries": [], "extracted_issues": [],
            "legal_domain": "general", "query_id": "fit"}
    r = await RetrieverAgent(db_session=db).execute({**plan, "filters": {}})
    w = await PrecedentWeighterAgent(db_session=db).execute(
        {**plan, "candidates": r.get("candidates", [])})
    return await EvaluatorAgent().execute({
        "query_id": "fit", "ranked_cases": w.get("ranked_cases", []),
        "extracted_issues": [], "debate_result": {},
        "candidates": r.get("candidates", [])})


def _project(signals: dict) -> float:
    """Confidence assuming the two LM-side signals come out perfect.

    Upper bound: it is what the retrieval side alone permits. A threshold above the top
    of THIS distribution can never be met however good the planner and debate are.
    """
    s = dict(signals)
    s["issue_coverage"] = 1.0
    s["debate_consensus"] = 1.0
    av = {k: v for k, v in s.items() if v is not None}
    tw = sum(SIGNAL_WEIGHTS[k] for k in av)
    return sum(SIGNAL_WEIGHTS[k] * v for k, v in av.items()) / tw if tw else 0.0


async def run(args: argparse.Namespace) -> None:
    data = Path(args.data_dir)
    settings = get_settings()
    idx = get_faiss_index()
    if not idx.is_loaded:
        settings.faiss_index_path = str((data / "index" / "cases.index").resolve())
        settings.faiss_mapping_path = str((data / "index" / "cases_mapping.json").resolve())
        idx.load()

    out_path = data / "eval" / "queries_natural_dev.json"
    if args.reuse_queries and out_path.exists():
        natural = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"[info] reusing {len(natural)} dev queries from {out_path.name}")
    else:
        src = json.loads((data / "eval" / args.queries).read_text(encoding="utf-8"))
        if isinstance(src, dict):
            src = src.get("queries", [])
        dev = [q for q in src if q.get("split") == "dev"][: args.n]
        print(f"[info] rewriting {len(dev)} dev queries with {settings.ollama_model}")

        natural = []
        for i, q in enumerate(dev, 1):
            nq = await _rewrite(q["text"])
            if nq:
                natural.append({"qid": q["qid"], "text": nq, "year": q.get("year"),
                                "split": "dev", "style": "natural"})
            if i % 10 == 0:
                print(f"    {i}/{len(dev)} ({len(natural)} usable)")

        out_path.write_text(json.dumps(natural, indent=1, ensure_ascii=False),
                            encoding="utf-8")
        print(f"[info] wrote {len(natural)} -> {out_path}")

    rows = []
    async with async_session_factory() as db:
        for q in natural:
            rows.append(await _signals(db, q["text"]))

    # ── Write the calibration the evaluator will apply ────────────────────────
    # QPP predictors are collection-specific and none of these saturates: on this corpus
    # score_dispersion tops out near 0.42, so an uncalibrated confidence can never
    # approach 1.0 and any high threshold is unreachable by construction. Min-max
    # calibrating each retrieval-side signal against its dev p05-p95 range puts
    # confidence back on a usable [0,1] scale and makes the threshold mean "this fraction
    # of the quality this system can actually achieve on this collection".
    #
    # Fitted on DEV only. issue_coverage and debate_consensus are excluded: they are
    # already true proportions on a natural [0,1] scale and stretching them would be
    # meaningless.
    calibration = {}
    for key in ("channel_agreement", "ranking_decisiveness"):
        vals = sorted(r["signals"][key] for r in rows if r["signals"][key] is not None)
        if len(vals) >= 10:
            # 21-point quantile grid; the evaluator interpolates a percentile rank.
            grid = [round(vals[min(len(vals) - 1, int(round(q / 100 * (len(vals) - 1))))], 6)
                    for q in range(0, 101, 5)]
            calibration[key] = {"quantiles": grid,
                                "min": round(vals[0], 4), "max": round(vals[-1], 4)}
    cal_path = data / "eval" / "qpp_calibration.json"
    cal_path.write_text(json.dumps({
        "fitted_on": "dev", "n": len(rows), "queries": out_path.name,
        "method": "percentile-rank against the dev empirical CDF",
        "note": "min-max clipping was abandoned: it piled mass at exactly 1.0 and made "
                "convergence an arithmetic coincidence with a subset sum of the weights",
        "signals": calibration,
    }, indent=1), encoding="utf-8")
    print(f"[info] calibration -> {cal_path}")

    def _calibrated(signals: dict) -> float:
        s = dict(signals)
        s["issue_coverage"] = 1.0
        s["debate_consensus"] = 1.0
        import bisect as _bi
        for key, c in calibration.items():
            if s.get(key) is None:
                continue
            grid = c["quantiles"]
            v = s[key]
            if v <= grid[0]:
                s[key] = 0.0
            elif v >= grid[-1]:
                s[key] = 1.0
            else:
                i = _bi.bisect_left(grid, v)
                lo_, hi_ = grid[i - 1], grid[i]
                frac = 0.0 if hi_ == lo_ else (v - lo_) / (hi_ - lo_)
                s[key] = (i - 1 + frac) / (len(grid) - 1)
        av = {k: v for k, v in s.items() if v is not None}
        tw = sum(SIGNAL_WEIGHTS[k] for k in av)
        return sum(SIGNAL_WEIGHTS[k] * v for k, v in av.items()) / tw if tw else 0.0

    proj = sorted(_project(r["signals"]) for r in rows)
    cal = sorted(_calibrated(r["signals"]) for r in rows)
    raw = sorted(r["confidence"] for r in rows)

    rep = Report("fit_confidence_threshold", data, args)
    rep.section("Calibration set")
    rep.stat("dev_queries_rewritten", len(natural))
    rep.stat("mean_words", round(st.mean(len(q["text"].split()) for q in natural), 1))
    rep.note("LM-generated from dev judgment spans, used ONLY to fit the threshold. The "
             "30 natural TEST questions are authored separately and are not derived from "
             "this process.")

    rep.section("Signal distribution on dev (retrieval side)")
    dist_rows = []
    for key in ("channel_agreement", "ranking_decisiveness"):
        vals = sorted(r["signals"][key] for r in rows if r["signals"][key] is not None)
        if vals:
            dist_rows.append([key, SIGNAL_WEIGHTS[key], round(vals[0], 3),
                              round(st.median(vals), 3),
                              round(vals[int(0.9 * (len(vals) - 1))], 3),
                              round(vals[-1], 3)])
    rep.table("Per-signal", ["signal", "weight", "min", "median", "p90", "max"], dist_rows)

    rep.section("Confidence distribution")
    rep.stat("projected_median", round(st.median(proj), 4))
    rep.stat("projected_p75", round(proj[int(0.75 * (len(proj) - 1))], 4))
    rep.stat("projected_p90", round(proj[int(0.90 * (len(proj) - 1))], 4))
    rep.stat("projected_max", round(proj[-1], 4))
    rep.stat("retrieval_only_median", round(st.median(raw), 4))
    rep.note("'Projected' assumes issue_coverage and debate_consensus both come out 1.0, "
             "so it is the ceiling the retrieval side allows. A threshold above "
             f"{proj[-1]:.3f} is unreachable on this collection no matter how well the "
             "planner and debate perform.")

    rep.stat("calibrated_median", round(st.median(cal), 4))
    rep.stat("calibrated_p90", round(cal[int(0.90 * (len(cal) - 1))], 4))
    rep.stat("calibrated_max", round(cal[-1], 4))

    th_rows = []
    for th in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        raw_pass = sum(1 for p in proj if p >= th)
        cal_pass = sum(1 for p in cal if p >= th)
        th_rows.append([th, f"{raw_pass}/{len(proj)}", f"{100*raw_pass/len(proj):.0f}%",
                        f"{cal_pass}/{len(cal)}", f"{100*cal_pass/len(cal):.0f}%"])
    rep.table("Candidate operating points",
              ["threshold", "raw: converge", "raw %", "calibrated: converge", "calibrated %"],
              th_rows)
    rep.note("Pick a threshold where a substantial minority iterates: too low and the "
             "scheduler never engages, too high and nothing ever converges and the loop "
             "is indistinguishable from a fixed iteration count.")
    subset_sums = set()
    weights = list(SIGNAL_WEIGHTS.values())
    for mask in range(1, 1 << len(weights)):
        subset_sums.add(round(sum(w for i, w in enumerate(weights) if mask >> i & 1), 4))
    rep.stat("weight_subset_sums", ", ".join(f"{v:.2f}" for v in sorted(subset_sums)))
    rep.note("DO NOT set the threshold at any of those subset sums. When a threshold "
             "coincides with one, a query whose other signals all saturate lands on it "
             "EXACTLY and counts as converged for arithmetic reasons. That is what "
             "happened at 0.85 = 0.30 + 0.25 + 0.20 + 0.10 in the first calibrated run: "
             "10 of 15 convergences sat on precisely 0.8500.")
    rep.save()

    print(f"\nprojected confidence: median={st.median(proj):.3f} "
          f"p75={proj[int(0.75*(len(proj)-1))]:.3f} max={proj[-1]:.3f}")
    for row in th_rows:
        print(f"  threshold {row[0]}: {row[1]} converge, {row[3]} iterate")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit the convergence threshold on dev")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--queries", type=str, default="queries_short.json")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--reuse-queries", action="store_true",
                    help="reuse queries_natural_dev.json instead of re-generating it")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
