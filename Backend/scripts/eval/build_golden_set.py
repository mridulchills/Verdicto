"""
Build the evaluation set: queries + TREC qrels from the citation graph.

Method (option (a) in Q47): a judgment becomes a QUERY; the cases it cites become
its RELEVANT documents. No annotators required, scales immediately, well precedented
in legal IR.

LEAKAGE CONTROL IS NOT OPTIONAL (Q48). The query text is a judgment that literally
contains the citations being used as its answer key. Every query is passed through
strip_leakage(), which removes citation strings AND case names. Without this, the
lexical channel simply copies the answer out of the query and every number in the
paper is invalid in a way a reviewer detects in seconds.

Outputs:
    <data-dir>/eval/queries.json        [{qid, text, year, n_relevant}]
    <data-dir>/eval/qrels.txt           TREC format: qid 0 docid grade
    <data-dir>/eval/leakage_samples.txt 20 stripped queries for manual inspection

Usage (from Backend/):
    python -m scripts.eval.build_golden_set --data-dir ../data
    python -m scripts.eval.build_golden_set --data-dir ../data --min-relevant 3 --graded
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
from collections import Counter
from pathlib import Path

from scripts.lib.citations import find_citations, strip_leakage
from scripts.lib.report import Report


async def run(args: argparse.Namespace) -> None:
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    data = Path(args.data_dir)
    out_dir = data / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url

    rep = Report("build_golden_set", data, args)
    engine = create_async_engine(db_url)

    # ── Load grades produced by extract_citations.py ──────────────────────
    grades: dict[tuple[str, str], int] = {}
    grade_file = out_dir / "citation_grades.tsv"
    if args.graded and grade_file.exists():
        for line in grade_file.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                grades[(parts[0], parts[1])] = int(parts[2])

    # ── Candidate queries: cases with enough outgoing citations ───────────
    print("[info] querying citation graph ...")
    async with engine.connect() as conn:
        rows = (await conn.execute(sa_text("""
            SELECT c.case_id, c.year, c.facts_text, c.issues_text,
                   array_agg(ci.cited_case_id) AS cited
            FROM cases c
            JOIN citations ci ON ci.citing_case_id = c.case_id
            GROUP BY c.case_id, c.year, c.facts_text, c.issues_text
            HAVING count(ci.cited_case_id) >= :minrel
            ORDER BY c.case_id
        """), {"minrel": args.min_relevant})).fetchall()
        total_cases = (await conn.execute(sa_text("SELECT count(*) FROM cases"))).scalar() or 0
    await engine.dispose()

    rep.section("Candidate pool")
    rep.stat("cases_in_corpus", int(total_cases))
    rep.stat("cases_with_at_least_min_citations", len(rows))
    rep.stat("min_relevant_required", args.min_relevant)

    if not rows:
        rep.note("No candidate queries. The citation graph is empty or too sparse — "
                 "run extract_citations.py, and check its resolution rate.")
        print("\n[ERROR] no candidates. Is the citations table populated?\n")
        rep.save()
        return

    # ── Build queries with leakage stripping ──────────────────────────────
    queries: list[dict] = []
    qrels: list[str] = []
    rel_counts: list[int] = []
    dropped_short = 0
    dropped_no_text = 0
    leak_residual = 0
    samples: list[str] = []

    for case_id, year, facts, issues, cited in rows:
        raw = ((facts or "")[: args.facts_chars] + " " + (issues or "")[: args.issues_chars]).strip()
        if not raw:
            dropped_no_text += 1
            continue

        text = strip_leakage(raw)
        if len(text) < args.min_query_chars:
            dropped_short += 1
            continue

        # Verify the stripper actually worked (Q48 requires this check).
        residual = find_citations(text, mark_discussed=False)
        if residual.citations:
            leak_residual += 1

        targets = sorted({t for t in cited if t and t != case_id})
        if len(targets) < args.min_relevant:
            continue

        queries.append({"qid": case_id, "text": text, "year": int(year or 0),
                        "n_relevant": len(targets)})
        rel_counts.append(len(targets))
        for t in targets:
            g = grades.get((case_id, t), 1) if args.graded else 1
            qrels.append(f"{case_id} 0 {t} {g}")

        if len(samples) < 20:
            samples.append(f"### {case_id}\n{text[:900]}\n")

    # ── Temporal split (Q53, Q54) ─────────────────────────────────────────
    queries.sort(key=lambda q: (q["year"], q["qid"]))
    split_at = int(len(queries) * args.dev_fraction)
    for i, q in enumerate(queries):
        q["split"] = "dev" if i < split_at else "test"

    # ── Write artefacts ───────────────────────────────────────────────────
    (out_dir / "queries.json").write_text(
        json.dumps(queries, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "qrels.txt").write_text("\n".join(qrels) + "\n", encoding="utf-8")
    (out_dir / "leakage_samples.txt").write_text(
        "MANUALLY INSPECT THESE. No case names or citations should remain (Q48).\n"
        "Put one of these in the paper's appendix.\n\n" + "\n".join(samples),
        encoding="utf-8")

    mean_rel = st.mean(rel_counts) if rel_counts else 0.0
    median_rel = st.median(rel_counts) if rel_counts else 0.0

    rep.section("Evaluation set (Q50, Q51)")
    rep.stat("Q_queries", len(queries), "number of query cases")
    rep.stat("total_judgements", len(qrels))
    rep.stat("mean_relevant_per_query", round(mean_rel, 2))
    rep.stat("median_relevant_per_query", round(median_rel, 2))
    rep.stat("dev_queries", split_at)
    rep.stat("test_queries", len(queries) - split_at)
    rep.stat("dropped_query_too_short_after_stripping", dropped_short)
    rep.stat("dropped_no_text", dropped_no_text)
    rep.stat("graded", bool(args.graded))

    if queries:
        yr = Counter(q["year"] for q in queries)
        rep.table("Queries per year", ["year", "queries"], [[y, yr[y]] for y in sorted(yr)])
        rep.stat("dev_year_range", f"{queries[0]['year']}-{queries[max(split_at-1,0)]['year']}")
        rep.stat("test_year_range", f"{queries[min(split_at,len(queries)-1)]['year']}-{queries[-1]['year']}")

    rep.section("Leakage control (Q48)")
    rep.stat("queries_with_residual_citations", leak_residual,
             "should be 0 — anything above 0 means the stripper missed a format")
    if leak_residual:
        rep.note(f"WARNING: {leak_residual} queries still contain citation strings after "
                 "stripping. Add the missing reporter format to scripts/lib/citations.py "
                 "and rebuild. Do not run the evaluation until this is 0.")
    rep.note("Manually read data/eval/leakage_samples.txt before running the evaluation. "
             "Include one stripped query in the paper's appendix — it pre-empts the first "
             "question any reviewer will ask.")

    # ── Metric guidance (Q51) ─────────────────────────────────────────────
    rep.section("Which metric to lead with (Q51)")
    if mean_rel < 5:
        rep.note(f"mean relevant/query = {mean_rel:.2f} < 5. P@10 has a ceiling below 0.5 "
                 "and is close to meaningless here. LEAD WITH nDCG@10 AND MRR. Report P@5 "
                 "only as a secondary figure.")
    else:
        rep.note(f"mean relevant/query = {mean_rel:.2f}. P@10 is interpretable; report "
                 "nDCG@10, P@5, P@10 and MRR together.")

    print(f"\n{'='*72}")
    print(f"  Q (queries) .................. {len(queries)}")
    print(f"  Judgements ................... {len(qrels)}")
    print(f"  Mean relevant per query ...... {mean_rel:.2f}")
    print(f"  Dev / test ................... {split_at} / {len(queries)-split_at}")
    print(f"  Residual leakage ............. {leak_residual}  (must be 0)")
    print(f"{'='*72}")
    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Build queries + qrels from the citation graph")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--database-url", type=str, default=None)
    ap.add_argument("--min-relevant", type=int, default=2,
                    help="minimum in-corpus citations for a case to become a query")
    ap.add_argument("--min-query-chars", type=int, default=200)
    ap.add_argument("--facts-chars", type=int, default=1500)
    ap.add_argument("--issues-chars", type=int, default=1000)
    ap.add_argument("--dev-fraction", type=float, default=0.6)
    ap.add_argument("--graded", action="store_true",
                    help="emit graded qrels (2=discussed, 1=cited in passing) — Q52")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
