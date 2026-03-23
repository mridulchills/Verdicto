import logging
import asyncio
from typing import Dict, Any

from .planner import PlannerAgent
from .retriever import RetrieverAgent
from .similarity import SimilarityAgent
from .mapping import MappingAgent
from .debate import DebateAgent
from .evaluator import EvaluatorAgent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class SchedulerAgent:
    """
    SchedulerAgent represents the central orchestration node of the autonomous workflow.
    It manages iteration boundaries, coordinates downstream agent inputs, and resolves
    complex rule-based lifecycle branches via its internal routing state map.
    """
    
    def __init__(self):
        self.agent_name = "SchedulerAgent"
        self.max_iterations = 3
        
        # Instantiate execution agents.
        self.planner = PlannerAgent()
        self.retriever = RetrieverAgent()
        self.similarity = SimilarityAgent()
        self.mapping = MappingAgent()
        self.debate = DebateAgent()
        self.evaluator = EvaluatorAgent()

    def decide_next_action(self, state: Dict[str, Any]) -> str:
        """
        Rule Engine validating the transition lifecycle.
        
        Args:
            state (dict): The active parameters of the job trace.
            
        Returns:
            str: Action mapping representing next state.
        """
        # Hard limits break cyclical dependencies unconditionally.
        if state["iteration"] > self.max_iterations:
            return "finalize"

        # Edge case: Insufficient precedents fetched
        if state["num_cases"] < 3:
            return "retrieve_more"

        # Evaluator flagged a refinement priority
        if state.get("disagreement", False) or state.get("score", 1.0) < 0.75:
            # During first cycle context is usually an issue -> re-query
            if state["iteration"] == 1:
                return "rerun_similarity"
            # In deeper cycles re-simulate debate to fix adversarial imbalances
            return "start_debate"

        # Acceptable criteria met early
        if state["iteration"] > 1 and state.get("score", 0.0) >= 0.75:
            return "finalize"

        # Default standard execution path
        return "start_debate"

    async def run(self, job_id: str, initial_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Robust system execution map that coordinates cross-agent RPC logic.
        
        Args:
            job_id (str): Reference GUID trace.
            initial_payload (dict): Source prompt / Case file payload.
            
        Returns:
            dict: Master response encompassing the entirety of analysis layers.
        """
        logger.info(f"[{self.agent_name}] Booting master scheduler loops for trace: {job_id}")
        
        # Mutable environment tracking for the state engine
        state = {
            "iteration": 1,
            "score": 0.0,
            "num_cases": 0,
            "disagreement": False
        }
        
        # Step 1: Baseline Structural generation
        plan_result = await self.planner.run(job_id, initial_payload)
        
        # Step 2: Semantic Document Retreival
        retrieval_result = await self.retriever.run(job_id, {"top_k": 3, **plan_result})
        state["num_cases"] = len(retrieval_result.get("candidates", []))
        
        # --- Lifecycle Iteration Engine ---
        final_result = {}
        
        while state["iteration"] <= self.max_iterations:
            logger.info(f"[{self.agent_name}] Processing Iteration Vector {state['iteration']}")
            
            action = self.decide_next_action(state)
            logger.info(f"[{self.agent_name}] Strategy determined: [ {action.upper()} ]")
            
            if action == "retrieve_more":
                retrieval_result = await self.retriever.run(job_id, {"top_k": 5, **plan_result})
                state["num_cases"] = len(retrieval_result.get("candidates", []))
                state["iteration"] += 1
                continue
                
            elif action == "rerun_similarity":
                # Inject a deeper recalculation pipeline
                sim_result = await self.similarity.run(job_id, retrieval_result)
                state["iteration"] += 1
                continue
                
            elif action == "start_debate":
                # Primary logic generation pathing
                sim_result = await self.similarity.run(job_id, retrieval_result)
                map_result = await self.mapping.run(job_id, sim_result)
                debate_result = await self.debate.run(job_id, map_result)
                
                # Confidence verification mapping
                eval_result = await self.evaluator.run(job_id, debate_result)
                state["score"] = eval_result.get("confidence", 0.0)
                state["disagreement"] = eval_result.get("needs_refinement", False)
                
                # Snapshot global results mapping
                final_result = {
                    "job_id": job_id,
                    "plan": plan_result,
                    "mapping": map_result,
                    "debate": debate_result,
                    "evaluation": eval_result,
                    "system_metrics": state.copy()
                }
                
                if not state["disagreement"]:
                    action = "finalize"
                    logger.info(f"[{self.agent_name}] Confidence bounds aligned. Emitting finalize transition.")
                    break
                    
            elif action == "finalize":
                break
                
            state["iteration"] += 1

        logger.info(f"[{self.agent_name}] Halting execution for orchestration sequence {job_id}")
        return final_result
