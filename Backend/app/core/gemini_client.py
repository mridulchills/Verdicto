"""
Centralized Client for Ollama (Replacing Gemini).
All agents call this client.
"""

from __future__ import annotations

import asyncio
import time
import json
import httpx
from typing import Any, TypeVar

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

# Shared persistent httpx client — avoids per-call connection overhead
# and allows connection reuse across concurrent debate calls.
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        # No timeout here — callers use asyncio.wait_for for deadline control
        _http_client = httpx.AsyncClient(timeout=None)
    return _http_client


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
    Centralized wrapper around Ollama (API compatible with original GeminiClient).
    Features:
    - Retry with exponential backoff on API errors only (not timeouts/cancellations)
    - Circuit breaker (3 consecutive failures → open)
    - Token usage tracking
    """

    def __init__(self) -> None:
        self._usage = _UsageStats()
        self._consecutive_failures: int = 0
        self._circuit_open: bool = False

    def _check_circuit(self) -> None:
        if self._circuit_open:
            raise GeminiCircuitOpenError(
                "Circuit breaker is open after 3 consecutive failures. "
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
                "ollama.circuit_open",
                consecutive_failures=self._consecutive_failures,
            )

    def get_usage_stats(self) -> dict[str, int]:
        return self._usage.to_dict()

    def reset_circuit(self) -> None:
        """Allow manual circuit reset after recovery."""
        self._circuit_open = False
        self._consecutive_failures = 0

    # Only retry on GeminiAPIError — never on TimeoutError or CancelledError
    @retry(
        retry=retry_if_exception_type(GeminiAPIError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
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
        Generate text from Ollama. Returns parsed text response.
        Callers should wrap with asyncio.wait_for() for deadline control.
        """
        self._check_circuit()
        log = logger.bind(model=settings.ollama_model, prompt_len=len(prompt))
        log.info("ollama.generate_text.start")

        start = time.monotonic()
        try:
            payload = {
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 1024,   # cap output tokens — prevents runaway generation
                },
            }
            if response_schema is not None:
                payload["format"] = "json"

            http = _get_http_client()
            response = await http.post(
                f"{settings.ollama_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            result_text = result.get("response", "")

            # Strip <think>...</think> blocks (deepseek-r1 reasoning traces)
            import re as _re
            result_text = _re.sub(r"<think>.*?</think>", "", result_text, flags=_re.DOTALL).strip()

            # Extract usage
            eval_count = result.get("eval_count", 0)
            prompt_eval_count = result.get("prompt_eval_count", 0)
            self._usage.record(prompt_tokens=prompt_eval_count, completion_tokens=eval_count)

            elapsed = (time.monotonic() - start) * 1000
            log.info(
                "ollama.generate_text.complete",
                latency_ms=round(elapsed, 2),
                output_len=len(result_text),
            )

            self._record_success()
            return result_text

        except (asyncio.CancelledError, asyncio.TimeoutError):
            # Never retry on cancellation/timeout — propagate immediately
            elapsed = (time.monotonic() - start) * 1000
            log.warning("ollama.generate_text.cancelled", latency_ms=round(elapsed, 2))
            raise

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self._record_failure()
            log.error("ollama.generate_text.failed", error=str(exc), latency_ms=round(elapsed, 2))
            raise GeminiAPIError(f"Ollama text generation failed: {exc}") from exc

    # Only retry on EmbeddingError — never on TimeoutError or CancelledError
    @retry(
        retry=retry_if_exception_type(EmbeddingError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text using Ollama."""
        self._check_circuit()
        log = logger.bind(text_len=len(text))
        log.info("ollama.generate_embedding.start")

        start = time.monotonic()
        try:
            payload = {
                "model": "nomic-embed-text:latest",
                "prompt": text,
            }
            http = _get_http_client()
            response = await http.post(
                f"{settings.ollama_url}/api/embeddings",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            embedding: list[float] = result.get("embedding", [])
            elapsed = (time.monotonic() - start) * 1000
            log.info(
                "ollama.generate_embedding.complete",
                latency_ms=round(elapsed, 2),
                dim=len(embedding),
            )

            self._record_success()
            return embedding

        except (asyncio.CancelledError, asyncio.TimeoutError):
            raise

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self._record_failure()
            log.error("ollama.generate_embedding.failed", error=str(exc), latency_ms=round(elapsed, 2))
            raise EmbeddingError(f"Ollama Embedding generation failed: {exc}") from exc

    async def generate_query_embedding(self, text: str) -> list[float]:
        """Generate an embedding optimized for query retrieval."""
        return await self.generate_embedding(text)

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
        """
        raw_text = await self.generate_text(
            prompt,
            model=model,
            temperature=temperature,
            response_schema=schema_class.model_json_schema(),
        )

        try:
            parsed = json.loads(raw_text)
            return schema_class.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as exc:
            logger.error(
                "ollama.structured_parse_failed",
                error=str(exc),
                raw_text_len=len(raw_text),
            )
            try:
                import re
                cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
                try:
                    parsed = json.loads(cleaned)
                    return schema_class.model_validate(parsed)
                except Exception:
                    pass
                match = re.search(r"```(?:json)?\n?(.*?)\n?```", cleaned, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(1))
                    return schema_class.model_validate(parsed)
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    return schema_class.model_validate(parsed)
            except Exception:
                pass

            raise GeminiAPIError(
                f"Failed to parse Ollama response as {schema_class.__name__}: {exc}"
            ) from exc


_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Get or create the singleton Ollama client."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client