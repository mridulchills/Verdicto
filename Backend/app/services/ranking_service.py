"""
Ranking service — RRF merge and final score computation.
"""
from __future__ import annotations
from typing import Any


def rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score."""
    return 1.0 / (k + rank)


def compute_final_score(semantic: float, authority: float, structural: float) -> float:
    """
    Final relevance score formula from PRD:
    final_score = 0.5 * semantic_score + 0.3 * authority_score + 0.2 * structural_alignment_score
    All scores clamped to [0, 1].
    """
    raw = 0.5 * semantic + 0.3 * authority + 0.2 * structural
    return max(0.0, min(1.0, raw))
