"""
Drive N queries end-to-end through the multi-agent pipeline and persist a QueryRecord
for each, so trace_stats.py has something to mine (Q27, Q28, Q31, Q33, Q36, Q37).

Calls SchedulerAgent directly rather than going through the HTTP API: the API's only
role is to create the record and hand off to a BackgroundTask, which is exactly what
this does. Requires Postgres and Ollama to be up.

Usage (from Backend/):
    python -m scripts.eval.run_agent_traces --n 30
    python -m scripts.eval.run_agent_traces --n 1 --queries queries_short.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.agents.scheduler import SchedulerAgent
from app.core.database import async_session_factory
from app.models.case import QueryRecord


async def one_query(text: str, timeout_s: float) -> tuple[str, float]:
    """Run a single query to completion. Returns (status, wall_seconds)."""
    qid = str(uuid.uuid4())
    t0 = time.monotonic()
    async with async_session_factory() as db:
        db.add(QueryRecord(id=uuid.UUID(qid), query_text=text, status="processing",
                           filters="{}", options="{}"))
        await db.commit()

    try:
        async with async_session_factory() as db:
            scheduler = SchedulerAgent(db_session=db)
            result = await asyncio.wait_for(
                scheduler.execute({"query_id": qid, "query": text,
                                   "filters": {}, "options": {}}),
                timeout=timeout_s)
            elapsed = time.monotonic() - t0
            record = await db.get(QueryRecord, uuid.UUID(qid))
            record.status = "complete"
            record.result = json.dumps(result.get("results", []), default=str)
            record.agent_trace = json.dumps(result.get("agent_trace", {}), default=str)
            # Prefer the pipeline's own measurement; fall back to wall clock.
            record.processing_time_ms = int(result.get("processing_time_ms")
                                            or elapsed * 1000)
            record.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return "complete", elapsed
    except Exception as e:                                  # noqa: BLE001
        elapsed = time.monotonic() - t0
        async with async_session_factory() as db:
            record = await db.get(QueryRecord, uuid.UUID(qid))
            if record:
                record.status = "failed"
                record.agent_trace = json.dumps({"error": f"{type(e).__name__}: {e}"})
                record.processing_time_ms = int(elapsed * 1000)
                record.completed_at = datetime.now(timezone.utc)
                await db.commit()
        print(f"    FAILED after {elapsed:.1f}s: {type(e).__name__}: {e}")
        return "failed", elapsed


async def main_async(args: argparse.Namespace) -> None:
    qpath = Path(args.data_dir) / "eval" / args.queries
    queries = json.loads(qpath.read_text(encoding="utf-8"))
    if isinstance(queries, dict):
        queries = queries.get("queries", [])
    # Test split only: these are the queries the retrieval numbers are reported on.
    queries = [q for q in queries if q.get("split") == args.split][: args.n]
    print(f"[info] {len(queries)} queries from {qpath.name} (split={args.split})\n")

    done = failed = 0
    t_start = time.monotonic()
    for i, q in enumerate(queries, 1):
        text = q["text"]
        print(f"[{i}/{len(queries)}] {q['qid']}  {text[:70]}...")
        status, elapsed = await one_query(text, args.timeout)
        done += status == "complete"
        failed += status == "failed"
        rate = (time.monotonic() - t_start) / i
        print(f"    {status} in {elapsed:.1f}s  "
              f"(mean {rate:.1f}s/query, ~{rate*(len(queries)-i)/60:.1f} min left)")

    print(f"\n[done] {done} complete, {failed} failed")
    print("[next] python -m scripts.eval.trace_stats --data-dir ../data")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run queries end-to-end for agent traces")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--queries", type=str, default="queries_short.json")
    ap.add_argument("--split", type=str, default="test")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="per-query timeout in seconds")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
