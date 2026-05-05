"""
Generate embeddings for segmented case texts using Gemini text-embedding-004.
Processes in batches of 100, checkpoints progress to a .progress file.
Idempotent — reruns skip completed cases.

Usage:
    python -m scripts.ingest.build_embeddings --input-dir ./data/processed/segmented --output-dir ./data/embeddings
"""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path
import numpy as np
from app.services.embedding_service import get_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


# (redundant _LOCAL_MODEL and generate_embedding removed)


async def process_batch(files: list[Path], output_dir: Path, progress_file: Path) -> int:
    """Process a batch of files, generating embeddings."""
    # Load progress
    completed: set[str] = set()
    if progress_file.exists():
        completed = set(progress_file.read_text().strip().split("\n"))

    count = 0
    for f in files:
        if f.name in completed:
            continue

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            # Combine sections for embedding
            text = " ".join([
                data.get("facts", ""),
                data.get("issues", ""),
                data.get("reasoning", "")[:2000],
                data.get("outcome", ""),
            ]).strip()

            if not text or len(text) < 50:
                logger.warning(f"SKIP (too short): {f.name}")
                continue

            embedding = await get_embedding(text)

            out_path = output_dir / f.with_suffix(".npy").name
            np.save(str(out_path), np.array(embedding, dtype=np.float32))

            # Update progress
            with open(progress_file, "a") as pf:
                pf.write(f.name + "\n")

            count += 1
            if count % 10 == 0:
                logger.info(f"Processed {count} embeddings...")

            # Rate limiting
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Failed to embed {f.name}: {e}")
            continue

    return count


async def main_async(args: argparse.Namespace) -> None:
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_file = output_dir / ".progress"

    json_files = sorted(input_dir.glob("*.json"))
    logger.info(f"Found {len(json_files)} files to embed")

    # Process in batches
    total = 0
    for i in range(0, len(json_files), BATCH_SIZE):
        batch = json_files[i:i + BATCH_SIZE]
        logger.info(f"Processing batch {i // BATCH_SIZE + 1} ({len(batch)} files)")
        count = await process_batch(batch, output_dir, progress_file)
        total += count

    logger.info(f"Embedding complete. Total: {total}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate case embeddings")
    parser.add_argument("--input-dir", type=str, default="./data/processed/segmented")
    parser.add_argument("--output-dir", type=str, default="./data/embeddings")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
