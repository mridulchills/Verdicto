"""
Mine query_records.agent_trace for the agent-level numbers (Q27, Q28, Q31, Q33, Q36, Q37).

The pipeline already records everything needed; nothing has ever read it back. One
run of this script over an existing database produces:

  Q27/Q28  iteration distribution, mean/max, fraction hitting the k_max cap
  Q36      end-to-end median and P95 latency, plus a per-agent breakdown
  Q31      how often debate changed the top-ranked precedent, WITH before/after examples
  Q33      Query Planner JSON parse-failure rate (sentinel confidence == 0.3)
  Q37      token usage, if the scheduler patch from IMPLEMENTATION_PLAN.md Step 8 is applied

Usage (from Backend/):
    python -m scripts.eval.trace_stats --data-dir ../data
    python -m scripts.eval.trace_stats --data-dir ../data --database-url postgresql+asyncpg://...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.lib.report import Report

AGENTS = ["query_planner", "retriever", "precedent_weighting", "debate", "evaluator", "scheduler"]


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))]


async def run(args: argparse.Namespace) -> None:
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    data = Path(args.data_dir)
    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        rows = (await conn.execute(sa_text("""
            SELECT id, query_text, status, processing_time_ms, agent_trace, created_at
            FROM query_records ORDER BY created_at
        """))).fetchall()
        status_counts = (await conn.execute(sa_text(
            "SELECT status, count(*) FROM query_records GROUP BY status"))).fetchall()
    await engine.dispose()

    rep = Report("trace_stats", data, args)
    rep.section("Query records")
    rep.stat("total_query_records", len(rows))
    rep.table("By status", ["status", "count"], [[r[0], r[1]] for r in status_counts])

    if not rows:
        rep.note("No query records. Run some queries through the API first — "
                 "test_scores.py submits one end to end.")
        rep.save()
        return

    iterations: list[int] = []
    confidences: list[float] = []
    totals: list[float] = []
    per_agent: dict[str, list[float]] = {a: [] for a in AGENTS}
    planner_failures = 0
    complete = 0
    debate_total = 0
    debate_changed = 0
    examples: list[dict[str, Any]] = []
    token_usage: list[dict[str, int]] = []
    debate_rounds_missing = 0

    for _id, qtext, status, ptime, trace_s, _created in rows:
        if status != "complete" or not trace_s:
            continue
        complete += 1
        try:
            tr = json.loads(trace_s)
        except Exception:
            continue

        if ptime:
            totals.append(float(ptime))
        for a in AGENTS:
            lat = (tr.get(a) or {}).get("latency_ms")
            if isinstance(lat, (int, float)) and lat > 0:
                per_agent[a].append(float(lat))

        sched = (tr.get("scheduler") or {}).get("details") or {}
        if "iterations" in sched:
            try:
                iterations.append(int(sched["iterations"]))
            except Exception:
                pass
        if "final_confidence" in sched:
            try:
                confidences.append(float(sched["final_confidence"]))
            except Exception:
                pass
        if isinstance(sched.get("token_usage"), dict):
            token_usage.append(sched["token_usage"])

        # Q33 — the planner's degradation path sets confidence to exactly 0.3
        pc = ((tr.get("query_planner") or {}).get("details") or {}).get("confidence")
        try:
            if pc is not None and abs(float(pc) - 0.3) < 1e-9:
                planner_failures += 1
        except Exception:
            pass

        # Q31 — did debate change the top precedent?
        det = (tr.get("debate") or {}).get("details") or {}
        ranking = det.get("final_ranking") or []
        rounds = det.get("debate_rounds") or []
        if ranking and rounds:
            entries = (rounds[0] or {}).get("entries") or []
            pre = [e.get("case_id") for e in entries if e.get("case_id")]
            if pre:
                debate_total += 1
                if ranking[0] != pre[0]:
                    debate_changed += 1
                    emap = {e.get("case_id"): e for e in entries}
                    examples.append({
                        "query": (qtext or "")[:300],
                        "was_top": pre[0],
                        "now_top": ranking[0],
                        "promoted_advocate_argument":
                            ((emap.get(ranking[0]) or {}).get("advocate") or {}).get("relevance_argument", "")[:600],
                        "demoted_counterargument":
                            ((emap.get(pre[0]) or {}).get("opposing") or {}).get("counterargument", "")[:600],
                        "consensus_rationale": det.get("consensus_rationale", "")[:600],
                    })
        elif ranking:
            debate_rounds_missing += 1

    rep.stat("complete_records_with_trace", complete)

    # ── Q27 / Q28 ─────────────────────────────────────────────────────────
    if iterations:
        dist = Counter(iterations)
        rep.section("Scheduler iterations (Q27, Q28)")
        rep.stat("mean_iterations", round(st.mean(iterations), 3))
        rep.stat("max_iterations", max(iterations))
        rep.stat("fraction_hitting_cap", round(dist.get(3, 0) / len(iterations), 4))
        rep.table("Iteration distribution", ["iterations", "queries", "share"],
                  [[k, dist[k], f"{100*dist[k]/len(iterations):.1f}%"] for k in sorted(dist)])
        if confidences:
            rep.stat("mean_final_confidence", round(st.mean(confidences), 4))
        if dist.get(2, 0) == 0 and len(dist) > 1:
            rep.note("BIMODAL WITH AN EMPTY MIDDLE — exactly the prediction from Q23/Q58. "
                     "Refinement iterations are byte-identical to the first, so confidence "
                     "cannot change between passes: a query either stops at 1 or runs to the "
                     "cap. This is a reportable negative result about naive iteration.")

    # ── Q36 ───────────────────────────────────────────────────────────────
    if totals:
        rep.section("Latency (Q36) — record the hardware from this report's header")
        rep.stat("n_measured", len(totals))
        rep.stat("median_total_ms", round(_pct(totals, 0.50), 1))
        rep.stat("p95_total_ms", round(_pct(totals, 0.95), 1))
        rep.stat("max_total_ms", round(max(totals), 1))
        rep.table("Per-agent latency (ms)",
                  ["agent", "n", "median", "p95", "max"],
                  [[a, len(v), round(_pct(v, 0.5), 1), round(_pct(v, 0.95), 1), round(max(v), 1)]
                   for a, v in per_agent.items() if v])
        rep.note("The PRD target of P95 < 8 s and NFR-02's 60 s are almost certainly missed — "
                 "debate is 7 sequential LLM calls. Revise the NFR and report the real "
                 "distribution as a considered latency/quality trade-off.")
        rep.note("Debate calls are deliberately SEQUENTIAL because Ollama on a single GPU "
                 "queues concurrent requests anyway (debate.py:8-13). Say so, or a reader "
                 "will assume a parallelism that was consciously avoided.")

    # ── Q31 ───────────────────────────────────────────────────────────────
    rep.section("Debate impact (Q31)")
    rep.stat("queries_with_usable_debate_trace", debate_total)
    rep.stat("debate_changed_top_precedent", debate_changed)
    rep.stat("debate_change_rate_pct",
             round(100 * debate_changed / max(debate_total, 1), 2))
    if debate_rounds_missing:
        rep.stat("traces_with_ranking_but_no_rounds", debate_rounds_missing)
    rep.note("Debate runs on iteration 1 only and sees only the top 3, so it can never "
             "promote a case ranked 4th or lower. Quote this rate against the 3! = 6 "
             "reachable permutations, not against the full result list.")
    if examples:
        ex_path = data / "reports" / "debate_examples.json"
        ex_path.parent.mkdir(parents=True, exist_ok=True)
        ex_path.write_text(json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")
        rep.stat("debate_examples_file", str(ex_path))
        rep.table("Reorderings (pick one to narrate in the paper)",
                  ["was_top", "now_top", "query"],
                  [[e["was_top"], e["now_top"], e["query"][:70]] for e in examples[:10]])
    elif debate_total:
        rep.note("Debate never changed the top precedent. With an 8B local model this is a "
                 "plausible and REPORTABLE negative result — state the model and its size.")

    # ── Q33 ───────────────────────────────────────────────────────────────
    rep.section("LLM output reliability (Q33)")
    rep.stat("planner_json_parse_failures", planner_failures)
    rep.stat("planner_failure_rate_pct", round(100 * planner_failures / max(complete, 1), 2))
    rep.note("Detected via the sentinel: the planner's degradation path returns exactly "
             "confidence=0.3. Debate-side failures are not in the trace — grep the server log "
             "for advocate_failed / opposing_failed / synthesis_failed to complete this figure.")
    rep.note("This rate is the strongest justification for switching to an instruction-tuned "
             "model with constrained JSON output: deepseek-r1 emits <think> traces and prose "
             "around its JSON, which is why the four-stage regex recovery ladder exists.")

    # ── Q37 ───────────────────────────────────────────────────────────────
    if token_usage:
        rep.section("Token usage (Q37)")
        pt = [t.get("total_prompt_tokens", 0) for t in token_usage]
        ct = [t.get("total_completion_tokens", 0) for t in token_usage]
        rep.stat("median_prompt_tokens", round(st.median(pt), 1))
        rep.stat("median_completion_tokens", round(st.median(ct), 1))
        rep.note("deepseek-r1 generates <think> reasoning traces that are counted, paid for "
                 "in latency, and then stripped and discarded — completion counts will look "
                 "high relative to visible output. Say so.")
    else:
        rep.note("No token_usage in any trace. Apply the two-line scheduler patch from "
                 "IMPLEMENTATION_PLAN.md Step 8, then re-run some queries.")

    rep.stat("api_calls_per_query", 0, "all inference is local — a genuine result")
    rep.stat("llm_invocations_per_query", "8 with debate, 1 without",
             "1 planner + 7 debate; iterations 2-3 add none")

    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Mine agent traces for the agent-level numbers")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--database-url", type=str, default=None)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
