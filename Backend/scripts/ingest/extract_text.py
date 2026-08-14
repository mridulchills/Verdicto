"""
Extract text from PDF judgments using pdfplumber with pypdf fallback.
Handles: corrupted PDFs (skip + log), scanned PDFs (skip with warning), password-protected (skip).
Idempotent — skips already extracted files.

Usage:
    python -m scripts.ingest.extract_text --input-dir ./data/raw/pdfs --output-dir ./data/processed
"""
from __future__ import annotations
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_with_pdfplumber(pdf_path: Path) -> str | None:
    """Primary extraction using pdfplumber."""
    try:
        import pdfplumber
        text_parts: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        full_text = "\n\n".join(text_parts)
        if len(full_text.strip()) < 100:
            return None  # Likely scanned
        return full_text
    except Exception as e:
        logger.debug(f"pdfplumber failed for {pdf_path}: {e}")
        return None


def extract_with_pypdf(pdf_path: Path) -> str | None:
    """Fallback extraction using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            logger.warning(f"SKIP (password-protected): {pdf_path}")
            return None
        text_parts = [page.extract_text() or "" for page in reader.pages]
        full_text = "\n\n".join(text_parts)
        if len(full_text.strip()) < 100:
            return None
        return full_text
    except Exception as e:
        logger.debug(f"pypdf failed for {pdf_path}: {e}")
        return None


def extract_text(pdf_path: Path) -> tuple[str | None, str]:
    """
    Extract text from a PDF using pdfplumber, falling back to pypdf.
    Returns (text, method) where method records HOW the document was handled —
    needed for the corpus-construction attrition table (Q46), which previously
    only existed as console output that scrolled past.
    """
    text = extract_with_pdfplumber(pdf_path)
    if text:
        return text, "pdfplumber"
    logger.info(f"Falling back to pypdf for {pdf_path.name}")
    text = extract_with_pypdf(pdf_path)
    if text:
        return text, "pypdf_fallback"
    logger.warning(f"SKIP (scanned/corrupted): {pdf_path.name}")
    return None, "failed_scanned_or_corrupt"


def _extract_one(job: tuple[str, str]) -> tuple[str, str, str, int]:
    """
    Worker for the process pool. Returns (case_id, status, method, chars).
    Module-level and picklable so it can be dispatched to a ProcessPoolExecutor.
    """
    pdf_str, out_str = job
    pdf_path, output_path = Path(pdf_str), Path(out_str)
    try:
        text, method = extract_text(pdf_path)
    except Exception as e:  # never let one bad PDF kill the pool
        return output_path.stem, "failed", f"error:{type(e).__name__}", 0
    if text:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
        except Exception as e:
            return output_path.stem, "failed", f"write_error:{type(e).__name__}", 0
        return output_path.stem, "ok", method, len(text)
    return output_path.stem, "failed", method, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from PDF judgments")
    parser.add_argument("--input-dir", type=str, default="./data/raw/pdfs", help="Directory containing PDFs")
    parser.add_argument("--output-dir", type=str, default="./data/processed", help="Output directory for .txt files")
    parser.add_argument("--data-dir", type=str, default="../data",
                        help="Root data directory; reports are written to <data-dir>/reports/")
    parser.add_argument("--workers", type=int, default=1,
                        help="parallel worker processes. PDF extraction is CPU-bound and "
                             "embarrassingly parallel; on an N-core machine use N-1. "
                             "Measured ~0.5 s/PDF single-threaded, so a 7,000-document "
                             "corpus goes from ~60 min to ~7 min.")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        logger.error(f"Input directory {input_dir} does not exist")
        return

    # Reporting is imported lazily so the script still runs standalone if the
    # scripts package is not on the path.
    try:
        from scripts.lib.report import EventLog, Report
        report_enabled = True
    except Exception:
        report_enabled = False
        logger.warning("scripts.lib.report unavailable — running without file reporting")

    pdf_files = sorted(input_dir.rglob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDFs to process")

    from collections import Counter
    methods: Counter[str] = Counter()
    char_lengths: list[int] = []
    extracted = 0
    skipped_existing = 0
    failed = 0

    log = EventLog("extract_text_per_doc", args.data_dir) if report_enabled else None

    # Build the job list, skipping anything already extracted (idempotent).
    jobs: list[tuple[str, str]] = []
    for pdf_path in pdf_files:
        relative = pdf_path.relative_to(input_dir)
        output_path = output_dir / relative.with_suffix(".txt")
        if output_path.exists():
            logger.debug(f"SKIP (exists): {output_path.name}")
            skipped_existing += 1
            methods["skipped_already_extracted"] += 1
            continue
        jobs.append((str(pdf_path), str(output_path)))

    def _record(case_id: str, status: str, method: str, chars: int) -> None:
        nonlocal extracted, failed
        methods[method] += 1
        if status == "ok":
            extracted += 1
            char_lengths.append(chars)
        else:
            failed += 1
        if log:
            log.write(case_id=case_id, status=status, method=method, chars=chars)

    import time as _time
    t0 = _time.monotonic()

    if args.workers > 1 and jobs:
        from concurrent.futures import ProcessPoolExecutor
        logger.info(f"Extracting {len(jobs)} PDFs across {args.workers} workers")
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for i, (cid, status, method, chars) in enumerate(
                pool.map(_extract_one, jobs, chunksize=8), 1
            ):
                _record(cid, status, method, chars)
                if i % 100 == 0:
                    el = _time.monotonic() - t0
                    rate = i / max(el, 1e-6)
                    logger.info(f"{i}/{len(jobs)}  |  {rate:.1f} PDFs/s  |  "
                                f"~{(len(jobs)-i)/max(rate,1e-6)/60:.1f} min left")
    else:
        for i, job in enumerate(jobs, 1):
            _record(*_extract_one(job))
            if i % 100 == 0:
                el = _time.monotonic() - t0
                logger.info(f"{i}/{len(jobs)}  |  {i/max(el,1e-6):.1f} PDFs/s")

    if log:
        log.close()

    logger.info(f"Done. Extracted: {extracted}, Failed: {failed}, Already present: {skipped_existing}")

    if report_enabled:
        import statistics as _st
        rep = Report("extract_text", args.data_dir, args)
        rep.section("PDF text extraction (Q46)")
        rep.stat("pdfs_found", len(pdf_files))
        rep.stat("extracted_this_run", extracted)
        rep.stat("failed", failed)
        rep.stat("already_present", skipped_existing)
        rep.stat("failure_rate_pct",
                 round(100 * failed / max(extracted + failed, 1), 2),
                 "share of newly attempted PDFs that yielded no usable text")
        rep.table("Extraction method", ["method", "documents"],
                  [[k, v] for k, v in methods.most_common()])
        if char_lengths:
            rep.stat("chars_mean", round(_st.mean(char_lengths), 1))
            rep.stat("chars_median", round(_st.median(char_lengths), 1))
        rep.note("Failures are scanned/image-only PDFs (<100 chars of text), encrypted "
                 "files, and corrupt files. Per-document outcomes: "
                 "reports/extract_text_per_doc.jsonl")
        rep.save()


if __name__ == "__main__":
    main()
