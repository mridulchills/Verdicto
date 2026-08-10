"""
Near-duplicate detection over the existing FAISS vectors (Q45).

No deduplication of any kind exists in the pipeline. The only control is exact
case_id (filename) matching via ON CONFLICT DO NOTHING, which catches re-ingesting
the same file and nothing else — not the same judgment under two ids, not connected
appeals, not corrected re-issues, not cross-year duplicates.

Near-duplicates inflate every retrieval metric, and under citation-derived ground
truth a duplicate of the query case sitting in the candidate pool is an outright leak.

CAVEAT THAT MUST ACCOMPANY THE NUMBER: embeddings are 1000-character truncations
(Q9), so this detects LEAD-PARAGRAPH duplicates. It over-flags judgments with
boilerplate openings and under-flags documents that diverge only late. Sweep the
threshold and inspect pairs by hand before reporting.

Usage (from Backend/):
    python -m scripts.eval.dedup --data-dir ../data
    python -m scripts.eval.dedup --data-dir ../data --thresholds 0.90,0.95,0.98 --neighbours 10
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.lib.report import Report


def main() -> None:
    ap = argparse.ArgumentParser(description="Near-duplicate detection over FAISS vectors")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--thresholds", type=str, default="0.90,0.95,0.98")
    ap.add_argument("--neighbours", type=int, default=6, help="incl. self")
    ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--write-blocklist", action="store_true",
                    help="write duplicate case_ids to eval/duplicates.txt for exclusion")
    args = ap.parse_args()

    import faiss
    import numpy as np

    data = Path(args.data_dir)
    idx_path = data / "index" / "cases.index"
    map_path = data / "index" / "cases_mapping.json"
    if not idx_path.exists() or not map_path.exists():
        raise SystemExit(f"Missing FAISS artefacts at {data/'index'}")

    index = faiss.read_index(str(idx_path))
    mapping = {int(k): v for k, v in json.loads(map_path.read_text(encoding="utf-8")).items()}
    n = index.ntotal
    print(f"[info] {n} vectors, dim {index.d}")

    thresholds = sorted(float(t) for t in args.thresholds.split(","))
    lowest = thresholds[0]

    # Reconstruct in batches — vectors are already L2-normalised, so IP == cosine.
    pairs: dict[tuple[str, str], float] = {}
    for start in range(0, n, args.batch):
        end = min(start + args.batch, n)
        X = index.reconstruct_n(start, end - start)
        D, I = index.search(X, args.neighbours)
        for row, (drow, irow) in enumerate(zip(D, I)):
            i = start + row
            for score, j in zip(drow, irow):
                j = int(j)
                if j == i or j < 0 or float(score) < lowest:
                    continue
                a, b = mapping.get(i), mapping.get(j)
                if not a or not b:
                    continue
                key = (a, b) if a < b else (b, a)
                pairs[key] = max(pairs.get(key, 0.0), float(score))
        print(f"[info] {end}/{n} scanned, {len(pairs)} candidate pairs ...", end="\r")

    rep = Report("dedup", data, args)
    rep.section("Near-duplicate detection (Q45)")
    rep.stat("vectors", n)
    rep.stat("neighbours_per_vector", args.neighbours)

    rows = []
    for t in thresholds:
        sel = {k: v for k, v in pairs.items() if v >= t}
        docs = {d for k in sel for d in k}
        rows.append([f"{t:.2f}", len(sel), len(docs), f"{100*len(docs)/max(n,1):.2f}%"])
        rep.stat(f"pairs_at_{str(t).replace('.','_')}", len(sel))
    rep.table("Duplicate rate by cosine threshold",
              ["threshold", "pairs", "documents involved", "share of corpus"], rows)

    top = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:40]
    rep.table("Highest-similarity pairs — INSPECT THESE BY HAND before reporting",
              ["cosine", "case_a", "case_b"],
              [[f"{v:.4f}", k[0], k[1]] for k, v in top])

    rep.note("Embeddings are 1000-character truncations (Q9), so this measures "
             "LEAD-PARAGRAPH similarity, not whole-document duplication. Judgments with "
             "boilerplate openings will be over-flagged. Report the threshold alongside "
             "the rate, and say how you inspected them.")
    rep.note("For a stricter check, add character-level MinHash / SimHash over the full "
             "extracted text and report the intersection of the two methods.")

    if args.write_blocklist:
        hi = thresholds[-1]
        dup_ids = sorted({b for (a, b), v in pairs.items() if v >= hi})
        out = data / "eval" / "duplicates.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(dup_ids) + "\n", encoding="utf-8")
        rep.stat("blocklist_file", str(out))
        rep.stat("blocklist_size", len(dup_ids))
        rep.note(f"Blocklist written at threshold {hi}. Either exclude these from the "
                 "candidate pool or collapse them into equivalence classes for scoring — "
                 "and say in the paper which you did.")

    print(f"\n[done] {len(pairs)} candidate pairs above {lowest}")
    rep.save()


if __name__ == "__main__":
    main()
