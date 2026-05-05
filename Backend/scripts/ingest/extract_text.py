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


def extract_text(pdf_path: Path) -> str | None:
    """Extract text from a PDF using pdfplumber, falling back to pypdf."""
    text = extract_with_pdfplumber(pdf_path)
    if text:
        return text
    logger.info(f"Falling back to pypdf for {pdf_path.name}")
    text = extract_with_pypdf(pdf_path)
    if text:
        return text
    logger.warning(f"SKIP (scanned/corrupted): {pdf_path.name}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from PDF judgments")
    parser.add_argument("--input-dir", type=str, default="./data/raw/pdfs", help="Directory containing PDFs")
    parser.add_argument("--output-dir", type=str, default="./data/processed", help="Output directory for .txt files")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        logger.error(f"Input directory {input_dir} does not exist")
        return

    pdf_files = sorted(input_dir.rglob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDFs to process")

    extracted = 0
    skipped = 0
    for pdf_path in pdf_files:
        relative = pdf_path.relative_to(input_dir)
        output_path = output_dir / relative.with_suffix(".txt")

        if output_path.exists():
            logger.debug(f"SKIP (exists): {output_path.name}")
            skipped += 1
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = extract_text(pdf_path)
        if text:
            output_path.write_text(text, encoding="utf-8")
            extracted += 1
            logger.info(f"Extracted: {pdf_path.name} ({len(text)} chars)")
        else:
            skipped += 1

    logger.info(f"Done. Extracted: {extracted}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
