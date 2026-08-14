"""
Pre-compute Query Planner reformulations for the evaluation queries.

WHY THIS IS THE INTERESTING CONDITION
Every retrieval result so far is LLM-free by design. This is the one place where the
agent system can legitimately improve retrieval rather than merely explain it: the
Query Planner already generates 2-3 alternative formulations of each query, and the
deployed retriever throws all but the first away (Q7). Retrieving with each and fusing
the ranked lists is textbook query expansion, and it is the multi-agent architecture
doing measurable work.

Reformulations are cached to disk so the expensive LLM pass runs once and the
retrieval experiments stay fast and repeatable.

Usage (from Backend/):
    python -m scripts.eval.build_expansions --data-dir ../data --queries queries_short.json --split test
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from scripts.lib.report import Report


async def run(args: argparse.Namespace) -> None:
    from app.agents.query_planner import QueryPlannerAgent

    data = Path(args.data_dir)
    eval_dir = data / "eval"
    queries = json.loads((eval_dir / args.queries).read_text(encoding="utf-8"))
    if args.split != "all":
        queries = [q for q in queries if q.get("split") == args.split]
    if args.limit:
        queries = queries[: args.limit]

    out_path = eval_dir / f"expansions_{Path(args.queries).stem}_{args.split}.json"
    cache: dict[str, dict] = {}
    if out_path.exists() and not args.force:
        cache = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"[info] resuming: {len(cache)} already cached")

    planner = QueryPlannerAgent()
    todo = [q for q in queries if q["qid"] not in cache]
    print(f"[info] {len(todo)} queries to plan ({len(queries)} total)")

    t0 = time.monotonic()
    failures = 0
    sem = asyncio.Semaphore(args.concurrency)

    async def plan_one(q: dict) -> None:
        nonlocal failures
        async with sem:
            try:
                r = await planner.execute({"query_id": q["qid"], "query": q["text"]})
                # confidence == 0.3 is the planner's JSON-parse degradation sentinel
                if abs(float(r.get("confidence", 0)) - 0.3) < 1e-9:
                    failures += 1
                cache[q["qid"]] = {
                    "reformulations": r.get("reformulated_queries", [])[:3],
                    "issues": r.get("extracted_issues", [])[:3],
                    "domain": r.get("legal_domain", "general"),
                    "confidence": r.get("confidence", 0.0),
                }
            except Exception as e:
                failures += 1
                cache[q["qid"]] = {"reformulations": [], "issues": [], "domain": "general",
                                   "confidence": 0.0, "error": str(e)[:120]}

    for i in range(0, len(todo), args.checkpoint):
        batch = todo[i: i + args.checkpoint]
        await asyncio.gather(*(plan_one(q) for q in batch))
        out_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        done = min(i + args.checkpoint, len(todo))
        el = time.monotonic() - t0
        rate = done / max(el, 1e-6)
        print(f"[info] planned {done}/{len(todo)} | {rate:.2f} q/s | "
              f"~{(len(todo)-done)/max(rate,1e-6)/60:.1f} min left | failures {failures}")

    out_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    elapsed = time.monotonic() - t0

    n_ref = [len(v.get("reformulations", [])) for v in cache.values()]
    rep = Report(f"build_expansions_{args.split}", data, args)
    rep.section("Query Planner expansions")
    rep.stat("queries_planned", len(cache))
    rep.stat("llm_calls", len(todo))
    rep.stat("json_parse_failures", failures)
    rep.stat("parse_failure_rate_pct", round(100 * failures / max(len(todo), 1), 2),
             "Q33 — the number that characterises the model's JSON reliability")
    rep.stat("mean_reformulations", round(sum(n_ref) / max(len(n_ref), 1), 2))
    rep.stat("elapsed_minutes", round(elapsed / 60, 2))
    rep.stat("seconds_per_query", round(elapsed / max(len(todo), 1), 2))
    rep.stat("cache_file", str(out_path))
    rep.save()
    print(f"[done] {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pre-compute planner reformulations")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--queries", type=str, default="queries_short.json")
    ap.add_argument("--split", type=str, default="test", choices=["all", "dev", "test"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=4,
                    help="parallel LLM requests; Ollama serialises on one GPU but "
                         "pipelining still helps")
    ap.add_argument("--checkpoint", type=int, default=20, help="save cache every N")
    ap.add_argument("--force", action="store_true")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
