"""
Run every retrieval condition over the golden set and write TREC run files.

NO LLM IS INVOLVED. The retriever reads `original_query` and `reformulated_queries`
from its input dict, and `reformulated[:1]` on an empty list is simply empty — so the
Query Planner can be bypassed entirely. Consequence: the paper's core evidence is
deterministic, reproducible, and completely unaffected by the quality of the local
8B model.

Conditions:
    dense           FAISS only
    tsrank          PostgreSQL ts_rank only          (what the deployed system uses)
    bm25            rank_bm25 only                   (true BM25 baseline, k1/b reportable)
    hybrid          RRF(dense, tsrank)               (the system's retrieval)
    hybrid_bm25     RRF(dense, bm25)
    hybrid_auth     RRF(dense, tsrank) + authority re-rank   (the full pipeline)

LEAKAGE CONTROLS APPLIED ON EVERY CONDITION:
    * temporal filter  — candidates restricted to year < query year   (Q54, Q56)
      applied to BOTH channels, including FAISS, which the app itself does not do (Q54)
    * self-exclusion   — the query case removed from its own pool     (Q55)
    * rank renumbering — after filtering, because RRF consumes RANKS  (Q54)

Usage (from Backend/):
    python -m scripts.eval.run_eval --data-dir ../data
    python -m scripts.eval.run_eval --data-dir ../data --conditions dense,bm25,hybrid
    python -m scripts.eval.run_eval --data-dir ../data --split test
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from scripts.lib.report import Report

ALL_CONDITIONS = ["dense", "tsrank", "bm25", "hybrid", "hybrid_bm25", "hybrid_auth"]


def _year_of(case_id: str) -> int:
    m = re.match(r"^(\d{4})_", case_id)
    return int(m.group(1)) if m else 0


def _renumber(results: list[dict], key: str) -> list[dict]:
    """RRF consumes ranks, so any filtering must be followed by renumbering."""
    for i, r in enumerate(results, 1):
        r[key] = i
    return results


class Harness:
    """
    Thin evaluation harness. Shares the RANKING MATHS with the application
    (merge_rankings, the authority formula) but owns its own storage access, so a
    condition can be isolated without going through the agent pipeline.
    """

    def __init__(self, db, data_dir: Path, top_k: int, depth: int) -> None:
        self.db = db
        self.data_dir = data_dir
        self.top_k = top_k
        self.depth = depth
        self._bm25 = None
        self._bm25_ids: list[str] = []

    # ── dense ─────────────────────────────────────────────────────────────
    async def dense(self, text: str, qid: str, max_year: int) -> list[dict]:
        from app.core.faiss_index import get_faiss_index
        from app.services.embedding_service import get_embedding

        idx = get_faiss_index()
        if not idx.is_loaded:
            idx.load()
        emb = await get_embedding(text)
        # Over-fetch, because the temporal filter and self-exclusion will remove some.
        raw = idx.search(emb, top_k=self.top_k * self.depth)
        keep = [r for r in raw
                if r["case_id"] != qid and (max_year <= 0 or _year_of(r["case_id"]) <= max_year)]
        return _renumber(keep[: self.top_k], "faiss_rank")

    # ── ts_rank (what the deployed system uses) ───────────────────────────
    async def tsrank(self, text: str, qid: str, max_year: int) -> list[dict]:
        from sqlalchemy import text as sa_text
        from app.agents.retriever import RetrieverAgent

        tsquery = RetrieverAgent._build_or_tsquery(text)
        if not tsquery:
            return []
        sql = sa_text("""
            SELECT case_id, ts_rank(text_search_vector, to_tsquery('english', :q)) AS score
            FROM cases
            WHERE text_search_vector @@ to_tsquery('english', :q)
              AND case_id <> :qid
              AND (:maxyear <= 0 OR year <= :maxyear)
            ORDER BY score DESC
            LIMIT :k
        """)
        try:
            rows = (await self.db.execute(
                sql, {"q": tsquery, "qid": qid, "maxyear": max_year, "k": self.top_k}
            )).fetchall()
        except Exception as e:
            print(f"[warn] ts_rank failed for {qid}: {e}")
            return []
        out = [{"case_id": r[0], "bm25_score": float(r[1])} for r in rows]
        return _renumber(out, "bm25_rank")

    # ── true BM25 ─────────────────────────────────────────────────────────
    async def _ensure_bm25(self) -> None:
        if self._bm25 is not None:
            return
        from rank_bm25 import BM25Okapi
        from sqlalchemy import text as sa_text

        cache = self.data_dir / "eval" / "bm25_corpus.json"
        if cache.exists():
            payload = json.loads(cache.read_text(encoding="utf-8"))
            ids, toks = payload["ids"], payload["tokens"]
        else:
            print("[info] building BM25 index (one-off; cached afterwards) ...")
            rows = (await self.db.execute(sa_text(
                "SELECT case_id, coalesce(title,'') || ' ' || coalesce(facts_text,'') "
                "|| ' ' || coalesce(issues_text,'') FROM cases"
            ))).fetchall()
            ids = [r[0] for r in rows]
            toks = [re.findall(r"[a-z]{3,}", (r[1] or "").lower()) for r in rows]
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"ids": ids, "tokens": toks}), encoding="utf-8")
            print(f"[info] BM25 index built over {len(ids)} documents")
        self._bm25_ids = ids
        # k1=1.5, b=0.75 are rank_bm25's BM25Okapi defaults — REPORT THESE (Q59).
        self._bm25 = BM25Okapi(toks)

    async def bm25(self, text: str, qid: str, max_year: int) -> list[dict]:
        await self._ensure_bm25()
        import numpy as np
        toks = re.findall(r"[a-z]{3,}", text.lower())
        if not toks:
            return []
        scores = self._bm25.get_scores(toks)
        order = np.argsort(scores)[::-1][: self.top_k * self.depth]
        out = []
        for i in order:
            cid = self._bm25_ids[int(i)]
            if cid == qid or (max_year > 0 and _year_of(cid) > max_year):
                continue
            out.append({"case_id": cid, "bm25_score": float(scores[int(i)])})
            if len(out) >= self.top_k:
                break
        return _renumber(out, "bm25_rank")


async def run_condition(name: str, h: Harness, queries: list[dict], out_dir: Path,
                        use_authority: bool = False) -> dict[str, Any]:
    from app.agents.retriever import merge_rankings

    lines: list[str] = []
    latencies: list[float] = []
    empty = 0

    for n, q in enumerate(queries, 1):
        qid, text = q["qid"], q["text"]
        max_year = (q.get("year") or 0) - 1          # strict temporal split (Q54/Q56)
        t0 = time.monotonic()

        if name == "dense":
            cands = await h.dense(text, qid, max_year)
        elif name == "tsrank":
            cands = await h.tsrank(text, qid, max_year)
        elif name == "bm25":
            cands = await h.bm25(text, qid, max_year)
        elif name == "hybrid":
            cands = merge_rankings(await h.dense(text, qid, max_year),
                                   await h.tsrank(text, qid, max_year))
        elif name == "hybrid_bm25":
            cands = merge_rankings(await h.dense(text, qid, max_year),
                                   await h.bm25(text, qid, max_year))
        elif name == "hybrid_auth":
            cands = merge_rankings(await h.dense(text, qid, max_year),
                                   await h.tsrank(text, qid, max_year))
            use_authority = True
        else:
            raise ValueError(f"unknown condition {name}")

        cands = cands[: h.top_k]

        if use_authority and cands:
            from app.agents.precedent_weighter import PrecedentWeighterAgent
            w = await PrecedentWeighterAgent(db_session=h.db).execute(
                {"query_id": qid, "candidates": cands, "legal_domain": "general"})
            ranked = w.get("ranked_cases", [])
            score_of = lambda c: c.get("authority_score", 0.0)
        else:
            ranked = cands
            score_of = (lambda c: c.get("rrf_score", c.get("faiss_score", c.get("bm25_score", 0.0))))

        latencies.append((time.monotonic() - t0) * 1000)
        if not ranked:
            empty += 1
        for rank, c in enumerate(ranked[: h.top_k], 1):
            lines.append(f"{qid} Q0 {c['case_id']} {rank} {score_of(c):.6f} {name}")

        if n % 25 == 0:
            print(f"  [{name}] {n}/{len(queries)} queries ...", end="\r")

    path = out_dir / f"run_{name}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lat_sorted = sorted(latencies)
    stats = {
        "condition": name,
        "queries": len(queries),
        "lines": len(lines),
        "empty_result_queries": empty,
        "median_latency_ms": round(lat_sorted[len(lat_sorted)//2], 1) if lat_sorted else 0,
        "run_file": str(path),
    }
    print(f"  [{name}] done: {len(lines)} lines, {empty} empty, "
          f"median {stats['median_latency_ms']} ms")
    return stats


async def run(args: argparse.Namespace) -> None:
    from app.core.database import async_session_factory

    data = Path(args.data_dir)
    out_dir = data / "eval"
    qfile = out_dir / "queries.json"
    if not qfile.exists():
        raise SystemExit(f"No {qfile}. Run build_golden_set.py first.")

    queries = json.loads(qfile.read_text(encoding="utf-8"))
    if args.split != "all":
        queries = [q for q in queries if q.get("split") == args.split]
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        raise SystemExit(f"No queries for split={args.split}")

    conditions = [c.strip() for c in args.conditions.split(",")] if args.conditions else ALL_CONDITIONS

    rep = Report("run_eval", data, args)
    rep.section("Configuration")
    rep.stat("split", args.split)
    rep.stat("queries", len(queries))
    rep.stat("conditions", ", ".join(conditions))
    rep.stat("top_k", args.top_k)
    rep.stat("temporal_split", "year < query_year, applied to BOTH channels")
    rep.stat("self_exclusion", True)
    rep.stat("llm_used", False, "the planner is bypassed — results are deterministic")
    rep.note("BM25 parameters (rank_bm25 BM25Okapi defaults): k1=1.5, b=0.75. Report these.")

    print(f"[info] {len(queries)} queries, conditions: {', '.join(conditions)}")
    all_stats = []
    async with async_session_factory() as db:
        h = Harness(db, data, args.top_k, args.depth)
        for cond in conditions:
            if cond not in ALL_CONDITIONS:
                print(f"[warn] skipping unknown condition '{cond}'")
                continue
            print(f"\n[run] {cond}")
            try:
                all_stats.append(await run_condition(cond, h, queries, out_dir))
            except Exception as e:
                print(f"[error] condition {cond} failed: {e}")
                rep.note(f"Condition '{cond}' FAILED: {e}")

    if all_stats:
        rep.section("Runs produced")
        rep.table("Run files",
                  ["condition", "queries", "lines", "empty", "median_ms"],
                  [[s["condition"], s["queries"], s["lines"], s["empty_result_queries"],
                    s["median_latency_ms"]] for s in all_stats])
    rep.note("Next: python -m scripts.eval.score --data-dir ../data")
    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Run retrieval conditions, write TREC run files")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--conditions", type=str, default=None,
                    help=f"comma-separated; default all: {','.join(ALL_CONDITIONS)}")
    ap.add_argument("--split", type=str, default="all", choices=["all", "dev", "test"])
    ap.add_argument("--top-k", type=int, default=20, help="results kept per query")
    ap.add_argument("--depth", type=int, default=5,
                    help="over-fetch multiplier before temporal filtering")
    ap.add_argument("--limit", type=int, default=None)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
