"""
Explanation service — generates human-readable rationale for results.
"""
from __future__ import annotations
from typing import Any


def generate_explanation(case: dict[str, Any], query_issues: list[str]) -> str:
    """Generate a brief human-readable explanation of why a case was ranked."""
    parts = []
    if case.get("title"):
        parts.append(f"This case ({case['title']})")
    if case.get("authority_score", 0) > 0.7:
        parts.append("has high authority")
    if case.get("bench"):
        parts.append(f"decided by {case['bench']}")
    if case.get("year"):
        parts.append(f"in {case['year']}")
    return " ".join(parts) + "." if parts else "Relevant case based on semantic similarity."
