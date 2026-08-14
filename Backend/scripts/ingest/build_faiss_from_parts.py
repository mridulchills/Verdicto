"""
Build the FAISS chunk index from encoded .npy parts — deliberately torch-free.

WHY A SEPARATE SCRIPT
faiss and torch both link libomp. On macOS, calling faiss in a process that has already
loaded torch deadlocks: index.add() sits at 0 % CPU indefinitely. Splitting the encode
step (needs torch) from the index step (needs faiss) removes the conflict entirely, and
makes the expensive encoding resumable.

Usage (from Backend/):
    python -m scripts.ingest.build_faiss_from_parts \
        --parts-dir ../data/index/cases_chunk_parts --out-index ../data/index/cases_chunk.index
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build FAISS index from encoded parts")
    ap.add_argument("--parts-dir", type=str, required=True)
    ap.add_argument("--out-index", type=str, required=True)
    ap.add_argument("--allow-partial", action="store_true",
                    help="build even if fewer vectors than owner entries. The index will "
                         "cover only the earliest documents — diagnostics only.")
    args = ap.parse_args()

    import faiss  # imported first and alone — no torch in this process

    parts_dir = Path(args.parts_dir)
    index_path = Path(args.out_index)
    map_path = index_path.with_name(index_path.stem + "_mapping.json")

    part_files = sorted(parts_dir.glob("part_*.npy"))
    if not part_files:
        raise SystemExit(f"No part_*.npy in {parts_dir}")
    owner = json.loads((parts_dir / "owner.json").read_text(encoding="utf-8"))

    logger.info(f"loading {len(part_files)} parts")
    mats = [np.load(str(p)).astype(np.float32) for p in part_files]
    vecs = np.vstack(mats)
    logger.info(f"matrix {vecs.shape}; owner entries {len(owner)}")

    if len(owner) != len(vecs) and args.allow_partial:
        logger.warning(f"PARTIAL INDEX: {len(vecs)}/{len(owner)} vectors — covers only "
                       "the earliest documents. Never report retrieval numbers from this.")
        n = min(len(owner), len(vecs))
        owner, vecs = owner[:n], vecs[:n]
    elif len(owner) != len(vecs):
        # ABORT, do not truncate. This was a warning once, and it silently produced a
        # 24,000-vector index from a 95,350-entry owner map after an encoding run was
        # interrupted. Truncation keeps only the FIRST n chunks, and because the parts
        # are written in corpus order that means the index covers only the earliest
        # documents — a biased index that still returns confident scores and shows up
        # nowhere as an error. A partial index is never the thing you wanted.
        raise SystemExit(
            f"owner/vector mismatch: {len(owner)} owner entries vs {len(vecs)} vectors "
            f"({len(vecs) / max(len(owner), 1):.1%} encoded).\n"
            "Encoding is INCOMPLETE — re-run build_chunk_embeddings until it logs "
            "'encoding complete', then re-run this script. Refusing to build a "
            "partial index.\n"
            "If a partial index is genuinely wanted, pass --allow-partial.")

    faiss.normalize_L2(vecs)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    map_path.write_text(json.dumps({str(i): cid for i, cid in enumerate(owner)}),
                        encoding="utf-8")
    logger.info(f"index: {index.ntotal} vectors, dim {index.d} -> {index_path}")
    logger.info(f"mapping: {len(owner)} entries -> {map_path}")


if __name__ == "__main__":
    main()
