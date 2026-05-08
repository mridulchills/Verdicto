"""
Download Indian Supreme Court judgment metadata from AWS S3 public bucket.
Supports --year-from and --year-to CLI args. Idempotent — skips already downloaded files.

Usage:
    python -m scripts.ingest.download_dataset --year-from 2020 --year-to 2024
"""
from __future__ import annotations
import argparse
import json
import logging
import os
from pathlib import Path
import boto3
import tarfile
from botocore import UNSIGNED
from botocore.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S3_BUCKET = "indian-supreme-court-judgments"
S3_CONFIG = Config(signature_version=UNSIGNED)


def download_metadata_parquet(year: int, output_dir: Path) -> Path | None:
    """Download Parquet metadata for a given year."""
    s3 = boto3.client("s3", config=S3_CONFIG)
    prefix = f"metadata/parquet/year={year}/"
    output_year_dir = output_dir / f"metadata/parquet/year={year}"
    output_year_dir.mkdir(parents=True, exist_ok=True)

    try:
        response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        if "Contents" not in response:
            logger.warning(f"No metadata found for year {year}")
            return None

        for obj in response["Contents"]:
            key = obj["Key"]
            filename = key.split("/")[-1]
            if not filename:
                continue
            output_path = output_year_dir / filename
            if output_path.exists():
                logger.info(f"SKIP (exists): {output_path}")
                continue
            logger.info(f"Downloading: s3://{S3_BUCKET}/{key} -> {output_path}")
            s3.download_file(S3_BUCKET, key, str(output_path))

        return output_year_dir
    except Exception as e:
        logger.error(f"Failed to download metadata for year {year}: {e}")
        return None


def download_index_json(year: int, output_dir: Path) -> Path | None:
    """Download the english.index.json for a given year."""
    s3 = boto3.client("s3", config=S3_CONFIG)
    key = f"data/tar/year={year}/english/english.index.json"
    output_path = output_dir / f"index/year={year}/english.index.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        logger.info(f"SKIP (exists): {output_path}")
        return output_path

    try:
        logger.info(f"Downloading: s3://{S3_BUCKET}/{key}")
        s3.download_file(S3_BUCKET, key, str(output_path))
        return output_path
    except Exception as e:
        logger.warning(f"Could not download index for year {year}: {e}")
        return None


def download_and_extract_tar(year: int, output_dir: Path) -> bool:
    """Download the english.tar for a year and extract PDFs."""
    s3 = boto3.client("s3", config=S3_CONFIG)
    key = f"data/tar/year={year}/english/english.tar"
    pdf_output_dir = output_dir / "pdfs"
    pdf_output_dir.mkdir(parents=True, exist_ok=True)
    
    tar_path = output_dir / f"english_{year}.tar"

    try:
        if not tar_path.exists():
            logger.info(f"Downloading bulk TAR for {year}: s3://{S3_BUCKET}/{key}")
            s3.download_file(S3_BUCKET, key, str(tar_path))
        
        logger.info(f"Extracting PDFs from {tar_path.name}...")
        with tarfile.open(tar_path) as tar:
            # We only want .pdf files
            members = [m for m in tar.getmembers() if m.name.endswith(".pdf")]
            # To avoid huge extractions, we could limit here, but let's do all
            # or first 50 for a 'demo' mode if we wanted. 
            # For now, let's extract all in the archive.
            tar.extractall(path=pdf_output_dir, members=members)
        
        # Cleanup tar to save space
        tar_path.unlink()
        logger.info(f"Successfully extracted PDFs for {year}")
        return True
    except Exception as e:
        logger.error(f"Failed to process TAR for {year}: {e}")
        if tar_path.exists():
            tar_path.unlink()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SC judgment metadata from S3")
    parser.add_argument("--year-from", type=int, default=2024, help="Start year (inclusive)")
    parser.add_argument("--year-to", type=int, default=2024, help="End year (inclusive)")
    parser.add_argument("--output-dir", type=str, default="./data/raw", help="Output directory")
    parser.add_argument("--skip-pdfs", action="store_true", help="Skip downloading bulk PDFs")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading metadata for years {args.year_from}-{args.year_to}")
    for year in range(args.year_from, args.year_to + 1):
        logger.info(f"--- Year {year} ---")
        download_metadata_parquet(year, output_dir)
        download_index_json(year, output_dir)
        
        if not args.skip_pdfs:
            download_and_extract_tar(year, output_dir)

    logger.info("Download complete.")


if __name__ == "__main__":
    main()
