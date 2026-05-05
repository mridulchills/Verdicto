"""
POST /api/v1/query — Submit a legal query for multi-agent analysis.
GET /api/v1/query/{query_id}/status — Poll query status.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Any
import structlog
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.scheduler import SchedulerAgent
from app.core.database import get_db, async_session_factory
from app.core.exceptions import AgentError, VerdictoError
from app.models.case import QueryRecord
from app.models.query import (ErrorResponse, QueryRequest, QueryResponse, QueryStatusResponse, QueryListItem, QueryListResponse)
from sqlalchemy import select

logger = structlog.get_logger()
router = APIRouter()


async def run_pipeline_background(query_id: str, query: str, filters: dict, options: dict):
    log = logger.bind(query_id=query_id)
    try:
        async with async_session_factory() as db:
            async def trace_update_callback(trace_data):
                record = await db.get(QueryRecord, uuid.UUID(query_id))
                if record:
                    record.agent_trace = json.dumps(trace_data, default=str)
                    await db.commit()
            
            scheduler = SchedulerAgent(db_session=db)
            result = await scheduler.execute({
                "query_id": query_id, "query": query,
                "filters": filters, "options": options,
                "trace_callback": trace_update_callback
            })

            record = await db.get(QueryRecord, uuid.UUID(query_id))
            if record:
                record.status = "complete"
                record.result = json.dumps(result.get("results", []), default=str)
                record.agent_trace = json.dumps(result.get("agent_trace", {}), default=str)
                record.processing_time_ms = result.get("processing_time_ms", 0)
                record.completed_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception as e:
        log.error("background_pipeline.failed", error=str(e))
        async with async_session_factory() as db:
            record = await db.get(QueryRecord, uuid.UUID(query_id))
            if record:
                record.status = "failed"
                await db.commit()

@router.post("/query", response_model=QueryResponse, responses={500: {"model": ErrorResponse}})
async def submit_query(request: QueryRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> QueryResponse:
    """Submit a legal query for multi-agent analysis."""
    query_id = str(uuid.uuid4())
    log = logger.bind(query_id=query_id)
    log.info("api.query.received", query_len=len(request.query))

    # Create query record
    record = QueryRecord(id=uuid.UUID(query_id), query_text=request.query, status="processing",
        filters=json.dumps(request.filters.model_dump()), options=json.dumps(request.options.model_dump()))
    db.add(record)
    await db.commit()
    
    background_tasks.add_task(run_pipeline_background, query_id, request.query, request.filters.model_dump(), request.options.model_dump())

    return QueryResponse(query_id=query_id, status="processing",
        processing_time_ms=0,
        results=[], agent_trace={})


@router.get("/query/{query_id}/status", response_model=QueryStatusResponse)
async def get_query_status(query_id: str, db: AsyncSession = Depends(get_db)) -> QueryStatusResponse:
    """Poll the status of a running or completed query."""
    stmt = select(QueryRecord).where(QueryRecord.id == uuid.UUID(query_id))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail={"error": {"code": "QUERY_NOT_FOUND", "message": f"Query {query_id} not found", "query_id": query_id}})
    
    trace_data = json.loads(record.agent_trace) if record.agent_trace else {}
    return QueryStatusResponse(query_id=query_id, status=record.status,
        processing_time_ms=record.processing_time_ms, created_at=record.created_at.isoformat(),
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        agent_trace=trace_data)

@router.get("/query/{query_id}", response_model=QueryResponse)
async def get_query(query_id: str, db: AsyncSession = Depends(get_db)) -> QueryResponse:
    """Get the full details of a completed query."""
    stmt = select(QueryRecord).where(QueryRecord.id == uuid.UUID(query_id))
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail={"error": {"code": "QUERY_NOT_FOUND", "message": f"Query {query_id} not found", "query_id": query_id}})
    if record.status != "complete":
        raise HTTPException(status_code=400, detail={"error": {"code": "QUERY_NOT_COMPLETE", "message": f"Query {query_id} is not complete", "query_id": query_id}})
        
    results_data = json.loads(record.result) if record.result else []
    trace_data = json.loads(record.agent_trace) if record.agent_trace else {}
    
    return QueryResponse(
        query_id=query_id,
        status=record.status,
        processing_time_ms=record.processing_time_ms or 0,
        results=results_data,
        agent_trace=trace_data
    )


@router.get("/queries", response_model=QueryListResponse)
async def list_queries(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)) -> QueryListResponse:
    """List past query records, ordered by most recent first."""
    from sqlalchemy import func as sqlfunc
    total_stmt = select(sqlfunc.count()).select_from(QueryRecord)
    total = (await db.execute(total_stmt)).scalar() or 0

    stmt = select(QueryRecord).order_by(QueryRecord.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    records = result.scalars().all()

    items = [
        QueryListItem(
            query_id=str(r.id),
            query_text=r.query_text[:200],  # Truncate for list view
            status=r.status,
            processing_time_ms=r.processing_time_ms,
            created_at=r.created_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
        )
        for r in records
    ]
    return QueryListResponse(queries=items, total=total)
