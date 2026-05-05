"""
Build FAISS IndexFlatIP from generated embeddings.
Normalizes all vectors before indexing (inner product = cosine similarity).
Persists index and mapping to disk.

Usage:
    python -m scripts.ingest.build_faiss_index --embeddings-dir ./data/embeddings --output-dir ./data/index
"""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
import faiss
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FAISS index")
    parser.add_argument("--embeddings-dir", type=str, default="./data/embeddings")
    parser.add_argument("--output-dir", type=str, default="./data/index")
    args = parser.parse_args()

    embeddings_dir = Path(args.embeddings_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    npy_files = sorted(embeddings_dir.glob("*.npy"))
    if not npy_files:
        logger.error("No .npy embedding files found!")
        return

    logger.info(f"Found {len(npy_files)} embedding files")

    # Load all embeddings
    vectors: list[np.ndarray] = []
    mapping: dict[str, str] = {}  # faiss_position -> case_id

    for i, npy_path in enumerate(npy_files):
        vec = np.load(str(npy_path)).astype(np.float32)
        vectors.append(vec)
        # Derive case_id from filename (e.g., "2023_SC_1234.npy" -> "2023_SC_1234")
        case_id = npy_path.stem.replace(".json", "").replace(".txt", "")
        mapping[str(i)] = case_id

    # Stack into matrix
    matrix = np.vstack(vectors)
    dim = matrix.shape[1]
    logger.info(f"Matrix shape: {matrix.shape} (dim={dim})")

    # Normalize for cosine similarity via inner product
    faiss.normalize_L2(matrix)

    # Build index
    index = faiss.IndexFlatIP(dim)
    index.add(matrix)
    logger.info(f"FAISS index built with {index.ntotal} vectors")

    # Save
    index_path = output_dir / "cases.index"
    mapping_path = output_dir / "cases_mapping.json"

    faiss.write_index(index, str(index_path))
    logger.info(f"Index saved to {index_path}")

    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    logger.info(f"Mapping saved to {mapping_path} ({len(mapping)} entries)")


if __name__ == "__main__":
    main()
