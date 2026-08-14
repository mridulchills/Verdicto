"""
Score every run file with a STANDARD library and run paired bootstrap significance.

Why a library and not the in-repo evaluator (Q60): app/agents/evaluator.py computes
nDCG over the system's OWN final_score values, with the "ideal" ranking being those
same values re-sorted — so it is ~1.0 by construction and measures whether the list is
sorted, not whether it is relevant. It must never be reported as retrieval quality.
ir_measures reads TREC qrels/run files and cannot make that mistake.

Produces:
  * the main results table (nDCG@10, P@5, P@10, MRR, R@20) for every condition
  * paired bootstrap: mean difference, 95% CI, and P(A > B) against a baseline
  * per-query scores, so failure analysis (Q64) and win examples (Q65) can be built

Usage (from Backend/):
    pip install ir_measures numpy
    python -m scripts.eval.score --data-dir ../data
    python -m scripts.eval.score --data-dir ../data --baseline bm25 --primary nDCG@10
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from scripts.lib.report import Report


def paired_bootstrap(a: dict[str, float], b: dict[str, float],
                     n: int = 10000, seed: int = 42) -> tuple[float, tuple[float, float], float]:
    """
    Paired bootstrap over the per-query differences.

    Paired is essential: the conditions run on identical queries, so pairing removes
    query-difficulty variance and gives far more power on a small Q.
    Returns (mean difference, 95% CI, fraction of resamples favouring `a`).
    """
    qids = sorted(set(a) & set(b))
    if not qids:
        return 0.0, (0.0, 0.0), 0.5
    d = np.array([a[q] - b[q] for q in qids], dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    means = d[idx].mean(axis=1)
    return float(d.mean()), (float(np.percentile(means, 2.5)),
                             float(np.percentile(means, 97.5))), float((means > 0).mean())


def main() -> None:
    ap = argparse.ArgumentParser(description="Score run files and test significance")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--baseline", type=str, default="bm25",
                    help="condition every other condition is compared against")
    ap.add_argument("--primary", type=str, default="nDCG@10",
                    help="metric used for the significance tests")
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tag", type=str, default="",
                    help="query-regime suffix to score, e.g. --tag _short")
    args = ap.parse_args()

    try:
        import ir_measures
        from ir_measures import parse_measure
    except ImportError:
        raise SystemExit("pip install ir_measures")

    data = Path(args.data_dir)
    eval_dir = data / "eval"
    qrels_path = eval_dir / "qrels.txt"
    if not qrels_path.exists():
        raise SystemExit(f"No {qrels_path}. Run build_golden_set.py first.")

    qrels = list(ir_measures.read_trec_qrels(str(qrels_path)))
    # --tag selects one query regime (e.g. _short). Without it, only untagged runs are
    # scored, so regimes are never accidentally mixed into the same table.
    if args.tag:
        runs = sorted(eval_dir.glob(f"run_*{args.tag}.txt"))
    else:
        tagged = {p for t in ("_short", "_keyword", "_medium", "_long")
                  for p in eval_dir.glob(f"run_*{t}.txt")}
        runs = sorted(p for p in eval_dir.glob("run_*.txt") if p not in tagged)
    if not runs:
        raise SystemExit(f"No run_*.txt in {eval_dir}. Run run_eval.py first.")

    # Column order matches the paper's Table 1: P@1, P@5, R@20, MRR, nDCG@10
    measures = [parse_measure(m) for m in
                ["P@1", "P@5", "R@20", "RR", "nDCG@10", "P@10", "nDCG@20", "R@100"]]
    primary = parse_measure(args.primary)

    rep = Report(f"score{args.tag}", data, args)
    rep.section("Evaluation set")
    rep.stat("qrels_file", str(qrels_path))
    rep.stat("judgements", len(qrels))
    rep.stat("queries_with_judgements", len({q.query_id for q in qrels}))
    rep.stat("graded", bool({q.relevance for q in qrels} - {0, 1}))
    rep.stat("primary_metric", str(primary))
    rep.stat("bootstrap_resamples", args.resamples)

    # ── Aggregate table ───────────────────────────────────────────────────
    agg_rows = []
    per_query: dict[str, dict[str, float]] = {}
    for run_path in runs:
        cond = run_path.stem.replace("run_", "")
        if args.tag:
            cond = cond[: -len(args.tag)] if cond.endswith(args.tag) else cond
        run = list(ir_measures.read_trec_run(str(run_path)))
        if not run:
            print(f"[warn] {run_path.name} is empty, skipping")
            continue
        agg = ir_measures.calc_aggregate(measures, qrels, run)
        agg_rows.append([cond] + [f"{agg[m]:.4f}" for m in measures])
        per_query[cond] = {m.query_id: m.value
                           for m in ir_measures.iter_calc([primary], qrels, run)}
        print(f"[score] {cond:14s} " +
              "  ".join(f"{str(m)}={agg[m]:.4f}" for m in measures[:4]))

    rep.section("MAIN RESULTS TABLE — paste this into the paper")
    rep.table("Retrieval effectiveness",
              ["condition"] + [str(m) for m in measures], agg_rows)

    # ── Significance ──────────────────────────────────────────────────────
    base = args.baseline
    if base in per_query:
        rows = []
        for cond, scores in per_query.items():
            if cond == base:
                continue
            mean_d, ci, p_win = paired_bootstrap(
                scores, per_query[base], n=args.resamples, seed=args.seed)
            sig = "yes" if (ci[0] > 0 or ci[1] < 0) else "no"
            rows.append([cond, f"{mean_d:+.4f}", f"[{ci[0]:+.4f}, {ci[1]:+.4f}]",
                         f"{p_win:.3f}", sig])
        rep.section(f"Paired bootstrap vs `{base}` on {primary}")
        rep.table("Significance",
                  ["condition", f"mean Δ{primary}", "95% CI", "P(better)", "CI excludes 0"],
                  rows)
        rep.note("A CI crossing zero means the difference is not statistically detectable "
                 "at this sample size. Report it as such — an honest wide interval is "
                 "respectable; an unqualified point estimate is not.")
    else:
        rep.note(f"Baseline '{base}' has no run file; significance tests skipped.")

    # ── Per-query dump for Q64/Q65 ────────────────────────────────────────
    pq_path = eval_dir / "per_query_scores.json"
    pq_path.write_text(json.dumps(per_query, indent=2), encoding="utf-8")
    rep.stat("per_query_scores_file", str(pq_path))

    # ── Biggest hybrid-over-dense wins (Q65) ──────────────────────────────
    if "hybrid" in per_query and "dense" in per_query:
        h, d = per_query["hybrid"], per_query["dense"]
        wins = sorted(((h[q] - d[q], q) for q in h if q in d), reverse=True)
        rep.section("Largest hybrid-over-dense wins (Q65) — narrate the top 3 in the paper")
        rep.table("Top 10 wins", [f"Δ{primary}", "query_id"],
                  [[f"{delta:+.4f}", qid] for delta, qid in wins[:10]])
        rep.note("For each: print the gold cases' ranks in the dense run vs the lexical run. "
                 "The expected mechanism is a specific statutory token (a section number, an "
                 "Act name) that the lexical channel matches exactly and the dense channel "
                 "misses — because all-MiniLM-L6-v2 has no legal pretraining, and because "
                 "the document vector only covers the first ~1000 characters (Q9).")

        losses = sorted(((h[q] - d[q], q) for q in h if q in d))[:10]
        rep.table("Top 10 hybrid LOSSES (start the failure analysis here — Q64)",
                  [f"Δ{primary}", "query_id"], [[f"{dl:+.4f}", qid] for dl, qid in losses])

    rep.save()


if __name__ == "__main__":
    main()
