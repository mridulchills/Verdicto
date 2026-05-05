"""
Custom exception hierarchy for the Verdicto backend.
Every FastAPI endpoint catches these and returns consistent error JSON.
"""

from __future__ import annotations


class VerdictoError(Exception):
    """Base exception for all Verdicto errors."""

    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, query_id: str | None = None) -> None:
        self.message = message
        self.query_id = query_id
        super().__init__(message)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "message": self.message,
            "query_id": self.query_id,
        }


class AgentError(VerdictoError):
    """Raised when an agent fails during execution."""

    code = "AGENT_FAILED"


class DatabaseError(VerdictoError):
    """Raised for database connectivity or query failures."""

    code = "DATABASE_ERROR"


class EmbeddingError(VerdictoError):
    """Raised when embedding generation fails."""

    code = "EMBEDDING_ERROR"


class IndexNotFoundError(VerdictoError):
    """Raised when the FAISS index file is not available."""

    code = "INDEX_NOT_FOUND"


class GeminiCircuitOpenError(VerdictoError):
    """Raised when the Gemini circuit breaker is open after consecutive failures."""

    code = "GEMINI_CIRCUIT_OPEN"


class GeminiAPIError(VerdictoError):
    """Raised when a Gemini API call fails after retries."""

    code = "GEMINI_API_ERROR"


class QueryValidationError(VerdictoError):
    """Raised when query input validation fails."""

    code = "VALIDATION_ERROR"


class CaseNotFoundError(VerdictoError):
    """Raised when a requested case doesn't exist in the database."""

    code = "CASE_NOT_FOUND"
