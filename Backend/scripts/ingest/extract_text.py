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


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from PDF judgments")
    parser.add_argument("--input-dir", type=str, default="./data/raw/pdfs", help="Directory containing PDFs")
    parser.add_argument("--output-dir", type=str, default="./data/processed", help="Output directory for .txt files")
    parser.add_argument("--data-dir", type=str, default="../data",
                        help="Root data directory; reports are written to <data-dir>/reports/")
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

    for pdf_path in pdf_files:
        relative = pdf_path.relative_to(input_dir)
        output_path = output_dir / relative.with_suffix(".txt")

        if output_path.exists():
            logger.debug(f"SKIP (exists): {output_path.name}")
            skipped_existing += 1
            methods["skipped_already_extracted"] += 1
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        text, method = extract_text(pdf_path)
        methods[method] += 1

        if text:
            output_path.write_text(text, encoding="utf-8")
            extracted += 1
            char_lengths.append(len(text))
            logger.info(f"Extracted: {pdf_path.name} ({len(text)} chars)")
            if log:
                log.write(case_id=output_path.stem, status="ok", method=method, chars=len(text))
        else:
            failed += 1
            if log:
                log.write(case_id=output_path.stem, status="failed", method=method, chars=0)

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
