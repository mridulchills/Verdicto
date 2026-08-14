"""
Build the full-text BM25 index at several (k1, b) settings so the baseline can be tuned.

WHY THIS MATTERS FOR THE PAPER
Reporting "our system beats BM25" against an UNTUNED BM25 is the most common way an IR
result fails review. b = 0.75 is a default carried over from TREC ad-hoc collections of
~500-word news articles. These judgments average 47,000 characters, and b controls how
hard BM25 penalises a document for being long. On a corpus this long-tailed the default
is not obviously right, and if a lower b beats it, that gain belongs to the BASELINE —
not to us.

Loading and OCR-cleaning 7,096 segmented judgments takes ~140 s and tokenising takes
~6 s, while indexing takes ~3 s. So the grid is built inside ONE load: the corpus is
tokenised once and re-indexed per setting, which makes a 6-point sweep about as cheap
as a single build.

Usage (from Backend/):
    python -m scripts.ingest.tune_bm25_params --data-dir ../data --grid "0.9:0.3,1.2:0.3,..."
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from scripts.ingest.build_bm25_full_index import get_titles, load_docs
from scripts.lib.report import Report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="Grid-build full-text BM25 at several (k1,b)")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--input-dir", type=str, default=None)
    ap.add_argument("--database-url", type=str, default=None)
    ap.add_argument("--grid", type=str,
                    default="0.9:0.3,0.9:0.5,1.2:0.3,1.2:0.5,1.2:0.75,1.5:0.5",
                    help="comma-separated k1:b pairs")
    args = ap.parse_args()

    import bm25s
    import Stemmer

    data = Path(args.data_dir)
    seg_dir = Path(args.input_dir) if args.input_dir else data / "processed" / "segmented"

    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url
    titles = asyncio.run(get_titles(db_url))

    t0 = time.monotonic()
    ids, texts = load_docs(seg_dir, titles)
    logger.info(f"{len(ids)} documents loaded in {time.monotonic()-t0:.0f}s")

    stemmer = Stemmer.Stemmer("english")
    logger.info("tokenising once ...")
    tokens = bm25s.tokenize(texts, stopwords="en", stemmer=stemmer, show_progress=False)

    built = []
    for pair in args.grid.split(","):
        k1_s, b_s = pair.strip().split(":")
        k1, b = float(k1_s), float(b_s)
        name = f"bm25_full_k{k1_s}_b{b_s}".replace(".", "")
        out_dir = data / "index" / name
        t = time.monotonic()
        r = bm25s.BM25(k1=k1, b=b)
        r.index(tokens, show_progress=False)
        r.save(str(out_dir), corpus=None)
        (out_dir / "owner.json").write_text(json.dumps(ids), encoding="utf-8")
        (out_dir / "case_ids.json").write_text(json.dumps(ids), encoding="utf-8")
        logger.info(f"{name}: k1={k1} b={b} built in {time.monotonic()-t:.1f}s")
        built.append((name, k1, b))

    rep = Report("tune_bm25_params", data, args)
    rep.section("BM25 parameter grid (full-text, document level)")
    rep.stat("documents", len(ids))
    rep.stat("settings_built", len(built))
    rep.table("Indexes", ["index", "k1", "b"], [[n, k, b] for n, k, b in built])
    rep.note("Evaluate each on the DEV split only. The winning setting becomes the "
             "reported BM25 baseline — tuning the baseline is required for the "
             "comparison to be honest, not optional.")
    rep.save()


if __name__ == "__main__":
    main()
