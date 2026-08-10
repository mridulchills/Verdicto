"""
Generate embeddings for segmented case texts using the local SentenceTransformer.

CHANGES FROM THE ORIGINAL VERSION — both were costing hours per run:

  1. REMOVED `await asyncio.sleep(0.5)` per document. That was rate-limiting left
     over from the Gemini API era. There is no API to rate-limit; the model is local.
     On 20,000 documents it was 2.8 hours of doing nothing.

  2. BATCHED encoding. The original called encode() once per document.
     SentenceTransformer.encode() accepts a list and batches on the GPU, which is
     typically 10-50x faster.

  3. Added file-based reporting so the truncation loss (Q9) and per-document
     outcomes are recorded rather than scrolling past in the console.

NOTE ON TRUNCATION (Q9): embedding_service.get_embedding() truncates to the first
1000 characters, which is about the model's 256-token limit. Each judgment is
therefore represented by roughly its first paragraph of facts. This script measures
and reports exactly how much of each document survives, so the limitation can be
stated with a number instead of an adjective.

Usage (from Backend/):
    python -m scripts.ingest.build_embeddings --input-dir ../data/processed/segmented --output-dir ../data/embeddings
    python -m scripts.ingest.build_embeddings --input-dir ../data/processed/segmented --output-dir ../data/embeddings --batch-size 256
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import time
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TRUNCATION_CHARS = 1000   # must match app/services/embedding_service.py
MIN_TEXT_CHARS = 50       # documents shorter than this are skipped


def build_text(data: dict) -> str:
    """Concatenate the four segments exactly as the original pipeline did."""
    return " ".join([
        data.get("facts", "") or "",
        data.get("issues", "") or "",
        (data.get("reasoning", "") or "")[:2000],
        data.get("outcome", "") or "",
    ]).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate case embeddings (batched, local)")
    parser.add_argument("--input-dir", type=str, default="./data/processed/segmented")
    parser.add_argument("--output-dir", type=str, default="./data/embeddings")
    parser.add_argument("--data-dir", type=str, default="../data",
                        help="Root data directory; reports go to <data-dir>/reports/")
    parser.add_argument("--batch-size", type=int, default=128,
                        help="documents encoded per batch (raise on a GPU)")
    parser.add_argument("--model", type=str, default="all-MiniLM-L6-v2")
    parser.add_argument("--force", action="store_true", help="re-embed documents already done")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_file = output_dir / ".progress"

    try:
        from scripts.lib.report import EventLog, Report
        report_enabled = True
    except Exception:
        report_enabled = False

    json_files = sorted(input_dir.glob("*.json"))
    logger.info(f"Found {len(json_files)} segmented files")
    if not json_files:
        raise SystemExit(f"No .json files in {input_dir}")

    completed: set[str] = set()
    if progress_file.exists() and not args.force:
        completed = {ln for ln in progress_file.read_text(encoding="utf-8").split("\n") if ln}
        logger.info(f"{len(completed)} already embedded (resume)")

    # ── Load and prepare ──────────────────────────────────────────────────
    todo: list[tuple[Path, str]] = []
    skipped_short = 0
    unreadable = 0
    fractions: list[float] = []
    full_lengths: list[int] = []

    for f in json_files:
        if f.name in completed and not args.force:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Unreadable {f.name}: {e}")
            unreadable += 1
            continue
        text = build_text(data)
        if len(text) < MIN_TEXT_CHARS:
            logger.warning(f"SKIP (too short): {f.name}")
            skipped_short += 1
            continue
        full_lengths.append(len(text))
        fractions.append(min(TRUNCATION_CHARS, len(text)) / len(text))
        todo.append((f, text[:TRUNCATION_CHARS]))

    logger.info(f"{len(todo)} documents to embed")
    if not todo:
        logger.info("Nothing to do.")
        return

    # ── Encode in batches ─────────────────────────────────────────────────
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading model {args.model} ...")
    model = SentenceTransformer(args.model)

    log = EventLog("build_embeddings_per_doc", args.data_dir) if report_enabled else None
    start = time.monotonic()
    done = 0

    with open(progress_file, "a", encoding="utf-8") as pf:
        for i in range(0, len(todo), args.batch_size):
            chunk = todo[i: i + args.batch_size]
            texts = [t for _, t in chunk]
            try:
                vectors = model.encode(
                    texts,
                    convert_to_numpy=True,
                    batch_size=args.batch_size,
                    show_progress_bar=False,
                )
            except Exception as e:
                logger.error(f"Batch starting at {i} failed: {e}")
                continue

            for (path, _), vec in zip(chunk, vectors):
                out_path = output_dir / path.with_suffix(".npy").name
                np.save(str(out_path), np.asarray(vec, dtype=np.float32))
                pf.write(path.name + "\n")
                done += 1
                if log:
                    log.write(case_id=path.stem, status="ok", dim=int(len(vec)))
            pf.flush()

            elapsed = time.monotonic() - start
            rate = done / max(elapsed, 1e-6)
            remaining = (len(todo) - done) / max(rate, 1e-6)
            logger.info(f"{done}/{len(todo)} embedded  |  {rate:.1f} docs/s  |  "
                        f"~{remaining/60:.1f} min remaining")

    if log:
        log.close()

    elapsed = time.monotonic() - start
    logger.info(f"Done. {done} embeddings in {elapsed/60:.1f} min ({done/max(elapsed,1e-6):.1f} docs/s)")

    if report_enabled:
        rep = Report("build_embeddings", args.data_dir, args)
        rep.section("Embedding generation")
        rep.stat("model", args.model)
        rep.stat("dimension", int(vectors.shape[1]) if len(todo) else 0)
        rep.stat("documents_embedded", done)
        rep.stat("skipped_too_short", skipped_short)
        rep.stat("unreadable", unreadable)
        rep.stat("elapsed_minutes", round(elapsed / 60, 2))
        rep.stat("docs_per_second", round(done / max(elapsed, 1e-6), 2))
        if fractions:
            rep.section("Truncation loss (Q9) — the key retrieval limitation, quantified")
            rep.stat("truncation_chars", TRUNCATION_CHARS)
            rep.stat("mean_fraction_embedded_pct", round(100 * st.mean(fractions), 3))
            rep.stat("median_fraction_embedded_pct", round(100 * st.median(fractions), 3))
            rep.stat("documents_embedded_in_full_pct",
                     round(100 * sum(1 for f in fractions if f >= 1.0) / len(fractions), 2))
            rep.stat("combined_text_chars_median", round(st.median(full_lengths), 0))
            rep.note("Each judgment is represented by approximately its first paragraph of "
                     "facts. Issues, reasoning and outcome reach the vector only for "
                     "documents whose facts section is under 1000 characters. Chunk-and-pool "
                     "is the fix and is likely the largest retrieval-quality gain available.")
        rep.save()


if __name__ == "__main__":
    main()
