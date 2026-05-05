"""
Scheduler Agent — Orchestrates the entire multi-agent pipeline.
Decides whether to iterate based on evaluator confidence and debate disagreement.
Max 3 iterations (hard cap).
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

        try:
            # Step 1: Query Planner
            planner = QueryPlannerAgent()
            plan_result = await planner.execute({"query_id": qid, "query": query})
            trace["query_planner"] = {"agent_name": "query_planner", "status": "complete", "details": {"legal_domain": plan_result.get("legal_domain"), "issues_count": len(plan_result.get("extracted_issues", [])), "confidence": plan_result.get("confidence")}}
            if "trace_callback" in input_data: await input_data["trace_callback"](trace)

            best_result: dict[str, Any] = {}
            best_eval: dict[str, Any] = {}
            best_debate: dict[str, Any] = {}

            while iteration < settings.scheduler_max_iterations:
                iteration += 1
                logger.info("scheduler.iteration", iteration=iteration, query_id=qid)

                retriever = RetrieverAgent(db_session=self._db)
                retriever_input = {**plan_result, "filters": filters}
                retrieval_result = await retriever.execute(retriever_input)
                trace["retriever"] = {"agent_name": "retriever", "status": "complete", "details": {"faiss_hits": retrieval_result.get("faiss_hits", 0), "bm25_hits": retrieval_result.get("bm25_hits", 0), "after_rrf": retrieval_result.get("after_rrf", 0)}}
                if "trace_callback" in input_data: await input_data["trace_callback"](trace)

                # Step 3: Precedent Weighting
                weighter = PrecedentWeighterAgent(db_session=self._db)
                weight_input = {**plan_result, "candidates": retrieval_result.get("candidates", [])}
                weight_result = await weighter.execute(weight_input)
                trace["precedent_weighting"] = {"agent_name": "precedent_weighting", "status": "complete", "details": {"reranked": weight_result.get("reranked_count", 0)}}
                if "trace_callback" in input_data: await input_data["trace_callback"](trace)

                ranked_cases = weight_result.get("ranked_cases", [])

                # Step 4: Debate (if enabled)
                debate_result: dict[str, Any] = {}
                if enable_debate and ranked_cases:
                    debater = DebateAgent()
                    debate_input = {"query_id": qid, "original_query": query, "ranked_cases": ranked_cases}
                    debate_result = await debater.execute(debate_input)
                    trace["debate"] = {"agent_name": "debate", "status": "complete", "details": {"rounds": len(debate_result.get("debate_rounds", [])), "disputes": len(debate_result.get("disagreement_flags", []))}}
                    if "trace_callback" in input_data: await input_data["trace_callback"](trace)

                    # Re-order based on debate final ranking
                    final_ranking = debate_result.get("final_ranking", [])
                    if final_ranking:
                        case_map = {c["case_id"]: c for c in ranked_cases}
                        reordered = [case_map[cid] for cid in final_ranking if cid in case_map]
                        remaining = [c for c in ranked_cases if c["case_id"] not in final_ranking]
                        ranked_cases = reordered + remaining

                # Step 5: Evaluator
                evaluator = EvaluatorAgent()
                eval_input = {"query_id": qid, "ranked_cases": ranked_cases, "extracted_issues": plan_result.get("extracted_issues", []), "debate_result": debate_result}
                eval_result = await evaluator.execute(eval_input)
                trace["evaluator"] = {"agent_name": "evaluator", "status": "complete", "details": {"precision_at_5": eval_result.get("precision_at_5"), "ndcg_at_10": eval_result.get("ndcg_at_10"), "mrr": eval_result.get("mrr"), "confidence": eval_result.get("confidence")}}
                if "trace_callback" in input_data: await input_data["trace_callback"](trace)

                best_result = {"ranked_cases": ranked_cases}
                best_eval = eval_result
                best_debate = debate_result

                # Decision: iterate or finalize
                if not eval_result.get("needs_refinement", False):
                    logger.info("scheduler.converged", iteration=iteration, confidence=eval_result.get("confidence"))
                    break
                elif eval_result.get("confidence", 0) < settings.confidence_threshold:
                    logger.info("scheduler.low_confidence_requery", iteration=iteration)
                elif eval_result.get("disagreement_rate", 0) > 0.3:
                    logger.info("scheduler.high_disagreement", iteration=iteration)

            elapsed_ms = int((time.monotonic() - pipeline_start) * 1000)
            trace["scheduler"] = {"agent_name": "scheduler", "status": "complete", "details": {"iterations": iteration, "final_confidence": best_eval.get("confidence", 0)}}
            if "trace_callback" in input_data: await input_data["trace_callback"](trace)

            # Compute final scores
            results = []
            for rank, case in enumerate(best_result.get("ranked_cases", [])[:top_k], start=1):
                sem = case.get("rrf_score", 0) or case.get("faiss_score", 0)
                auth = case.get("authority_score", 0)
                struct = case.get("norm_factual", 0) if "norm_factual" in case else 0.5
                final = 0.5 * sem + 0.3 * auth + 0.2 * struct
                results.append({
                    "rank": rank, "case_id": case.get("case_id", ""), "title": case.get("title", ""), "year": case.get("year", 0),
                    "citation": case.get("citation"), "bench": case.get("bench"), "decision_date": str(case.get("decision_date", "")),
                    "disposal_nature": case.get("disposal_nature"), "relevance_score": round(sem, 4), "authority_score": round(auth, 4),
                    "final_score": round(min(1.0, final), 4), "matched_issues": plan_result.get("extracted_issues", [])[:3],
                    "snippet": (case.get("facts_text", "") or "")[:200], "explanation": best_debate.get("consensus_rationale", ""),
                    "debate_notes": ", ".join(best_debate.get("disagreement_flags", [])[:2]), "acts_sections": case.get("acts_sections", []),
                })

            return {"query_id": qid, "status": "complete", "processing_time_ms": elapsed_ms, "results": results, "agent_trace": trace}
        except Exception as e:
            raise AgentError(f"Scheduler pipeline failed: {e}", query_id=qid) from e
