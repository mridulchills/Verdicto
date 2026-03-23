import logging
from typing import Dict, Any

# Configure logging at the module level
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class AgentBase:
    """
    Base class for all agents in the multi-agent legal case analysis system.
    Provides a standardized async interface and utilities for building prompts, 
    parsing responses, and tracking outputs.
    """
    
    def __init__(self, agent_name: str):
        """
        Initialize the agent with a specific name.
        
        Args:
            agent_name (str): The name identifier for the agent.
        """
        self.agent_name = agent_name

    async def run(self, job_id: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main async execution method for the agent.
        
        Args:
            job_id (str): Unique identifier for the current analysis job.
            input_payload (dict): Structured input data required by the agent.
            
        Returns:
            dict: The structured execution result of the agent.
        """
        logger.info(f"[{self.agent_name}] Starting job {job_id}")
        
        prompt = self.build_prompt(input_payload)
        
        # Mock LLM API/inference invocation
        raw_response = self._mock_llm_call(prompt)
        
        result = self.parse_response(raw_response)
        self.log_output(job_id, result)
        
        return result

    def build_prompt(self, input_payload: Dict[str, Any]) -> str:
        """
        Construct the prompt or intermediate representation for the LLM.
        
        Args:
            input_payload (dict): The upstream context or data.
            
        Returns:
            str: The formatted prompt.
        """
        logger.debug(f"[{self.agent_name}] Building prompt from payload context.")
        return str(input_payload)

    def parse_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse raw the LLM response into a structured format (e.g., JSON dict).
        
        Args:
            response (Any): Data retuned by the LLM or external service.
            
        Returns:
            dict: The validated and parsed output.
        """
        logger.debug(f"[{self.agent_name}] Parsing unformatted response.")
        return {"parsed": response}

    def log_output(self, job_id: str, output: Dict[str, Any]) -> None:
        """
        Persist and/or log the final agent payload for observability.
        
        Args:
            job_id (str): Identifier tracing the execution flow.
            output (dict): Final structured response of the agent.
        """
        logger.info(f"[{self.agent_name}] Completed job {job_id} effectively. Output sample size: {len(str(output))} chars")

    def _mock_llm_call(self, prompt: str) -> str:
        """
        Placeholder demonstrating an external dependency call, resolving asynchronously.
        """
        return "MOCK_RESPONSE"
