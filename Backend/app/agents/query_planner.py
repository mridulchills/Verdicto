"""
Query Planner Agent — Parses and decomposes the user's natural language legal query.
Uses Gemini structured output to extract legal domain, issues, facts, and reformulated queries.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from app.agents.base_agent import BaseAgent
from app.core.exceptions import AgentError
from app.core.gemini_client import get_gemini_client

logger = structlog.get_logger()

QUERY_PLANNER_PROMPT = """You are an expert Indian Supreme Court legal researcher and query analyst.

Given the following legal query or case description, analyze it and produce a structured JSON response.

Legal Query:
{query}

You must respond with ONLY a JSON object containing:
{{
  "legal_domain": "one of: constitutional, civil, criminal, tax, labour, commercial, environmental, family, property, arbitration, administrative, general",
  "extracted_issues": ["list of specific legal issues/questions raised"],
  "extracted_facts": "summary of key factual elements",
  "target_outcome": "what outcome the querier seems to be looking for",
  "temporal_hint": "one of: recent, historical, any",
  "reformulated_queries": ["2-3 alternative search queries that capture different angles of the same legal issue"],
  "confidence": 0.0 to 1.0
}}

Be specific to Indian law. Identify relevant Acts, Articles, and Sections where possible.
Respond with ONLY the JSON, no other text.
"""


class QueryPlannerAgent(BaseAgent):
    """
    Parses raw user queries into structured legal analysis parameters.
    Stateless — all state passes through input_data → return dict.
    """

    name: str = "query_planner"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute query planning.

        Input: {"query_id": str, "query": str}
        Output: QueryPlannerOutput-compatible dict
        """
        query = input_data.get("query", "")
        query_id = input_data.get("query_id", str(uuid.uuid4()))

        if not query.strip():
            raise AgentError("Empty query provided", query_id=query_id)

        client = get_gemini_client()

        prompt = QUERY_PLANNER_PROMPT.format(query=query)

        try:
            raw_response = await client.generate_text(
                prompt,
                model="flash",
                temperature=0.1,
            )

            # Clean the response of potential markdown formatting and think blocks
            cleaned_response = raw_response.strip()
            # Strip <think>...</think> blocks (deepseek-r1 reasoning traces)
            import re as _re
            cleaned_response = _re.sub(r"<think>.*?</think>", "", cleaned_response, flags=_re.DOTALL).strip()
            if cleaned_response.startswith("```"):
                import re
                match = re.search(r"```(?:json)?\n?(.*?)\n?```", cleaned_response, re.DOTALL)
                if match:
                    cleaned_response = match.group(1)
            # Try to find JSON object if not clean JSON
            if not cleaned_response.startswith("{"):
                import re
                match = re.search(r"\{.*\}", cleaned_response, re.DOTALL)
                if match:
                    cleaned_response = match.group(0)
            
            # Parse the JSON response
            parsed = json.loads(cleaned_response)


            return {
                "query_id": query_id,
                "original_query": query,
                "legal_domain": parsed.get("legal_domain", "general"),
                "extracted_issues": parsed.get("extracted_issues", []),
                "extracted_facts": parsed.get("extracted_facts", ""),
                "target_outcome": parsed.get("target_outcome", ""),
                "temporal_hint": parsed.get("temporal_hint", "any"),
                "reformulated_queries": parsed.get("reformulated_queries", []),
                "confidence": float(parsed.get("confidence", 0.5)),
            }

        except json.JSONDecodeError as e:
            logger.warning(
                "query_planner.json_parse_failed",
                error=str(e),
                query_id=query_id,
            )
            # Graceful degradation — return basic structure
            return {
                "query_id": query_id,
                "original_query": query,
                "legal_domain": "general",
                "extracted_issues": [query],
                "extracted_facts": query,
                "target_outcome": "",
                "temporal_hint": "any",
                "reformulated_queries": [query],
                "confidence": 0.3,
            }
        except Exception as e:
            raise AgentError(
                f"Query planner failed: {e}", query_id=query_id
            ) from e
