"""
Build a persistent BM25 index over the corpus — the replacement for `ts_rank`.

WHY
The deployed lexical channel is PostgreSQL `ts_rank` over at most 8 keywords. On the
2016-2024 corpus that scores P@1 = 2.95 against BM25's 11.18 on *identical text*
(title + facts + issues). The gap is the ranking function plus the keyword cap, not
the data. Replacing it is the single largest available improvement to the system.

WHY bm25s RATHER THAN rank_bm25
rank_bm25 holds the tokenised corpus as Python lists of strings — for 7k judgments
that is several GB, which pushed the evaluation process into swap and stalled it.
bm25s stores the index as scipy sparse matrices, saves and loads from disk, and
scores roughly two orders of magnitude faster. It also makes the lexical channel
deployable rather than a research-only artefact.

Text indexed is exactly what the Postgres tsvector covers (title + facts + issues),
so `bm25s` vs `tsrank` is a like-for-like comparison of ranking functions.

Usage (from Backend/):
    python -m scripts.ingest.build_bm25_index --data-dir ../data
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from scripts.eval.build_query_sets import clean_ocr
from scripts.lib.report import Report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

K1 = 1.2
B = 0.75


async def run(args: argparse.Namespace) -> None:
    import bm25s
    import Stemmer
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    data = Path(args.data_dir)
    out_dir = Path(args.out_dir) if args.out_dir else data / "index" / "bm25"
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url

    engine = create_async_engine(db_url)
    logger.info("loading corpus text ...")
    async with engine.connect() as conn:
        rows = (await conn.execute(sa_text(
            "SELECT case_id, coalesce(title,'') || ' ' || coalesce(facts_text,'') "
            "|| ' ' || coalesce(issues_text,'') FROM cases ORDER BY case_id"
        ))).fetchall()
    await engine.dispose()

    ids = [r[0] for r in rows]
    corpus = [clean_ocr(r[1] or "") for r in rows]
    logger.info(f"{len(ids)} documents")

    t0 = time.monotonic()
    stemmer = Stemmer.Stemmer("english")
    tokens = bm25s.tokenize(corpus, stopwords="en", stemmer=stemmer, show_progress=False)
    retriever = bm25s.BM25(k1=K1, b=B)
    retriever.index(tokens, show_progress=False)
    retriever.save(str(out_dir), corpus=None)
    (out_dir / "case_ids.json").write_text(json.dumps(ids), encoding="utf-8")
    elapsed = time.monotonic() - t0
    logger.info(f"indexed in {elapsed:.1f}s -> {out_dir}")

    rep = Report("build_bm25_index", data, args)
    rep.section("BM25 index")
    rep.stat("documents", len(ids))
    rep.stat("k1", K1)
    rep.stat("b", B)
    rep.stat("stemmer", "english (PyStemmer)")
    rep.stat("stopwords", "en")
    rep.stat("text_indexed", "title + facts_text + issues_text (matches the tsvector)")
    rep.stat("build_seconds", round(elapsed, 1))
    rep.stat("index_dir", str(out_dir))
    rep.note("Report k1=1.2, b=0.75 in the paper. Text is OCR-cleaned before indexing, "
             "which the Postgres tsvector is not — that difference is part of what the "
             "bm25s vs tsrank comparison measures.")
    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a persistent BM25 index")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--out-dir", type=str, default=None)
    ap.add_argument("--database-url", type=str, default=None)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
