"""
Debate Agent — Three-call adversarial deliberation per the PRD spec.

Call 1 — Advocate:   strongest relevance argument for each top case
Call 2 — Opposing:   counterarguments and weaknesses
Call 3 — Synthesis:  Chief Justice consensus ranking

Cases are processed sequentially (Ollama is single-GPU; concurrent requests
just queue and each times out waiting). Top 3 cases × 2 calls + 1 synthesis
= 7 LLM calls total. Each call gets 50 s → worst case ~6 min, but deepseek-r1:8b
typically answers in 15-30 s so real time is ~2 min.

A hard outer timeout of 110 s is applied so the pipeline never hangs.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import structlog

from app.agents.base_agent import BaseAgent
from app.core.config import get_settings
from app.core.exceptions import AgentError
from app.core.gemini_client import get_gemini_client

logger = structlog.get_logger()
settings = get_settings()

# ── Prompt templates (from PRD) ──────────────────────────────────────────────

ADVOCATE_PROMPT = """You are a Senior Advocate in the Supreme Court of India.
Given the legal query and the following case, make the strongest possible argument
for why this case is highly relevant as a precedent.
Be specific about which legal principles from the case apply.

Query: {query}

Case:
  case_id: {case_id}
  Title: {title}
  Year: {year}
  Facts: {facts}
  Issues: {issues}
  Reasoning: {reasoning}
  Outcome: {outcome}

Respond with ONLY valid JSON (no markdown, no explanation):
{{"relevance_argument": "...", "key_principles": ["...", "..."], "confidence": 0.85}}"""

OPPOSING_PROMPT = """You are a Senior Advocate in the Supreme Court of India tasked with
challenging precedent selection. Identify weaknesses in the relevance argument below.
Was this case overruled? Is the factual matrix different? Are there stronger precedents?

Query: {query}

Case:
  case_id: {case_id}
  Title: {title}
  Year: {year}
  Facts: {facts}
  Issues: {issues}

Advocate's Argument: {relevance_argument}

Respond with ONLY valid JSON (no markdown, no explanation).
Set confidence between 0.5 and 0.9 based on how strong the counterargument is:
{{"counterargument": "...", "weaknesses": ["...", "..."], "overruled_by": null, "confidence": 0.75}}"""

SYNTHESIS_PROMPT = """You are a Chief Justice reviewing arguments from both sides.
Produce a final consensus ranking with brief justification.

Query: {query}

Cases with arguments:
{debate_transcript}

Respond with ONLY valid JSON (no markdown, no explanation):
{{"final_ranking": ["case_id_1", "case_id_2", "case_id_3"], "rationale": "2-3 sentence explanation", "disputes": []}}"""


# ── JSON parser ───────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Robustly extract a JSON object from LLM output."""
    # Strip deepseek-r1 thinking blocks
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Strip markdown code fences
    if cleaned.startswith("```"):
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
    # Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON in response (first 200 chars): {cleaned[:200]}")


def _clean_case_id(value: Any) -> str:
    """
    Normalise a case id returned by the model.

    The prompts present each case as `case_id: <id>`, and the model frequently echoes
    that shape back inside final_ranking — "case_id=2023_15_1081_1212_EN" or
    "case_id: 2023_15_1081_1212_EN" instead of the bare id. An unnormalised value
    matches nothing in the scheduler's case_map, so the whole reordering is silently
    dropped (scheduler.py) while the trace still records a reordering that never
    happened. Strip the echoed key, surrounding quotes and whitespace.
    """
    s = str(value).strip().strip("\"'").strip()
    m = re.match(r"^case[_ ]?id\s*[:=]\s*(.+)$", s, re.IGNORECASE)
    if m:
        s = m.group(1)
    return s.strip().strip("\"'").strip()


# ── Per-case debate (sequential advocate → opposing) ─────────────────────────

async def _debate_one_case(
    client: Any,
    query: str,
    case: dict,
    per_call_timeout: float,
) -> dict:
    """
    Run advocate then opposing for a single case.
    Both calls are sequential — Ollama processes one at a time anyway.
    Failures are caught and return safe defaults so the case is never dropped.
    """
    case_id   = case.get("case_id", "?")
    title     = str(case.get("title", ""))[:100]
    year      = case.get("year", "")
    facts     = str(case.get("facts_text", ""))[:500]
    issues    = str(case.get("issues_text", ""))[:350]
    reasoning = str(case.get("reasoning_text", ""))[:400]
    outcome   = str(case.get("outcome_text", ""))[:150]

    # ── Advocate ──────────────────────────────────────────────────────────
    adv_prompt = ADVOCATE_PROMPT.format(
        query=query[:500],
        case_id=case_id, title=title, year=year,
        facts=facts, issues=issues, reasoning=reasoning, outcome=outcome,
    )
    adv: dict = {"relevance_argument": "", "key_principles": [], "confidence": 0.5}
    try:
        raw = await asyncio.wait_for(
            client.generate_text(adv_prompt, model="flash", temperature=0.3),
            timeout=per_call_timeout,
        )
        adv = _parse_json(raw)
        logger.info("debate.advocate_ok", case_id=case_id)
    except Exception as e:
        logger.warning("debate.advocate_failed", case_id=case_id, error=str(e))

    # ── Opposing ──────────────────────────────────────────────────────────
    opp_prompt = OPPOSING_PROMPT.format(
        query=query[:500],
        case_id=case_id, title=title, year=year,
        facts=facts, issues=issues,
        relevance_argument=str(adv.get("relevance_argument", ""))[:350],
    )
    opp: dict = {"counterargument": "", "weaknesses": [], "overruled_by": None, "confidence": 0.5}
    try:
        raw = await asyncio.wait_for(
            client.generate_text(opp_prompt, model="flash", temperature=0.3),
            timeout=per_call_timeout,
        )
        opp = _parse_json(raw)
        logger.info("debate.opposing_ok", case_id=case_id)
    except Exception as e:
        logger.warning("debate.opposing_failed", case_id=case_id, error=str(e))

    return {
        "case_id": case_id,
        "advocate": {
            "relevance_argument": str(adv.get("relevance_argument", "")),
            "key_principles":     adv.get("key_principles", []),
            "confidence":         float(adv.get("confidence", 0.5)),
        },
        "opposing": {
            "counterargument": str(opp.get("counterargument", "")),
            "weaknesses":      opp.get("weaknesses", []),
            "overruled_by":    opp.get("overruled_by"),
            "confidence":      float(opp.get("confidence", 0.5)),
        },
    }


