"""
Precedent Weighting Agent — Re-ranks candidates using legal authority signals.
"""
from __future__ import annotations
import re
from datetime import date
from typing import Any
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.base_agent import BaseAgent
from app.core.exceptions import AgentError
from app.models.case import Case, Citation

logger = structlog.get_logger()
WEIGHTS = {"citation_count": 0.35, "bench_size": 0.20, "recency": 0.15, "factual_alignment": 0.20, "domain_match": 0.10}

def _extract_bench_size(bench_text: str | None) -> int:
    if not bench_text: return 2
    match = re.search(r"(\d+)\s*[-]?\s*[Jj]udge", bench_text)
    if match: return int(match.group(1))
    return max(len([n for n in bench_text.split(",") if n.strip()]), 1)

def _bench_size_score(bs: int) -> float:
    if bs >= 5: return 1.0
    if bs >= 3: return 0.6
    return 0.3

def _recency_score(yr: int | None) -> float:
    if yr is None: return 0.3
    age = date.today().year - yr
    if age <= 0: return 1.0
    if age >= 30: return 0.1
    return 1.0 - (age / 30) * 0.9

def _norm(val: float, mn: float, mx: float) -> float:
    if mx == mn: return 0.5
    return max(0.0, min(1.0, (val - mn) / (mx - mn)))

class PrecedentWeighterAgent(BaseAgent):
    name: str = "precedent_weighting"
    def __init__(self, db_session: AsyncSession | None = None) -> None:
        self._db = db_session

    async def _meta(self, ids: list[str]) -> dict[str, dict]:
        if not self._db or not ids: return {}
        r = await self._db.execute(select(Case).where(Case.case_id.in_(ids)))
        return {c.case_id: {"title": c.title, "year": c.year, "bench": c.bench, "decision_date": c.decision_date, "facts_text": c.facts_text or "", "issues_text": c.issues_text or "", "disposal_nature": c.disposal_nature, "acts_sections": c.acts_sections or [], "citation": c.citation} for c in r.scalars().all()}

    async def _cites(self, ids: list[str]) -> dict[str, int]:
        if not self._db or not ids: return {}
        r = await self._db.execute(select(Citation.cited_case_id, func.count()).where(Citation.cited_case_id.in_(ids)).group_by(Citation.cited_case_id))
        return {row[0]: row[1] for row in r.fetchall()}

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        qid = input_data.get("query_id", "")
        cands = input_data.get("candidates", [])
        domain = input_data.get("legal_domain", "general")
        if not cands: return {"query_id": qid, "ranked_cases": [], "reranked_count": 0}
        ids = [c["case_id"] for c in cands]
        try:
            meta = await self._meta(ids)
            cites = await self._cites(ids)
            scored = []
            for c in cands:
                m = meta.get(c["case_id"], {})
                cc = float(cites.get(c["case_id"], 0))
                bs = _bench_size_score(_extract_bench_size(m.get("bench")))
                rc = _recency_score(m.get("year"))
                ds = 1.0 if domain.lower() != "general" and domain.lower() in (m.get("issues_text","")+" "+m.get("facts_text","")).lower() else 0.3
                scored.append({**c, **m, "cite_count": cc, "raw_bench": bs, "raw_recency": rc, "domain_score": ds, "factual_alignment": c.get("rrf_score", 0.0)})
            if scored:
                mx_c = max(s["cite_count"] for s in scored) or 1.0
                mn_c = min(s["cite_count"] for s in scored)
                mx_f = max(s["factual_alignment"] for s in scored) or 1.0
                mn_f = min(s["factual_alignment"] for s in scored)
                for s in scored:
                    nc = _norm(s["cite_count"], mn_c, mx_c)
                    nf = _norm(s["factual_alignment"], mn_f, mx_f)
                    s["authority_score"] = round(min(1.0, WEIGHTS["citation_count"]*nc + WEIGHTS["bench_size"]*s["raw_bench"] + WEIGHTS["recency"]*s["raw_recency"] + WEIGHTS["factual_alignment"]*nf + WEIGHTS["domain_match"]*s["domain_score"]), 4)
            scored.sort(key=lambda x: x.get("authority_score", 0), reverse=True)
            return {"query_id": qid, "ranked_cases": scored[:20], "reranked_count": min(20, len(scored))}
        except Exception as e:
            raise AgentError(f"Precedent weighting failed: {e}", query_id=qid) from e
