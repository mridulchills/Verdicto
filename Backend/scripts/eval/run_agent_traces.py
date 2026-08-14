"""
Drive N queries end-to-end through the multi-agent pipeline and persist a QueryRecord
for each, so trace_stats.py has something to mine (Q27, Q28, Q31, Q33, Q36, Q37).

Calls SchedulerAgent directly rather than going through the HTTP API: the API's only
role is to create the record and hand off to a BackgroundTask, which is exactly what
this does. Requires Postgres and Ollama to be up.

CRASH DURABILITY. Every completed query is appended to a JSONL sidecar and fsync'd
before the next one starts, so an interrupted run loses at most the query in flight:

    data/traces/run_<tag>.jsonl        one JSON object per query, append-only
    data/traces/run_<tag>.meta.json    settings the run was executed under

Re-running the same --tag RESUMES: queries already in the JSONL are skipped. Pass
--restart to ignore the sidecar and start over. The JSONL carries the full agent_trace,
so the run survives even total loss of the database.

Usage (from Backend/):
    python -m scripts.eval.run_agent_traces --n 30 --tag thresh085
    python -m scripts.eval.run_agent_traces --n 30 --tag thresh085          # resumes
    python -m scripts.eval.run_agent_traces --n 1 --queries queries_short.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.scheduler import SchedulerAgent
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.case import QueryRecord


# ── Durable sidecar ──────────────────────────────────────────────────────────

def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    """Append one record and force it to disk before returning.

    flush() alone only reaches the OS buffer; os.fsync is what survives a hard kill.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, default=str, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _load_done(path: Path) -> dict[str, str]:
    """qid -> status for every query already recorded. Tolerates a torn last line."""
    if not path.exists():
        return {}
    done: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            print(f"[warn] discarding torn JSONL line ({len(line)} chars) — "
                  f"that query will be re-run")
            continue
        if rec.get("qid"):
            done[rec["qid"]] = rec.get("status", "unknown")
    return done


def _summarise(trace: dict[str, Any]) -> dict[str, Any]:
    """Pull the headline numbers out of a trace so the JSONL is readable without tooling."""
    sched = trace.get("scheduler", {}).get("details", {})
    ev = trace.get("evaluator", {}).get("details", {})
    return {
        "iterations": sched.get("iterations"),
        "final_confidence": ev.get("confidence"),
        "needs_refinement": ev.get("needs_refinement"),
        "latency_ms": {a: trace.get(a, {}).get("latency_ms")
                       for a in ("query_planner", "retriever", "precedent_weighting",
                                 "debate", "evaluator", "scheduler")},
    }


# ── One query ────────────────────────────────────────────────────────────────

async def one_query(text: str, timeout_s: float) -> tuple[str, float, dict[str, Any]]:
    """Run a single query to completion. Returns (status, wall_seconds, payload)."""
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
            trace = result.get("agent_trace", {}) or {}
            record = await db.get(QueryRecord, uuid.UUID(qid))
            record.status = "complete"
            record.result = json.dumps(result.get("results", []), default=str)
            record.agent_trace = json.dumps(trace, default=str)
            # Prefer the pipeline's own measurement; fall back to wall clock.
            record.processing_time_ms = int(result.get("processing_time_ms")
                                            or elapsed * 1000)
            record.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return "complete", elapsed, {
                "record_id": qid,
                "agent_trace": trace,
                "results": result.get("results", []),
                "processing_time_ms": record.processing_time_ms,
                **_summarise(trace),
            }
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
        return "failed", elapsed, {"record_id": qid,
                                   "error": f"{type(e).__name__}: {e}"}


# ── Driver ───────────────────────────────────────────────────────────────────