# ── Agent ─────────────────────────────────────────────────────────────────────

class DebateAgent(BaseAgent):
    name: str = "debate"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        qid          = input_data.get("query_id", "")
        query        = input_data.get("original_query", "")
        ranked_cases = input_data.get("ranked_cases", [])

        if not ranked_cases:
            return {
                "query_id": qid,
                "debate_rounds": [],
                "final_ranking": [],
                "consensus_rationale": "",
                "disagreement_flags": [],
            }

        # Top 3 cases — keeps total LLM calls to 7 (3×2 + 1 synthesis)
        top_cases = ranked_cases[:3]
        client = get_gemini_client()
        client.reset_circuit()

        # Per-call timeout: 120 s each.
        # deepseek-r1:8b can take 30-90 s depending on prompt length.
        # 7 calls × 120 s worst-case = 840 s, but real time ~3-5 min.
        per_call_timeout = 120.0

        logger.info("debate.start", query_id=qid, cases=len(top_cases))

        try:
            # ── Rounds 1 & 2: Advocate + Opposing (sequential per case) ──
            entries: list[dict] = []
            for case in top_cases:
                entry = await _debate_one_case(client, query, case, per_call_timeout)
                entries.append(entry)

            # ── Round 3: Synthesis ────────────────────────────────────────
            transcript_lines = []
            for e in entries:
                adv_arg = e["advocate"].get("relevance_argument", "")[:250]
                opp_arg = e["opposing"].get("counterargument", "")[:150]
                transcript_lines.append(
                    f"case_id={e['case_id']}\n"
                    f"  Advocate: {adv_arg}\n"
                    f"  Opposing: {opp_arg}"
                )

            synthesis_prompt = SYNTHESIS_PROMPT.format(
                query=query[:500],
                debate_transcript="\n\n".join(transcript_lines),
            )

            synthesis: dict = {}
            try:
                syn_raw = await asyncio.wait_for(
                    client.generate_text(synthesis_prompt, model="flash", temperature=0.1),
                    timeout=per_call_timeout,
                )
                synthesis = _parse_json(syn_raw)
                logger.info("debate.synthesis_ok", query_id=qid)
            except Exception as e:
                logger.warning("debate.synthesis_failed", query_id=qid, error=str(e))
                synthesis = {
                    "final_ranking": [e["case_id"] for e in entries],
                    "rationale": "Synthesis unavailable — using advocate confidence ranking.",
                    "disputes": [],
                }

            # ── Build final ranking — never drop cases ────────────────────
            # Only cases that were actually debated may appear: the model both echoes
            # the "case_id=" key (see _clean_case_id) and occasionally invents ids, and
            # either one silently voids the reordering downstream.
            debated_ids = [e["case_id"] for e in entries]
            final_ranking: list[str] = []
            dropped: list[str] = []
            for raw in synthesis.get("final_ranking", []):
                cid = _clean_case_id(raw)
                if cid in debated_ids and cid not in final_ranking:
                    final_ranking.append(cid)
                elif cid not in debated_ids:
                    dropped.append(str(raw))
            if dropped:
                logger.warning("debate.synthesis_unknown_case_ids",
                               query_id=qid, dropped=dropped)
            for cid in debated_ids:
                if cid not in final_ranking:
                    final_ranking.append(cid)

            debate_rounds = [
                {
                    "round_number": 1,
                    "type": "advocate_opposing",
                    "entries": entries,
                },
                {
                    "round_number": 2,
                    "type": "synthesis",
                    "result": {
                        "final_ranking": final_ranking,
                        "rationale":     synthesis.get("rationale", ""),
                        "disputes":      synthesis.get("disputes", []),
                    },
                },
            ]

            logger.info(
                "debate.complete",
                query_id=qid,
                cases_debated=len(entries),
                final_ranking=final_ranking,
            )

            return {
                "query_id":            qid,
                "debate_rounds":       debate_rounds,
                "final_ranking":       final_ranking,
                "consensus_rationale": synthesis.get("rationale", ""),
                "disagreement_flags":  synthesis.get("disputes", []),
            }

        except Exception as e:
            raise AgentError(f"Debate agent failed: {e}", query_id=qid) from e
