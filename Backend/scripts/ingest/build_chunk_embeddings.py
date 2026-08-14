"""
Chunk-and-pool document embeddings — the fix for the 4.7 % coverage problem.

THE PROBLEM THIS SOLVES
The original pipeline embeds each judgment as ONE vector built from the first 1,000
characters of its concatenated segments. Measured on the 2016-2024 corpus, that is
4.69 % of the mean document; 100 % of documents exceed the encoder's token limit.
The dense channel was therefore matching on roughly the opening paragraph of facts.

WHAT THIS DOES INSTEAD
Splits each document into overlapping windows sized to the encoder, embeds every
window, and indexes all of them. At query time the retriever searches chunks and
max-pools to case level: a case scores as well as its single best-matching passage.
That is the standard treatment for long documents and it lets a citation buried in
the reasoning section be found.

Two other changes bundled here, both of which the evaluation showed to matter:
  * ENCODER: BAAI/bge-small-en-v1.5 instead of all-MiniLM-L6-v2. Same 384 dimensions,
    so the index shape is unchanged, but a 512-token window (vs 256) and markedly
    better retrieval quality. BGE expects an instruction prefix on QUERIES only —
    handled in the retrieval path, not here.
  * OCR CLEANING: SCR margin markers, running headers and page numbers are stripped
    before embedding. They are pure noise in the vector.

Writes to a SEPARATE index path so the original single-vector index survives for
comparison — `dense` vs `dense_chunk` is then a clean ablation.

Usage (from Backend/):
    python -m scripts.ingest.build_chunk_embeddings --data-dir ../data
    python -m scripts.ingest.build_chunk_embeddings --data-dir ../data --max-chunks 24
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import time
from pathlib import Path

import numpy as np

from scripts.eval.build_query_sets import clean_ocr
from scripts.lib.report import Report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def chunk_text(text: str, size: int, overlap: int, max_chunks: int) -> list[str]:
    """
    Split on a character window with overlap, preferring to break at sentence ends so
    a chunk does not start mid-clause. Overlap ensures a passage spanning a boundary
    is still fully present in one window.
    """
    if len(text) <= size:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    step = max(size - overlap, 1)
    while start < len(text) and len(chunks) < max_chunks:
        end = min(start + size, len(text))
        if end < len(text):
            # Prefer a sentence boundary in the last 20 % of the window.
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind("? "), window.rfind("; "))
            if cut > size * 0.8:
                end = start + cut + 1
        piece = text[start:end].strip()
        if len(piece) > 80:
            chunks.append(piece)
        start += step
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description="Build chunked document embeddings")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--input-dir", type=str, default=None)
    ap.add_argument("--out-index", type=str, default=None,
                    help="default <data>/index/cases_chunk.index")
    ap.add_argument("--model", type=str, default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--chunk-chars", type=int, default=1800,
                    help="~450 word-pieces, inside bge-small's 512-token window")
    ap.add_argument("--overlap", type=int, default=200)
    ap.add_argument("--max-chunks", type=int, default=16,
                    help="cap per document; bounds cost on very long judgments")
    ap.add_argument("--batch-size", type=int, default=64,
                    help="encoder batch; large batches hung on MPS")
    ap.add_argument("--block", type=int, default=5000,
                    help="chunks per encode() call — bounds memory, gives progress")
    ap.add_argument("--device", type=str, default=None,
                    help="mps / cpu / cuda; default lets sentence-transformers choose")
    ap.add_argument("--force", action="store_true", help="re-encode blocks already on disk")
    args = ap.parse_args()

    data = Path(args.data_dir)
    seg_dir = Path(args.input_dir) if args.input_dir else data / "processed" / "segmented"
    index_path = Path(args.out_index) if args.out_index else data / "index" / "cases_chunk.index"
    map_path = index_path.with_name(index_path.stem + "_mapping.json")
    index_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(seg_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No segmented JSON in {seg_dir}")
    logger.info(f"{len(files)} documents to chunk")

    # ── Chunk ─────────────────────────────────────────────────────────────
    texts: list[str] = []
    owner: list[str] = []          # chunk index -> case_id
    per_doc: list[int] = []
    doc_chars: list[int] = []
    covered: list[float] = []
    t0 = time.monotonic()

    for i, f in enumerate(files, 1):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw = " ".join((d.get(k) or "") for k in ("facts", "issues", "reasoning", "outcome"))
        body = clean_ocr(raw)
        if len(body) < 50:
            continue
        cs = chunk_text(body, args.chunk_chars, args.overlap, args.max_chunks)
        if not cs:
            continue
        doc_chars.append(len(body))
        per_doc.append(len(cs))
        # How much of the document the chunks actually span (accounting for the cap).
        span = min(len(body), args.chunk_chars + (len(cs) - 1) * (args.chunk_chars - args.overlap))
        covered.append(span / len(body))
        for c in cs:
            texts.append(c)
            owner.append(f.stem)
        if i % 1000 == 0:
            logger.info(f"chunked {i}/{len(files)} docs -> {len(texts)} chunks")

    logger.info(f"{len(texts)} chunks from {len(per_doc)} documents "
                f"({st.mean(per_doc):.1f} per doc)")

    # ── Embed ─────────────────────────────────────────────────────────────
    from sentence_transformers import SentenceTransformer
    logger.info(f"loading {args.model}")
    model = SentenceTransformer(args.model, device=args.device) if args.device else SentenceTransformer(args.model)

    # Encode in explicit blocks rather than one giant call. A single 200k-item encode
    # on MPS hung with no output; blocks bound peak memory, give progress, and let a
    # failure be attributed to a specific range.
    # Each block is written to disk as soon as it is encoded. Two reasons, both learned
    # the hard way:
    #   * RESUMABILITY. A crash or stall no longer discards the whole encoding pass;
    #     a re-run skips every block already on disk.
    #   * The faiss step must NOT run in this process. torch and faiss both link libomp,
    #     and calling faiss after torch is loaded deadlocks on macOS (observed: 0 % CPU
    #     forever at index.add). Indexing therefore happens in a separate, torch-free
    #     process — see build_faiss_from_parts.py.
    block = args.block
    parts_dir = index_path.parent / (index_path.stem + "_parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    (parts_dir / "owner.json").write_text(json.dumps(owner), encoding="utf-8")

    t_enc = time.monotonic()
    for s in range(0, len(texts), block):
        part_path = parts_dir / f"part_{s:08d}.npy"
        if part_path.exists() and not args.force:
            continue
        v = model.encode(
            texts[s: s + block],
            batch_size=args.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,   # BGE expects cosine over normalised vectors
            show_progress_bar=False,
        ).astype(np.float32)
        np.save(str(part_path), v)
        done = min(s + block, len(texts))
        el = time.monotonic() - t_enc
        rate = done / max(el, 1e-6)
        logger.info(f"embedded {done}/{len(texts)} | {rate:.0f} chunks/s | "
                    f"~{(len(texts)-done)/max(rate,1e-6)/60:.1f} min left")

    elapsed = time.monotonic() - t0
    logger.info(f"encoding complete in {elapsed/60:.1f} min -> {parts_dir}")
    logger.info(f"NEXT: python -m scripts.ingest.build_faiss_from_parts "
                f"--parts-dir {parts_dir} --out-index {index_path}")

    n_chunks = len(texts)

    rep = Report("build_chunk_embeddings", data, args)
    rep.section("Chunked document embeddings")
    rep.stat("model", args.model)
    rep.stat("chunks_encoded", n_chunks)
    rep.stat("documents", len(per_doc))
    rep.stat("parts_dir", str(parts_dir))
    rep.stat("mean_chunks_per_document", round(st.mean(per_doc), 2))
    rep.stat("median_chunks_per_document", round(st.median(per_doc), 1))
    rep.stat("chunk_chars", args.chunk_chars)
    rep.stat("overlap_chars", args.overlap)
    rep.stat("max_chunks_per_document", args.max_chunks)
    rep.stat("mean_document_coverage_pct", round(100 * st.mean(covered), 2),
             "share of each document now reachable by the dense channel")
    rep.stat("median_document_coverage_pct", round(100 * st.median(covered), 2))
    rep.stat("documents_fully_covered_pct",
             round(100 * sum(1 for c in covered if c >= 0.999) / max(len(covered), 1), 2))
    rep.stat("elapsed_minutes", round(elapsed / 60, 2))
    rep.stat("index_path", str(index_path))
    rep.note("Run build_faiss_from_parts.py next — faiss must not be called from a "
             "process that has loaded torch (libomp deadlock on macOS).")
    rep.note("Compare mean_document_coverage_pct against the 4.69 % achieved by the "
             "original single-vector pipeline (corpus_stats: mean_fraction_embedded_pct).")
    rep.save()


if __name__ == "__main__":
    main()
