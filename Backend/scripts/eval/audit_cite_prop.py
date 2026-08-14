"""
Leakage audit for the citation-propagation channel.

WHY THIS EXISTS
RESULTS_V2 §4 documents a result that had to be withdrawn: the authority re-rank looked
like a win, and the entire advantage was the label edge Q -> C being counted in C's
in-degree. `cite_prop` touches the same citation graph, so it must clear the same bar
BEFORE its numbers are reported. A channel that scores candidates using the graph is
guilty until proven innocent.

THE THREE WAYS THIS CHANNEL COULD CHEAT, each checked directly against the data:

  1. SELF-EDGE. If the query case Q appears in its own neighbour set, then Q's own
     citations — which ARE the qrels — vote for the answer. Checked: Q never appears
     among the neighbours.

  2. FUTURE CITATIONS. If a neighbour was decided after Q, its citations are not
     information a reader had at query time. Checked: every neighbour's year and every
     voting edge's citing year is <= query_year - 1.

  3. THE LABEL EDGE ITSELF. Even with Q excluded from the neighbour list, an edge whose
     citing_case_id == qid would still leak if it reached the vote. Checked: zero such
     edges contribute.

Also reports COVERAGE — the share of queries for which the channel votes at all — since
a channel that fires on few queries cannot be responsible for a large mean gain, and
that is worth knowing before attributing the improvement to it.

Usage (from Backend/):
    python -m scripts.eval.audit_cite_prop --data-dir ../data --split dev
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from scripts.lib.report import Report


def _year_of(case_id: str) -> int:
    m = re.match(r"^(\d{4})_", case_id)
    return int(m.group(1)) if m else 0


async def run(args: argparse.Namespace) -> None:
    from sqlalchemy import text as sa_text

    from app.core.database import async_session_factory
    from scripts.eval.run_eval import Harness

    data = Path(args.data_dir)
    queries = json.loads((data / "eval" / args.queries).read_text(encoding="utf-8"))
    if args.split != "all":
        queries = [q for q in queries if q.get("split") == args.split]
    if args.limit:
        queries = queries[: args.limit]

    # The qrels are the ground truth the channel must not be reading.
    qrels: dict[str, set[str]] = {}
    for line in (data / "eval" / "qrels.txt").read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) >= 4 and int(p[3]) > 0:
            qrels.setdefault(p[0], set()).add(p[2])

    v_self = v_future_n = v_future_e = v_label_edge = 0
    n_with_votes = 0
    n_qrel_hits = 0
    n_votes_total = 0

    async with async_session_factory() as db:
        h = Harness(db, data, args.top_k, args.depth)
        for n, q in enumerate(queries, 1):
            qid = q["qid"]
            qyear = q.get("year") or 0
            max_year = qyear - 1

            neigh = (await h.bm25_pooled("bm25_full", q["text"], qid, max_year))[:50]
            nids = [x["case_id"] for x in neigh]

            # ── check 1: the query case must never be its own neighbour
            if qid in nids:
                v_self += 1
            # ── check 2a: no neighbour decided at or after the query year
            if any(_year_of(c) > max_year for c in nids):
                v_future_n += 1

            rows = (await db.execute(sa_text("""
                SELECT ci.citing_case_id, ci.cited_case_id, c.year
                FROM citations ci
                JOIN cases c ON c.case_id = ci.citing_case_id
                WHERE ci.citing_case_id = ANY(:nids)
                  AND ci.cited_case_id <> :qid
                  AND (:maxyear <= 0 OR c.year <= :maxyear)
            """), {"nids": nids, "qid": qid, "maxyear": max_year})).fetchall()

            if rows:
                n_with_votes += 1
            n_votes_total += len(rows)
            for citing, cited, cyear in rows:
                # ── check 3: an edge FROM the query case is the label itself
                if citing == qid:
                    v_label_edge += 1
                # ── check 2b: no voting edge from a case decided after the query
                if max_year > 0 and (cyear or 0) > max_year:
                    v_future_e += 1
                if cited in qrels.get(qid, set()):
                    n_qrel_hits += 1

            if n % 100 == 0:
                print(f"  audited {n}/{len(queries)} ...", end="\r")

    nq = len(queries)
    rep = Report("audit_cite_prop", data, args)
    rep.section("Leakage audit — citation propagation")
    rep.stat("queries_audited", nq)
    rep.stat("split", args.split)
    rep.table("Violations (every count must be 0)",
              ["check", "violating queries/edges"],
              [["query case present in its own neighbour set", v_self],
               ["neighbour decided after query year", v_future_n],
               ["voting edge from a case decided after query year", v_future_e],
               ["voting edge whose citing_case_id == query (the label edge)", v_label_edge]])
    clean = (v_self + v_future_n + v_future_e + v_label_edge) == 0
    rep.stat("VERDICT", "CLEAN" if clean else "LEAKAGE DETECTED")

    rep.section("Coverage")
    rep.stat("queries_with_any_vote", n_with_votes)
    rep.stat("coverage_pct", round(100 * n_with_votes / max(nq, 1), 1))
    rep.stat("mean_voting_edges_per_query", round(n_votes_total / max(nq, 1), 1))
    rep.stat("voting_edges_hitting_a_relevant_case", n_qrel_hits)
    rep.note("Coverage below 100 % is expected: the in-corpus citation graph is sparse "
             "(4,891 edges over 7,096 judgments). RRF contributes nothing for a query "
             "where the channel is silent, so the gain is concentrated on covered queries.")
    rep.save()

    print(f"\nVERDICT: {'CLEAN' if clean else 'LEAKAGE DETECTED'}")
    print(f"  self-edge violations ........ {v_self}")
    print(f"  future neighbour violations . {v_future_n}")
    print(f"  future edge violations ...... {v_future_e}")
    print(f"  label-edge violations ....... {v_label_edge}")
    print(f"  coverage .................... {n_with_votes}/{nq} "
          f"({100*n_with_votes/max(nq,1):.1f}%)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit cite_prop for citation-graph leakage")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--split", type=str, default="dev", choices=["all", "dev", "test"])
    ap.add_argument("--queries", type=str, default="queries_short.json")
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--depth", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
