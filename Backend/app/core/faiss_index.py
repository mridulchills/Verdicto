"""
FAISS index wrapper — read-only at API runtime.
Loads index at startup and provides search functionality.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import structlog

from app.core.config import get_settings
from app.core.exceptions import IndexNotFoundError

logger = structlog.get_logger()
settings = get_settings()


class FAISSIndex:
    """
    Wrapper around a FAISS IndexFlatIP for cosine similarity search.
    Embeddings are assumed to be L2-normalized before indexing,
    so inner product == cosine similarity.

    The index is READ-ONLY at runtime. Writes only happen during ingestion.
    """

    def __init__(self) -> None:
        self._index: faiss.IndexFlatIP | None = None
        self._mapping: dict[int, str] = {}  # FAISS position → case_id
        self._reverse_mapping: dict[str, int] = {}  # case_id → FAISS position

    def load(self) -> None:
        """Load FAISS index and mapping from disk. Fails fast if files are missing."""
        index_path = Path(settings.faiss_index_path)
        mapping_path = Path(settings.faiss_mapping_path)

        if not index_path.exists():
            msg = (
                f"FAISS index not found at {index_path}. "
                "Run scripts/ingest/build_faiss_index.py first."
            )
            logger.error("faiss.index_not_found", path=str(index_path))
            raise IndexNotFoundError(msg)

        if not mapping_path.exists():
            msg = (
                f"FAISS mapping not found at {mapping_path}. "
                "Run scripts/ingest/build_faiss_index.py first."
            )
            logger.error("faiss.mapping_not_found", path=str(mapping_path))
            raise IndexNotFoundError(msg)

        self._index = faiss.read_index(str(index_path))
        logger.info(
            "faiss.index_loaded",
            path=str(index_path),
            total_vectors=self._index.ntotal,
            dimension=self._index.d,
        )

        with open(mapping_path, "r", encoding="utf-8") as f:
            raw_mapping: dict[str, str] = json.load(f)

        # Mapping file stores {str(faiss_pos): case_id}
        self._mapping = {int(k): v for k, v in raw_mapping.items()}
        self._reverse_mapping = {v: int(k) for k, v in raw_mapping.items()}
        logger.info("faiss.mapping_loaded", total_cases=len(self._mapping))

    @property
    def is_loaded(self) -> bool:
        return self._index is not None

    @property
    def total_vectors(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal

    @property
    def dimension(self) -> int:
        if self._index is None:
            return 0
        return self._index.d

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Search the index for nearest neighbors.
        Normalizes the query embedding before search.

        Returns a list of {case_id: str, score: float} sorted by descending score.
        """
        if self._index is None:
            raise IndexNotFoundError("FAISS index not loaded. Call load() first.")

        query_vec = np.array([query_embedding], dtype=np.float32)

        # Normalize the query vector for cosine similarity via inner product
        faiss.normalize_L2(query_vec)

        # Clamp top_k to index size
        effective_k = min(top_k, self._index.ntotal)

        distances, indices = self._index.search(query_vec, effective_k)

        results: list[dict[str, Any]] = []
        for score, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            case_id = self._mapping.get(int(idx))
            if case_id is not None:
                results.append(
                    {
                        "case_id": case_id,
                        "faiss_score": float(score),
                        "faiss_rank": len(results) + 1,
                    }
                )

        logger.info(
            "faiss.search_complete",
            query_dim=len(query_embedding),
            top_k=top_k,
            results_count=len(results),
        )
        return results

    def get_case_embedding(self, case_id: str) -> list[float] | None:
        """Retrieve the stored embedding for a case_id (useful for similar-case queries)."""
        if self._index is None:
            return None
        pos = self._reverse_mapping.get(case_id)
        if pos is None:
            return None
        vec = self._index.reconstruct(pos)
        return vec.tolist()


# Module-level singleton
_faiss_index: FAISSIndex | None = None


def get_faiss_index() -> FAISSIndex:
    """Get or create the singleton FAISS index wrapper."""
    global _faiss_index
    if _faiss_index is None:
        _faiss_index = FAISSIndex()
    return _faiss_index
