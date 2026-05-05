"""
Application configuration via Pydantic BaseSettings.
All environment variables are defined here — the app fails loudly if required ones are missing.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration. Reads from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Required ──────────────────────────────────────────────────────────
    gemini_api_key: str

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://verdicto:verdicto_secret@localhost:5432/verdicto"
    db_pool_min: int = 5
    db_pool_max: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── FAISS ─────────────────────────────────────────────────────────────
    faiss_index_path: str = "./data/index/cases.index"
    faiss_mapping_path: str = "./data/index/cases_mapping.json"

    # ── Data ──────────────────────────────────────────────────────────────
    processed_text_dir: str = "./data/processed/"
    raw_data_dir: str = "./data/raw/"

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── CORS ──────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    # ── Search / Retrieval ────────────────────────────────────────────────
    max_query_k: int = 50
    bm25_top_k: int = 50
    final_candidates: int = 50

    # ── Agent Configuration ───────────────────────────────────────────────
    debate_max_rounds: int = 3
    scheduler_max_iterations: int = 3
    confidence_threshold: float = 0.75

    # ── Gemini Models & Rate Limits ───────────────────────────────────────
    gemini_rate_limit_rpm: int = 60
    gemini_model_flash: str = "gemini-1.5-flash"
    gemini_model_pro: str = "gemini-1.5-pro"
    
    # ── Embedding Models ──────────────────────────────────────────────────
    use_local_embeddings: bool = True
    embedding_model_local: str = "all-MiniLM-L6-v2"
    gemini_embedding_model: str = "text-embedding-004"

    # ── API Server ────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000


def get_settings() -> Settings:
    """Singleton-like factory for settings. Raises immediately if config is invalid."""
    return Settings()  # type: ignore[call-arg]
