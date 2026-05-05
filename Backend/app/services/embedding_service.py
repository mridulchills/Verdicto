"""
Shared service for generating embeddings using either local SentenceTransformers or Gemini API.
"""
from __future__ import annotations
import asyncio
import structlog
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

_LOCAL_MODEL = None

async def get_embedding(text: str) -> list[float]:
    """Generate embedding using configured method."""
    if settings.use_local_embeddings:
        global _LOCAL_MODEL
        from sentence_transformers import SentenceTransformer
        if _LOCAL_MODEL is None:
            logger.info("embedding.loading_local_model", model=settings.embedding_model_local)
            _LOCAL_MODEL = SentenceTransformer(settings.embedding_model_local)
        
        # Truncate for local models which usually have 512 token limit
        # 1000 chars is roughly 250-300 tokens
        embedding = await asyncio.to_thread(_LOCAL_MODEL.encode, text[:1000], convert_to_numpy=True)
        return embedding.tolist()
    else:
        from app.core.gemini_client import get_gemini_client
        client = get_gemini_client()
        return await client.generate_query_embedding(text)
