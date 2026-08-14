"""
Scheduler Agent — orchestrates the pipeline and decides what to re-run.

On a low-confidence pass it does NOT re-run everything. The evaluator's confidence is a
weighted sum of independent signals, each owned by exactly one agent; the scheduler
re-runs the owner of the signal with the largest headroom, plus everything downstream
of it. See _SIGNAL_OWNER below and app/agents/evaluator.py for the decomposition.

Up to min(settings.scheduler_max_iterations, 5) passes: the initial one plus at most
one attempt at each of the four remedies.
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
from app.agents.evaluator import SIGNAL_WEIGHTS, EvaluatorAgent
from app.core.config import get_settings
from app.core.exceptions import AgentError

logger = structlog.get_logger()
settings = get_settings()


def _ms(start: float) -> int:
    """Return elapsed milliseconds since start."""
    return int((time.monotonic() - start) * 1000)


# ── Adaptive re-scheduling ───────────────────────────────────────────────────
# Re-running everything on a low-confidence pass is both wasteful and a no-op: the
# pipeline is deterministic, so unchanged input re-derives identical output.
#
# Each confidence signal is owned by exactly one agent, so a deficient signal names the
# agent that can repair it. This mapping is the whole routing policy — it is not a
# heuristic bolted on top of the evaluator, it IS the evaluator's decomposition.
_SIGNAL_OWNER = {
    "channel_agreement": "rewiden",    # the channels disagree -> the query is wrong for them
    "issue_coverage": "replan",        # the issues are ungrounded -> the question is wrong
    "score_dispersion": "reweight",    # the ranking is flat     -> the weighting is wrong
    "top_margin": "reweight",          # no clear winner         -> the weighting is wrong
    "debate_consensus": "redebate",    # the advocates disagreed -> re-argue it
}
# What each action re-runs, in pipeline order. The scheduler runs the named agent
# and then everything downstream of it — that is the "pass its work to the next
# agent" part; a re-ranked list still has to be re-evaluated to score the change.
_DOWNSTREAM = {
    "replan":   ("query_planner", "retriever", "precedent_weighting", "evaluator"),
    "rewiden":  ("retriever", "precedent_weighting", "evaluator"),
    "reweight": ("precedent_weighting", "evaluator"),
    "redebate": ("debate", "evaluator"),
}
# Ordering is wrong -> trust query-alignment over global fame. Renormalised to 1.0.
_REWEIGHT_OVERRIDES = {
    "factual_alignment": 0.40,
    "citation_count": 0.15,
    "bench_size": 0.15,
    "recency": 0.15,
    "domain_match": 0.15,
}


def _diagnose(eval_result: dict[str, Any], tried: set[str],
              debate_enabled: bool) -> tuple[str | None, str]:
    """Pick the one agent most likely to raise confidence. Returns (action, reason).

    Chooses by *headroom* — weight x (1 - value) — not by raw value, because a weak
    signal carrying little weight is worth less than a middling one carrying a lot.
    Signals the evaluator could not measure are skipped: there is no evidence they are
    deficient, so re-running their owner would be guesswork.

    An action is only ever attempted once per query. If a remedy did not help, the next
    pass moves to the next-best one rather than repeating a known no-op.
    """
    signals = eval_result.get("signals", {}) or {}
    headroom: dict[str, float] = {}
    for signal, weight in SIGNAL_WEIGHTS.items():
        value = signals.get(signal)
        if value is None:               # not measurable this pass — no evidence either way
            continue
        headroom[signal] = weight * (1.0 - float(value))

    for signal, gap in sorted(headroom.items(), key=lambda kv: kv[1], reverse=True):
        action = _SIGNAL_OWNER[signal]
        if action in tried:
            continue
        if action == "redebate" and not debate_enabled:
            continue
        if gap <= 0.0:                  # signal is already saturated; nothing to win
            continue
        return action, (f"{signal}={float(signals[signal]):.3f} leaves the largest "
                        f"confidence headroom ({gap:.3f})")

    return None, "no remedy left with measurable headroom"


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

        # Up to 5 passes: the initial one plus at most one attempt at each of the four
        # remedies. There is no point going beyond that — every remedy is tried once.
        max_iter = min(settings.scheduler_max_iterations, 5)

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
            best_confidence = -1.0

            # Adaptive-scheduling state, carried across iterations.
            retrieval_result: dict[str, Any] = {}
            weight_result: dict[str, Any] = {}
            ranked_cases: list[dict[str, Any]] = []
            debate_result: dict[str, Any] = {}
            tried_actions: set[str] = set()
            variant_index = 0
            weight_overrides: dict[str, float] = {}
            history: list[dict[str, Any]] = []
            action, reason = "initial", "first pass"

            while iteration < max_iter:
                iteration += 1
                # Which agents run this pass. The first pass is the full pipeline;
                # every later pass runs only the diagnosed agent and its downstream.
                stages = (("retriever", "precedent_weighting", "debate", "evaluator")
                          if iteration == 1 else _DOWNSTREAM[action])
                logger.info("scheduler.iteration", iteration=iteration, query_id=qid,
                            action=action, reason=reason, stages=list(stages))

                # ── Step 1b: Query Planner (re-plan only) ──────────────────
                if "query_planner" in stages:
                    t0 = time.monotonic()
                    missing = plan_result.get("extracted_issues", [])[:3]
                    replan_query = (
                        f"{query}\n\n[Refine: an earlier search returned cases that did "
                        f"not address these issues: {'; '.join(missing)}. Produce broader "
                        f"alternative phrasings that would reach them.]"
                    )
                    plan_result = await QueryPlannerAgent().execute(
                        {"query_id": qid, "query": replan_query})
                    trace["query_planner"] = {
                        "agent_name": "query_planner",
                        "status": "complete",
                        "latency_ms": _ms(t0),
                        "input_size": len(replan_query),
                        "output_size": len(str(plan_result)),
                        "details": {
                            "legal_domain": plan_result.get("legal_domain"),
                            "issues_count": len(plan_result.get("extracted_issues", [])),
                            "confidence": plan_result.get("confidence"),
                            "reformulated_queries": len(plan_result.get("reformulated_queries", [])),
                            "iteration": iteration,
                            "replanned": True,
                        },
                    }
                    await _callback()

                # ── Step 2: Retriever ──────────────────────────────────────
                if "retriever" in stages:
                    t0 = time.monotonic()
                    retriever = RetrieverAgent(db_session=self._db)
                    # A re-retrieval must differ from the one that just failed, or it
                    # re-derives the same candidates: advance to the next reformulation
                    # and widen the pool.
                    if iteration > 1:
                        variant_index += 1
                    retriever_input = {
                        **plan_result,
                        "filters": filters,
                        "variant_index": variant_index,
                        "top_k_override": settings.max_query_k * (1 + variant_index),
                    }
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
                            "variant_index": retrieval_result.get("variant_index", 0),
                            "top_k_used": retrieval_result.get("top_k_used"),
                        },
                    }
                    await _callback()

                # ── Step 3: Precedent Weighting ────────────────────────────
                if "precedent_weighting" in stages:
                    t0 = time.monotonic()
                    weighter = PrecedentWeighterAgent(db_session=self._db)
                    weight_input = {**plan_result,
                                    "candidates": retrieval_result.get("candidates", []),
                                    "weight_overrides": weight_overrides}
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
                            "reweighted": bool(weight_overrides),
                        },
                    }
                    await _callback()

                    ranked_cases = weight_result.get("ranked_cases", [])

                # ── Step 4: Debate ─────────────────────────────────────────
                # Runs on the first pass, and again only if the evaluator reports the
                # advocates disagreed (action == "redebate").
                if "debate" in stages and enable_debate and ranked_cases:
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
                    # Per-channel scores survive RRF, and channel agreement is the
                    # heaviest confidence signal — the evaluator needs the raw pool.
                    "candidates": retrieval_result.get("candidates", []),
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
                        **(eval_result.get("signals") or {}),
                        "confidence": eval_result.get("confidence"),
                        "needs_refinement": eval_result.get("needs_refinement"),
                        "signals_missing": eval_result.get("signals_missing", []),
                    },
                }
                await _callback()

                confidence = float(eval_result.get("confidence", 0.0) or 0.0)
                history.append({
                    "iteration": iteration,
                    "action": action,
                    "reason": reason,
                    "stages_run": list(stages),
                    "confidence": confidence,
                    "signals": eval_result.get("signals") or {},
                })

                # Keep the BEST pass, not the last one. A remedy can make things
                # worse, and when it does we must not ship the degraded ranking.
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_result = {"ranked_cases": ranked_cases}
                    best_eval = eval_result
                    best_debate = debate_result

                # Decision: iterate or finalize
                if not eval_result.get("needs_refinement", False):
                    logger.info("scheduler.converged", iteration=iteration,
                                confidence=confidence)
                    break

                if iteration >= max_iter:
                    logger.info("scheduler.cap_reached", iteration=iteration,
                                confidence=confidence)
                    break

                # Diagnose which single agent to re-run next.
                if action != "initial":
                    tried_actions.add(action)
                action, reason = _diagnose(eval_result, tried_actions, enable_debate)
                if action is None:
                    logger.info("scheduler.remedies_exhausted", iteration=iteration,
                                confidence=confidence, tried=sorted(tried_actions))
                    break

                # Configure the remedy before the next pass runs it.
                if action == "reweight":
                    weight_overrides = dict(_REWEIGHT_OVERRIDES)
                logger.info("scheduler.requery", iteration=iteration,
                            confidence=confidence, next_action=action, reason=reason)

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
                    # Adaptive-scheduling record (Q27/Q28): which agent was re-run on
                    # each pass, why, and what it did to confidence.
                    "iteration_history": history,
                    "actions_taken": [h["action"] for h in history],
                    "confidence_trajectory": [h["confidence"] for h in history],
                    "confidence_gain": (round(history[-1]["confidence"] - history[0]["confidence"], 4)
                                        if len(history) > 1 else 0.0),
                    "best_confidence": round(best_confidence, 4) if best_confidence >= 0 else 0.0,
                    "converged": bool(best_eval and not best_eval.get("needs_refinement", False)),
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
