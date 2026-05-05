"""
Base agent class — all agents inherit from this.
Provides standardized logging, timing, and error handling.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    Each agent must set `name` and implement `run()`.
    The `execute()` wrapper adds logging, timing, and error handling.
    """

    name: str  # Must be set in subclass

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent. Must be idempotent for the same input.

        Args:
            input_data: Input dictionary including at minimum a `query_id` key.

        Returns:
            Result dictionary with agent-specific output.
        """
        ...

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Wrapper that adds logging, timing, and error handling.
        All callers should use `execute()` not `run()` directly.
        """
        start = time.monotonic()
        log = logger.bind(
            agent=self.name,
            query_id=input_data.get("query_id"),
            input_size=len(str(input_data)),
        )
        log.info("agent.start")

        try:
            result = await self.run(input_data)
            elapsed = (time.monotonic() - start) * 1000
            log.info(
                "agent.complete",
                latency_ms=round(elapsed, 2),
                output_size=len(str(result)),
            )
            return result
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            log.error(
                "agent.failed",
                error=str(e),
                latency_ms=round(elapsed, 2),
            )
            raise