def _load_faiss(data_dir: Path) -> dict[str, Any]:
    """Load the FAISS index the way app/main.py's lifespan does.

    The scheduler is invoked directly here, which bypasses the API startup that
    normally calls load(). Without this the retriever logs `faiss_not_loaded`, silently
    returns [] from the dense channel, and the whole pipeline degrades to Postgres
    ts_rank — which is exactly what happened in the first trace run. Fail loudly.

    settings.faiss_index_path is relative to the CWD ("./data/index/..."), which is
    wrong when running from Backend/, so resolve it against --data-dir instead.
    """
    from app.core.faiss_index import get_faiss_index

    settings = get_settings()
    idx = get_faiss_index()
    if not idx.is_loaded:
        settings.faiss_index_path = str((data_dir / "index" / "cases.index").resolve())
        settings.faiss_mapping_path = str((data_dir / "index" / "cases_mapping.json").resolve())
        idx.load()
    return {"faiss_vectors": idx.total_vectors,
            "faiss_index_path": settings.faiss_index_path}


async def main_async(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    qpath = data_dir / "eval" / args.queries
    queries = json.loads(qpath.read_text(encoding="utf-8"))
    if isinstance(queries, dict):
        queries = queries.get("queries", [])
    # Test split only: these are the queries the retrieval numbers are reported on.
    queries = [q for q in queries if q.get("split") == args.split][: args.n]

    jsonl = data_dir / "traces" / f"run_{args.tag}.jsonl"
    meta = data_dir / "traces" / f"run_{args.tag}.meta.json"

    if args.restart and jsonl.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        jsonl.rename(jsonl.with_suffix(f".jsonl.superseded-{stamp}"))
        print(f"[info] --restart: previous sidecar moved aside")

    done = _load_done(jsonl)
    pending = [q for q in queries if q["qid"] not in done]

    faiss_info = _load_faiss(data_dir)

    settings = get_settings()
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({
        "tag": args.tag,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries_file": args.queries,
        "split": args.split,
        "n_requested": args.n,
        "confidence_threshold": settings.confidence_threshold,
        "scheduler_max_iterations": settings.scheduler_max_iterations,
        "ollama_model": settings.ollama_model,
        "ollama_url": settings.ollama_url,
        **faiss_info,
    }, indent=1), encoding="utf-8")

    print(f"[info] {len(queries)} queries from {qpath.name} (split={args.split})")
    print(f"[info] model={settings.ollama_model} threshold={settings.confidence_threshold} "
          f"max_iter={settings.scheduler_max_iterations}")
    print(f"[info] faiss vectors={faiss_info['faiss_vectors']}")
    print(f"[info] durable log -> {jsonl}")
    if done:
        print(f"[info] resuming: {len(done)} already recorded, {len(pending)} to run")
    print()

    ok = sum(1 for s in done.values() if s == "complete")
    bad = sum(1 for s in done.values() if s != "complete")
    t_start = time.monotonic()

    for i, q in enumerate(pending, 1):
        text = q["text"]
        print(f"[{i}/{len(pending)}] {q['qid']}  {text[:70]}...")
        status, elapsed, payload = await one_query(text, args.timeout)
        ok += status == "complete"
        bad += status != "complete"

        # Durable BEFORE the next query starts — a kill here loses nothing already run.
        _append_jsonl(jsonl, {
            "qid": q["qid"],
            "tag": args.tag,
            "query_text": text,
            "status": status,
            "wall_seconds": round(elapsed, 2),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        })

        rate = (time.monotonic() - t_start) / i
        it = payload.get("iterations")
        conf = payload.get("final_confidence")
        extra = f"  iters={it} conf={conf}" if it is not None else ""
        print(f"    {status} in {elapsed:.1f}s{extra}  "
              f"(mean {rate:.1f}s/query, ~{rate*(len(pending)-i)/60:.1f} min left)")

    print(f"\n[done] {ok} complete, {bad} failed  (of {len(queries)} requested)")
    print(f"[log ] {jsonl}")
    print("[next] python -m scripts.eval.trace_stats --data-dir ../data")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run queries end-to-end for agent traces")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--queries", type=str, default="queries_short.json")
    ap.add_argument("--split", type=str, default="test")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--tag", type=str, default="default",
                    help="names the durable sidecar; re-using a tag resumes that run")
    ap.add_argument("--restart", action="store_true",
                    help="ignore an existing sidecar for this tag and start over")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="per-query timeout in seconds")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
