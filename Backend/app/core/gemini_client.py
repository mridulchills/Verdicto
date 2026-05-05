"""
Centralized Gemini API client.
This is the ONLY place where google.generativeai is imported.
All agents call this client — never the SDK directly.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TypeVar

import google.generativeai as genai
import structlog
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.exceptions import (
    EmbeddingError,
    GeminiAPIError,
    GeminiCircuitOpenError,
)

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)

settings = get_settings()


class _UsageStats:
    """Track token usage across calls."""

    def __init__(self) -> None:
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_calls: int = 0

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_calls += 1

    def to_dict(self) -> dict[str, int]:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_calls": self.total_calls,
        }


class GeminiClient:
    """
    Centralized wrapper around the Google Generative AI SDK.
    Features:
    - Retry with exponential backoff (max 3 retries)
    - Circuit breaker (3 consecutive failures → open)
    - Token usage tracking
    """

    def __init__(self) -> None:
        genai.configure(api_key=settings.gemini_api_key)
        self._usage = _UsageStats()
        self._consecutive_failures: int = 0
        self._circuit_open: bool = False
        self._flash_model = genai.GenerativeModel(settings.gemini_model_flash)
        self._pro_model = genai.GenerativeModel(settings.gemini_model_pro)
        self._embedding_model_name = settings.gemini_embedding_model

    def _check_circuit(self) -> None:
        if self._circuit_open:
            raise GeminiCircuitOpenError(
                "Gemini circuit breaker is open after 3 consecutive failures. "
                "Skipping to fallback."
            )

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open = False

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= 3:
            self._circuit_open = True
            logger.error(
                "gemini.circuit_open",
                consecutive_failures=self._consecutive_failures,
            )

    def get_usage_stats(self) -> dict[str, int]:
        return self._usage.to_dict()

    def reset_circuit(self) -> None:
        """Allow manual circuit reset after recovery."""
        self._circuit_open = False
        self._consecutive_failures = 0

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def generate_text(
        self,
        prompt: str,
        *,
        model: str = "flash",
        response_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        """
        Generate text from Gemini. Returns parsed text response.

        Args:
            prompt: The prompt string.
            model: "flash" or "pro".
            response_schema: Optional JSON schema for structured output.
            temperature: Sampling temperature.
        """
        self._check_circuit()
        log = logger.bind(model=model, prompt_len=len(prompt))
        log.info("gemini.generate_text.start")

        start = time.monotonic()
        try:
            genai_model = self._pro_model if model == "pro" else self._flash_model

            generation_config: dict[str, Any] = {"temperature": temperature}
            if response_schema is not None:
                generation_config["response_mime_type"] = "application/json"
                generation_config["response_schema"] = response_schema

            response = await asyncio.to_thread(
                genai_model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(**generation_config),
            )

            # Extract usage metadata
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                self._usage.record(
                    prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", 0),
                    completion_tokens=getattr(response.usage_metadata, "candidates_token_count", 0),
                )

            result_text = response.text
            elapsed = (time.monotonic() - start) * 1000
            log.info("gemini.generate_text.complete", latency_ms=round(elapsed, 2), output_len=len(result_text))

            self._record_success()
            return result_text

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self._record_failure()
            log.error("gemini.generate_text.failed", error=str(exc), latency_ms=round(elapsed, 2))
            raise GeminiAPIError(f"Gemini text generation failed: {exc}") from exc

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text using Gemini Embedding API.
        Returns a list of floats (the embedding vector).
        """
        self._check_circuit()
        log = logger.bind(text_len=len(text))
        log.info("gemini.generate_embedding.start")

        start = time.monotonic()
        try:
            result = await asyncio.to_thread(
                genai.embed_content,
                model=f"models/{self._embedding_model_name}",
                content=text,
                task_type="retrieval_document",
            )

            embedding: list[float] = result["embedding"]
            elapsed = (time.monotonic() - start) * 1000
            log.info(
                "gemini.generate_embedding.complete",
                latency_ms=round(elapsed, 2),
                dim=len(embedding),
            )

            self._record_success()
            return embedding

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self._record_failure()
            log.error("gemini.generate_embedding.failed", error=str(exc), latency_ms=round(elapsed, 2))
            raise EmbeddingError(f"Embedding generation failed: {exc}") from exc

    async def generate_query_embedding(self, text: str) -> list[float]:
        """Generate an embedding optimized for query retrieval."""
        self._check_circuit()
        log = logger.bind(text_len=len(text))

        start = time.monotonic()
        try:
            result = await asyncio.to_thread(
                genai.embed_content,
                model=f"models/{self._embedding_model_name}",
                content=text,
                task_type="retrieval_query",
            )

            embedding: list[float] = result["embedding"]
            elapsed = (time.monotonic() - start) * 1000
            log.info(
                "gemini.generate_query_embedding.complete",
                latency_ms=round(elapsed, 2),
                dim=len(embedding),
            )

            self._record_success()
            return embedding

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self._record_failure()
            log.error("gemini.generate_query_embedding.failed", error=str(exc))
            raise EmbeddingError(f"Query embedding generation failed: {exc}") from exc

    async def generate_structured(
        self,
        prompt: str,
        schema_class: type[T],
        *,
        model: str = "flash",
        temperature: float = 0.1,
    ) -> T:
        """
        Generate structured JSON output and validate against a Pydantic model.
        Uses response_mime_type: "application/json".
        """
        import json as _json

        raw_text = await self.generate_text(
            prompt,
            model=model,
            temperature=temperature,
            response_schema=None,  # We'll parse manually for broader compatibility
        )

        try:
            parsed = _json.loads(raw_text)
            return schema_class.model_validate(parsed)
        except (_json.JSONDecodeError, Exception) as exc:
            logger.error(
                "gemini.structured_parse_failed",
                error=str(exc),
                raw_text_len=len(raw_text),
            )
            raise GeminiAPIError(
                f"Failed to parse Gemini response as {schema_class.__name__}: {exc}"
            ) from exc


# Module-level singleton
_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get or create the singleton Gemini client."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
