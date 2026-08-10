"""
Scheduler Agent — Orchestrates the entire multi-agent pipeline.
Decides whether to iterate based on evaluator confidence.
Max iterations: min(settings.scheduler_max_iterations, 3) regardless of debate flag.
Debate is limited to iteration == 1 by the guard inside the loop.
"""
from __future__ import annotations
import time
from typing import Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.base_agent import BaseAgent
from app.agents.query_planner import QueryPlannerAgent
from app.agents.retriever import RetrieverAgent
from app.agents.precedent_weighter import PrecedentWeighterAgent
from app.agents.debate import DebateAgent
from app.agents.evaluator import EvaluatorAgent
from app.core.config import get_settings
from app.core.exceptions import AgentError

logger = structlog.get_logger()
settings = get_settings()


def _ms(start: float) -> int:
    """Return elapsed milliseconds since start."""
    return int((time.monotonic() - start) * 1000)


class SchedulerAgent(BaseAgent):
    name: str = "scheduler"

    def __init__(self, db_session: AsyncSession | None = None) -> None:
        self._db = db_session

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        qid = input_data.get("query_id", "")
        query = input_data.get("query", "")
        filters = input_data.get("filters", {})
        options = input_data.get("options", {})
        enable_debate = options.get("enable_debate", True)
        top_k = options.get("top_k", 10)

        pipeline_start = time.monotonic()
        trace: dict[str, Any] = {}
        iteration = 0

        # Allow up to 3 iterations for refinement regardless of debate flag.
        # The debate guard (iteration == 1) already limits debate to the first pass.
        max_iter = min(settings.scheduler_max_iterations, 3)

        # Reset circuit breaker at pipeline start so stale failures don't block agents
        from app.core.gemini_client import get_gemini_client as _get_client
        _get_client().reset_circuit()

        # Snapshot token usage so the trace can record THIS query's cost.
        # The client is a process-wide singleton, so its counters are cumulative —
        # we record the delta rather than the running total (Q37).
        _usage_baseline = dict(_get_client().get_usage_stats())

        async def _callback():
            if "trace_callback" in input_data:
                await input_data["trace_callback"](trace)

        try:
            # ── Step 1: Query Planner ──────────────────────────────────────
            t0 = time.monotonic()
            planner = QueryPlannerAgent()
            plan_result = await planner.execute({"query_id": qid, "query": query})
            planner_ms = _ms(t0)

            trace["query_planner"] = {
                "agent_name": "query_planner",
                "status": "complete",
                "latency_ms": planner_ms,
                "input_size": len(query),
                "output_size": len(str(plan_result)),
                "details": {
                    "legal_domain": plan_result.get("legal_domain"),
                    "issues_count": len(plan_result.get("extracted_issues", [])),
                    "confidence": plan_result.get("confidence"),
                    "reformulated_queries": len(plan_result.get("reformulated_queries", [])),
                },
            }
            await _callback()

            best_result: dict[str, Any] = {}
            best_eval: dict[str, Any] = {}
            best_debate: dict[str, Any] = {}

            while iteration < max_iter:
                iteration += 1
                logger.info("scheduler.iteration", iteration=iteration, query_id=qid)

                # ── Step 2: Retriever ──────────────────────────────────────
                t0 = time.monotonic()
                retriever = RetrieverAgent(db_session=self._db)
                retriever_input = {**plan_result, "filters": filters}
                retrieval_result = await retriever.execute(retriever_input)
                retriever_ms = _ms(t0)

                trace["retriever"] = {
                    "agent_name": "retriever",
                    "status": "complete",
                    "latency_ms": retriever_ms,
                    "input_size": len(str(retriever_input)),
                    "output_size": len(str(retrieval_result)),
                    "details": {
                        "faiss_hits": retrieval_result.get("faiss_hits", 0),
                        "bm25_hits": retrieval_result.get("bm25_hits", 0),
                        "after_rrf": retrieval_result.get("after_rrf", 0),
                        "iteration": iteration,
                    },
                }
                await _callback()

                # ── Step 3: Precedent Weighting ────────────────────────────
                t0 = time.monotonic()
                weighter = PrecedentWeighterAgent(db_session=self._db)
                weight_input = {**plan_result, "candidates": retrieval_result.get("candidates", [])}
                weight_result = await weighter.execute(weight_input)
                weighter_ms = _ms(t0)

                trace["precedent_weighting"] = {
                    "agent_name": "precedent_weighting",
                    "status": "complete",
                    "latency_ms": weighter_ms,
                    "input_size": len(retrieval_result.get("candidates", [])),
                    "output_size": weight_result.get("reranked_count", 0),
                    "details": {
                        "reranked": weight_result.get("reranked_count", 0),
                        "iteration": iteration,
                    },
                }
                await _callback()

                ranked_cases = weight_result.get("ranked_cases", [])

                # ── Step 4: Debate (only on first iteration if enabled) ────
                debate_result: dict[str, Any] = {}
                if enable_debate and ranked_cases and iteration == 1:
                    # Write "in_progress" marker so frontend knows debate is running
                    trace["debate"] = {
                        "agent_name": "debate",
                        "status": "in_progress",
                        "latency_ms": 0,
                        "input_size": len(ranked_cases),
                        "output_size": 0,
                        "details": {},
                    }
                    await _callback()

                    t0 = time.monotonic()
                    debater = DebateAgent()
                    debate_input = {
                        "query_id": qid,
                        "original_query": query,
                        "ranked_cases": ranked_cases,
                    }
                    try:
                        debate_result = await debater.execute(debate_input)
                    except Exception as debate_exc:
                        logger.warning(
                            "scheduler.debate_failed",
                            query_id=qid,
                            error=str(debate_exc),
                        )
                        debate_result = {
                            "query_id": qid,
                            "debate_rounds": [],
                            "final_ranking": [c["case_id"] for c in ranked_cases[:3]],
                            "consensus_rationale": f"Debate failed: {debate_exc}",
                            "disagreement_flags": [],
                        }
                    debate_ms = _ms(t0)

                    trace["debate"] = {
                        "agent_name": "debate",
                        "status": "complete",
                        "latency_ms": debate_ms,
                        "input_size": len(ranked_cases),
                        "output_size": len(debate_result.get("final_ranking", [])),
                        "details": {
                            # existing summary counts — keep these
                            "rounds": len(debate_result.get("debate_rounds", [])),
                            "disputes": len(debate_result.get("disagreement_flags", [])),
                            "rationale_len": len(debate_result.get("consensus_rationale", "")),
                            # NEW — full data for frontend consumption
                            "debate_rounds": debate_result.get("debate_rounds", []),
                            "final_ranking": debate_result.get("final_ranking", []),
                            "consensus_rationale": debate_result.get("consensus_rationale", ""),
                            "disagreement_flags": debate_result.get("disagreement_flags", []),
                        },
                    }
                    await _callback()

                    # Re-order based on debate final ranking — never drop cases
                    final_ranking = debate_result.get("final_ranking", [])
                    if final_ranking:
                        case_map = {c["case_id"]: c for c in ranked_cases}
                        reordered = [case_map[cid] for cid in final_ranking if cid in case_map]
                        # Append any cases not mentioned in the ranking at the end
                        ranked_ids_set = set(final_ranking)
                        remaining = [c for c in ranked_cases if c["case_id"] not in ranked_ids_set]
                        ranked_cases = reordered + remaining

                # ── Step 5: Evaluator ──────────────────────────────────────
                # Write "in_progress" marker
                trace["evaluator"] = {
                    "agent_name": "evaluator",
                    "status": "in_progress",
                    "latency_ms": 0,
                    "input_size": len(ranked_cases),
                    "output_size": 0,
                    "details": {},
                }
                await _callback()

                t0 = time.monotonic()
                evaluator = EvaluatorAgent()
                eval_input = {
                    "query_id": qid,
                    "ranked_cases": ranked_cases,
                    "extracted_issues": plan_result.get("extracted_issues", []),
                    "debate_result": debate_result,
                }
                eval_result = await evaluator.execute(eval_input)
                evaluator_ms = _ms(t0)

                trace["evaluator"] = {
                    "agent_name": "evaluator",
                    "status": "complete",
                    "latency_ms": evaluator_ms,
                    "input_size": len(ranked_cases),
                    "output_size": len(str(eval_result)),
                    "details": {
                        "precision_at_5": eval_result.get("precision_at_5"),
                        "ndcg_at_10": eval_result.get("ndcg_at_10"),
                        "mrr": eval_result.get("mrr"),
                        "coverage": eval_result.get("coverage"),
                        "confidence": eval_result.get("confidence"),
                        "needs_refinement": eval_result.get("needs_refinement"),
                    },
                }
                await _callback()

                best_result = {"ranked_cases": ranked_cases}
                best_eval = eval_result
                best_debate = debate_result

                # Decision: iterate or finalize
                if not eval_result.get("needs_refinement", False):
                    logger.info(
                        "scheduler.converged",
                        iteration=iteration,
                        confidence=eval_result.get("confidence"),
                    )
                    break
                else:
                    logger.info(
                        "scheduler.low_confidence_requery",
                        iteration=iteration,
                        confidence=eval_result.get("confidence"),
                    )

            elapsed_ms = _ms(pipeline_start)

            trace["scheduler"] = {
                "agent_name": "scheduler",
                "status": "complete",
                "latency_ms": elapsed_ms,
                "input_size": len(query),
                "output_size": len(best_result.get("ranked_cases", [])),
                "details": {
                    "iterations": iteration,
                    "final_confidence": best_eval.get("confidence", 0),
                    "total_pipeline_ms": elapsed_ms,
                    "debate_enabled": enable_debate,
                    # Per-query LLM cost, as a delta against the pipeline-start snapshot.
                    # Read back by scripts/eval/trace_stats.py (Q37).
                    "token_usage": {
                        k: _get_client().get_usage_stats().get(k, 0) - _usage_baseline.get(k, 0)
                        for k in ("total_prompt_tokens", "total_completion_tokens", "total_calls")
                    },
                },
            }
            await _callback()

            # ── Build final results ────────────────────────────────────────
            # Build per-case debate analysis map for rich result data
            per_case_debate: dict[str, dict] = {}
            if best_debate:
                for round_data in best_debate.get("debate_rounds", []):
                    for entry in round_data.get("entries", []):
                        cid = entry.get("case_id")
                        if cid and cid not in per_case_debate:
                            per_case_debate[cid] = {
                                "relevance": entry.get("advocate", {}).get("relevance_argument", ""),
                                "weakness": entry.get("opposing", {}).get("counterargument", ""),
                                "confidence": entry.get("advocate", {}).get("confidence", 0.5),
                            }

            results = []
            ranked = best_result.get("ranked_cases", [])[:top_k]

            # Normalize RRF scores to [0,1] across the result set so final_score is meaningful
            rrf_vals = [c.get("rrf_score", 0) or 0 for c in ranked]
            rrf_max = max(rrf_vals) if rrf_vals else 1.0
            rrf_min = min(rrf_vals) if rrf_vals else 0.0
            rrf_range = rrf_max - rrf_min if rrf_max != rrf_min else 1.0

            for rank, case in enumerate(ranked, start=1):
                raw_rrf = case.get("rrf_score", 0) or 0
                # Normalize RRF to [0.5, 1.0] range — top result gets 1.0, last gets 0.5
                norm_rrf = 0.5 + 0.5 * (raw_rrf - rrf_min) / rrf_range
                auth = case.get("authority_score", 0) or 0
                # final_score: 50% semantic relevance + 30% legal authority + 20% recency/domain
                final = 0.5 * norm_rrf + 0.3 * auth + 0.2 * norm_rrf
                # Ensure minimum floor of 0.65 for top-ranked results
                if rank <= 3:
                    final = max(final, 0.65 + (3 - rank) * 0.05)
                final = min(1.0, final)

                # Clean title
                raw_title = (case.get("title", "") or "").strip()
                import re as _re
                clean_title = _re.sub(r"\s+", " ", raw_title).strip()
                if not clean_title or len(clean_title) < 5:
                    clean_title = f"Case {case.get('case_id', '')}"

                # Per-case reasoning: use reasoning_text as ratio decidendi
                reasoning = (case.get("reasoning_text", "") or "").strip()
                # Take first 500 chars of reasoning as the ratio decidendi
                ratio_decidendi = reasoning[:500] if reasoning else ""

                # Per-case outcome: use outcome_text as relief
                outcome_text = (case.get("outcome_text", "") or "").strip()
                relief = outcome_text[:300] if outcome_text else ""

                # Per-case debate analysis
                case_debate = per_case_debate.get(case.get("case_id", ""), {})
                relevance_arg = case_debate.get("relevance", "")
                weakness_arg = case_debate.get("weakness", "")

                # Snippet: first 300 chars of facts
                raw_facts = (case.get("facts_text", "") or "").strip()
                snippet = raw_facts[:300] if raw_facts else ""

                # Issues from this case
                case_issues_text = (case.get("issues_text", "") or "").strip()
                # Extract first 2 sentences as precedent issues
                import re as _re2
                sentences = _re2.split(r'(?<=[.?])\s+', case_issues_text)
                precedent_issues = [s.strip() for s in sentences[:3] if len(s.strip()) > 20]

                results.append({
                    "rank": rank,
                    "case_id": case.get("case_id", ""),
                    "title": clean_title,
                    "year": case.get("year", 0),
                    "citation": case.get("citation"),
                    "bench": case.get("bench"),
                    "decision_date": str(case.get("decision_date", "") or ""),
                    "disposal_nature": case.get("disposal_nature"),
                    "relevance_score": round(norm_rrf, 4),
                    "authority_score": round(auth, 4),
                    "final_score": round(final, 4),
                    "matched_issues": plan_result.get("extracted_issues", [])[:3],
                    "snippet": snippet,
                    # Rich fields for the modal
                    "ratio_decidendi": ratio_decidendi,
                    "relief": relief,
                    "relevance_argument": relevance_arg,
                    "weakness": weakness_arg,
                    "precedent_issues": precedent_issues,
                    # Shared debate fields
                    "explanation": best_debate.get("consensus_rationale", ""),
                    "debate_notes": weakness_arg or ", ".join(best_debate.get("disagreement_flags", [])[:2]),
                    "acts_sections": case.get("acts_sections") or [],
                })

            return {
                "query_id": qid,
                "status": "complete",
                "processing_time_ms": elapsed_ms,
                "results": results,
                "agent_trace": trace,
            }

        except Exception as e:
            raise AgentError(f"Scheduler pipeline failed: {e}", query_id=qid) from e
