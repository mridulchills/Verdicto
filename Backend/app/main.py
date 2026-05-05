"""
FastAPI application entrypoint.
Configures CORS, structured logging, lifespan events, and router includes.
"""
from __future__ import annotations
import logging
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import close_db
from app.core.faiss_index import get_faiss_index
from app.core.exceptions import IndexNotFoundError
from app.api.v1 import query as query_router
from app.api.v1 import cases as cases_router
from app.api.v1 import system as system_router

settings = get_settings()

# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level.upper())
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown events."""
    logger.info("app.startup", log_level=settings.log_level)

    # Load FAISS index (non-fatal if missing — allows API to start without index)
    try:
        faiss_idx = get_faiss_index()
        faiss_idx.load()
        logger.info("app.faiss_loaded", vectors=faiss_idx.total_vectors)
    except IndexNotFoundError as e:
        logger.warning("app.faiss_not_loaded", error=str(e))
    except Exception as e:
        logger.warning("app.faiss_load_error", error=str(e))

    yield

    # Shutdown
    await close_db()
    logger.info("app.shutdown")


app = FastAPI(
    title="Verdicto — Legal AI Multi-Agent System",
    description="AI-powered multi-agent platform for Indian Supreme Court judgment research.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router includes
app.include_router(query_router.router, prefix="/api/v1", tags=["Query"])
app.include_router(cases_router.router, prefix="/api/v1", tags=["Cases"])
app.include_router(system_router.router, prefix="/api/v1", tags=["System"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Verdicto Legal AI API", "version": "1.0.0", "docs": "/docs"}
