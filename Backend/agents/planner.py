import logging
from typing import Dict, Any, List
from .base import AgentBase

logger = logging.getLogger(__name__)

class PlannerAgent(AgentBase):
    """
    PlannerAgent takes unstructured or raw case details and systematically
    distills them into key facts, binding legal issues, and the execution trace (tasks)
    required for full legal analysis.
    """
    
    def __init__(self):
        super().__init__(agent_name="PlannerAgent")

    def build_prompt(self, input_payload: Dict[str, Any]) -> str:
        """
        Creates a structured prompt mapping the objective to LLM capabilities.
        """
        case_text = input_payload.get("case_text", "No context provided.")
        return f"""
        System Instruction: Act as an expert legal planner.
        Constraint: Provide purely objective, highly synthesized analytical extractions.
        
        Analyze the following case log:
        {case_text[:1000]}
        
        Please extract exactly:
        1. Material facts
        2. Legal issues of consequence
        3. Subtasks resolving the matter progressively.
        """

    def parse_response(self, response: Any) -> Dict[str, Any]:
        """
        Enforce schema and transform the raw string extraction.
        In a production scenario, use Instructor or Pydantic to enforce JSON validation.
        """
        return {
            "facts": [
                "The plaintiff claims a direct breach of multi-year contract.",
                "The defendant asserts non-liability due to unforeseeable supply restrictions."
            ],
            "issues": [
                "Does an international supply shock invoke force majeure?",
                "Did the delayed communication constitute secondary liability?"
            ],
            "subtasks": [
                "Analyze factual similarity against contract jurisdiction.",
                "Extract top 5 preceding judgments on foreseeability.",
                "Perform structural mapping of the core issues."
            ]
        }

    async def run(self, job_id: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the case dissection flow asynchronously.
        """
        logger.info(f"[{self.agent_name}] Analyzing initial context for job {job_id}")
        prompt = self.build_prompt(input_payload)
        
        # Async invocation placeholder
        mock_response = self._mock_llm_call(prompt)
        parsed_result = self.parse_response(mock_response)
        
        self.log_output(job_id, parsed_result)
        return parsed_result
