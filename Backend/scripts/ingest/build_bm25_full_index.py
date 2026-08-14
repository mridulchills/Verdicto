"""
Build BM25 indexes over the FULL judgment, at document and at passage level.

WHY THIS EXISTS
The v2 lexical index (`build_bm25_index.py`) indexes `title + facts + issues`, which
is exactly what the Postgres tsvector covers — chosen so `bm25s` vs `tsrank` isolated
the ranking function. Measured on the segmented corpus, that text is only **20 % of
the document**:

    facts        4,004 chars   9.1 %
    issues       4,782 chars  10.9 %
    reasoning   20,938 chars  47.7 %   <- never indexed
    outcome     14,188 chars  32.3 %   <- never indexed

The reasoning section is where a court discusses the precedents it relies on. Under
citation-derived ground truth ("C is relevant to Q because Q cites C") that is the
single most on-topic region of the document, and the lexical channel could not see
it. The dense chunk index already embeds all four sections, so the two channels were
not even reading the same corpus.

TWO INDEXES ARE BUILT
  doc      one bag-of-words per judgment over all four sections.
           The honest, stronger BM25 *baseline* — the system must beat this, not the
           20 %-coverage version, or the comparison is rigged in our favour.

  passage  the same chunking the dense channel uses (1800 chars, 200 overlap, cap 16),
           each chunk indexed as its own BM25 document, max-pooled to case level at
           query time.

           Why this should beat doc-level BM25: BM25's `b` length normalisation
           penalises a 44k-character judgment for being long, and a single decisive
           paragraph is diluted across thousands of unrelated terms. Scoring passages
           and taking each case's best one removes both effects. This is the standard
           treatment for long-document retrieval and it is the lexical mirror of what
           chunking did for the dense channel.

Both are built from the segmented JSON (not the DB), so the text matches the dense
channel exactly and OCR cleaning is applied identically.

Usage (from Backend/):
    python -m scripts.ingest.build_bm25_full_index --data-dir ../data --mode doc
    python -m scripts.ingest.build_bm25_full_index --data-dir ../data --mode passage
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import time
from pathlib import Path

from scripts.eval.build_query_sets import clean_ocr
from scripts.ingest.build_chunk_embeddings import chunk_text
from scripts.lib.report import Report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

K1 = 1.2
B = 0.75

# Passage geometry is deliberately identical to build_chunk_embeddings.py, so the
# lexical and dense channels segment the corpus the same way and `bm25_chunk` vs
# `dense_chunk` is a clean comparison of scoring functions on identical passages.
CHUNK_CHARS = 1800
OVERLAP = 200
MAX_CHUNKS = 16

SECTIONS = ("facts", "issues", "reasoning", "outcome")


def load_docs(seg_dir: Path, titles: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (case_ids, full_text) from the segmented JSON, OCR-cleaned."""
    ids: list[str] = []
    texts: list[str] = []
    files = sorted(seg_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No segmented JSON in {seg_dir}")
    for i, f in enumerate(files, 1):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw = " ".join((d.get(k) or "") for k in SECTIONS)
        body = clean_ocr(raw)
        if len(body) < 50:
            continue
        # Title is prepended for parity with the v2 index, which included it.
        t = titles.get(f.stem, "")
        ids.append(f.stem)
        texts.append((t + ". " + body) if t else body)
        if i % 2000 == 0:
            logger.info(f"loaded {i}/{len(files)}")
    return ids, texts


async def get_titles(db_url: str) -> dict[str, str]:
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        rows = (await conn.execute(sa_text(
            "SELECT case_id, coalesce(title,'') FROM cases"))).fetchall()
    await engine.dispose()
    return {r[0]: r[1] for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser(description="BM25 over full judgments, doc or passage level")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--mode", type=str, default="doc", choices=["doc", "passage"])
    ap.add_argument("--input-dir", type=str, default=None)
    ap.add_argument("--out-dir", type=str, default=None)
    ap.add_argument("--database-url", type=str, default=None)
    args = ap.parse_args()

    import asyncio

    import bm25s
    import Stemmer

    data = Path(args.data_dir)
    seg_dir = Path(args.input_dir) if args.input_dir else data / "processed" / "segmented"
    out_dir = (Path(args.out_dir) if args.out_dir
               else data / "index" / ("bm25_full" if args.mode == "doc" else "bm25_chunk"))
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url
    titles = asyncio.run(get_titles(db_url))

    t0 = time.monotonic()
    ids, texts = load_docs(seg_dir, titles)
    logger.info(f"{len(ids)} documents, mean {st.mean([len(t) for t in texts]):.0f} chars")

    # ── build the unit list: one entry per document, or one per passage ────
    per_doc: list[int] = []
    if args.mode == "passage":
        units: list[str] = []
        owner: list[str] = []
        for cid, txt in zip(ids, texts):
            cs = chunk_text(txt, CHUNK_CHARS, OVERLAP, MAX_CHUNKS)
            if not cs:
                cs = [txt]
            per_doc.append(len(cs))
            for c in cs:
                units.append(c)
                owner.append(cid)
        logger.info(f"{len(units)} passages ({st.mean(per_doc):.1f} per doc)")
    else:
        units = texts
        owner = ids

    stemmer = Stemmer.Stemmer("english")
    logger.info("tokenising ...")
    tokens = bm25s.tokenize(units, stopwords="en", stemmer=stemmer, show_progress=False)
    logger.info("indexing ...")
    retriever = bm25s.BM25(k1=K1, b=B)
    retriever.index(tokens, show_progress=False)
    retriever.save(str(out_dir), corpus=None)
    # `owner` maps unit-index -> case_id. For doc mode it is just the id list; keeping
    # the same filename in both modes lets the harness load them through one path.
    (out_dir / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
    (out_dir / "case_ids.json").write_text(json.dumps(ids), encoding="utf-8")
    elapsed = time.monotonic() - t0
    logger.info(f"built in {elapsed:.1f}s -> {out_dir}")

    rep = Report("build_bm25_full_index", data, args)
    rep.section(f"BM25 index ({args.mode} level, full judgment)")
    rep.stat("mode", args.mode)
    rep.stat("documents", len(ids))
    rep.stat("units_indexed", len(units))
    if per_doc:
        rep.stat("mean_passages_per_document", round(st.mean(per_doc), 2))
        rep.stat("median_passages_per_document", round(st.median(per_doc), 1))
    rep.stat("mean_document_chars", round(st.mean([len(t) for t in texts])))
    rep.stat("sections_indexed", "title + " + " + ".join(SECTIONS))
    rep.stat("k1", K1)
    rep.stat("b", B)
    rep.stat("build_seconds", round(elapsed, 1))
    rep.stat("index_dir", str(out_dir))
    rep.note("Contrast with build_bm25_index.py, which covers title+facts+issues only "
             "= 20 % of the document. The reasoning section (47.7 %) is where precedents "
             "are discussed, so under citation-derived qrels it is the most on-topic text "
             "in the corpus.")
    rep.save()


if __name__ == "__main__":
    main()
