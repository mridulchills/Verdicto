"""
Debate Agent — 3-round structured deliberation using Gemini Pro.
Round 1: Advocate argues for relevance.
Round 2: Opposing counsel challenges.
Round 3: Synthesis produces final consensus ranking.
"""
from __future__ import annotations
import json
from typing import Any
import structlog
from app.agents.base_agent import BaseAgent
from app.core.config import get_settings
from app.core.exceptions import AgentError
from app.core.gemini_client import get_gemini_client

logger = structlog.get_logger()
settings = get_settings()

ADVOCATE_PROMPT = """You are a Senior Advocate in the Supreme Court of India.
Given the legal query and the following case, make the strongest possible argument for why this case is highly relevant as a precedent.
Be specific about which legal principles from the case apply.
Query: {query}
Case: {case_summary}
Response must be JSON: {{"relevance_argument": "...", "key_principles": [...], "confidence": 0.0-1.0}}"""

OPPOSING_PROMPT = """You are a Senior Advocate in the Supreme Court of India tasked with challenging precedent selection.
Given the original query and the following case with its relevance argument, identify weaknesses.
Was this case overruled? Is the factual matrix different? Are there stronger precedents?
Query: {query}
Case: {case_summary}
Advocate's Argument: {relevance_argument}
Response must be JSON: {{"counterargument": "...", "weaknesses": [...], "overruled_by": "case_id or null", "confidence": 0.0-1.0}}"""

SYNTHESIS_PROMPT = """You are a Chief Justice reviewing arguments from both sides.
Produce a final consensus ranking with brief justification.
Query: {query}
Cases with arguments: {debate_transcript}
Response must be JSON: {{"final_ranking": ["case_id", ...], "rationale": "...", "disputes": [...]}}"""


class DebateAgent(BaseAgent):
    name: str = "debate"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        qid = input_data.get("query_id", "")
        query = input_data.get("original_query", "")
        ranked_cases = input_data.get("ranked_cases", [])
        max_rounds = min(settings.debate_max_rounds, 3)

        if not ranked_cases:
            return {"query_id": qid, "debate_rounds": [], "final_ranking": [], "consensus_rationale": "", "disagreement_flags": []}

        top_cases = ranked_cases[:5]
        client = get_gemini_client()
        debate_rounds = []
        transcript_entries = []

        try:
            # Round 1 — Advocate
            for case in top_cases:
                cid = case.get("case_id", "unknown")
                summary = f"Title: {case.get('title','')}, Year: {case.get('year','')}, Bench: {case.get('bench','')}, Facts: {str(case.get('facts_text',''))[:500]}"
                prompt = ADVOCATE_PROMPT.format(query=query, case_summary=summary)
                raw = await client.generate_text(prompt, model="pro", temperature=0.3)
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"relevance_argument": raw[:500], "key_principles": [], "confidence": 0.5}
                transcript_entries.append({"case_id": cid, "advocate": parsed})

            # Round 2 — Opposing
            for entry in transcript_entries:
                cid = entry["case_id"]
                case = next((c for c in top_cases if c.get("case_id") == cid), {})
                summary = f"Title: {case.get('title','')}, Year: {case.get('year','')}"
                prompt = OPPOSING_PROMPT.format(query=query, case_summary=summary, relevance_argument=entry["advocate"].get("relevance_argument",""))
                raw = await client.generate_text(prompt, model="pro", temperature=0.3)
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"counterargument": raw[:500], "weaknesses": [], "overruled_by": None, "confidence": 0.5}
                entry["opposing"] = parsed

            debate_rounds = [
                {"round_number": 1, "type": "advocate", "entries": [{k: v for k, v in e.items() if k in ("case_id", "advocate")} for e in transcript_entries]},
                {"round_number": 2, "type": "opposing", "entries": [{k: v for k, v in e.items() if k in ("case_id", "opposing")} for e in transcript_entries]},
            ]

            # Round 3 — Synthesis
            transcript_text = json.dumps(transcript_entries, default=str)[:3000]
            prompt = SYNTHESIS_PROMPT.format(query=query, debate_transcript=transcript_text)
            raw = await client.generate_text(prompt, model="pro", temperature=0.2)
            try:
                synthesis = json.loads(raw)
            except json.JSONDecodeError:
                synthesis = {"final_ranking": [e["case_id"] for e in transcript_entries], "rationale": raw[:500], "disputes": []}

            debate_rounds.append({"round_number": 3, "type": "synthesis", "result": synthesis})

            # Compute disagreement flags
            disagreements = synthesis.get("disputes", [])
            for entry in transcript_entries:
                opp = entry.get("opposing", {})
                if opp.get("overruled_by"):
                    disagreements.append(f"{entry['case_id']} may be overruled by {opp['overruled_by']}")

            return {
                "query_id": qid,
                "debate_rounds": debate_rounds,
                "final_ranking": synthesis.get("final_ranking", []),
                "consensus_rationale": synthesis.get("rationale", ""),
                "disagreement_flags": disagreements,
            }
        except Exception as e:
            raise AgentError(f"Debate agent failed: {e}", query_id=qid) from e
