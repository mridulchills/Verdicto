"""
Extract citations from judgment text and populate the `citations` table.

This is the highest-leverage script in the project. One extractor unlocks three
separate blockers:
    1. the citation graph                  (Q18 — currently zero nodes, zero edges)
    2. the 0.35 precedential authority signal (Q20 — currently identically zero)
    3. cited-precedents-as-labels ground truth (Q47 — the paper's only realistic
       route to relevance judgements)

PREREQUISITE: load_metadata.py must have populated cases.citation. Without it there
is nothing to resolve extracted citation strings against, and this script will
correctly report a 0% resolution rate.

Resolution strategy, in order:
    1. canonical citation match   (AIR:1973:0:1461 == AIR:1973:0:1461)   — high precision
    2. case-name match            ("X v. Y" against title/petitioner+respondent) — fallback

Usage (from Backend/):
    python -m scripts.ingest.extract_citations --data-dir ../data --dry-run
    python -m scripts.ingest.extract_citations --data-dir ../data
    python -m scripts.ingest.extract_citations --data-dir ../data --limit 500   # smoke test
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from pathlib import Path

from scripts.lib.citations import find_citations, name_key, normalise_metadata_citations
from scripts.lib.report import EventLog, Report


async def run(args: argparse.Namespace) -> None:
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    data = Path(args.data_dir)
    txt_dir = data / "processed"
    if not txt_dir.exists():
        raise SystemExit(f"No extracted text at {txt_dir}")

    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url

    rep = Report("extract_citations", data, args)
    engine = create_async_engine(db_url)

    # ── 1. Build the resolution index from the DB ─────────────────────────
    print("[info] loading case metadata for resolution ...")
    async with engine.connect() as conn:
        rows = (await conn.execute(sa_text(
            "SELECT case_id, citation, title, petitioner, respondent FROM cases"
        ))).fetchall()

    by_citation: dict[str, str] = {}
    by_name: dict[str, str] = {}
    citation_populated = 0
    for case_id, citation, title, pet, resp in rows:
        if citation:
            citation_populated += 1
            # Index EVERY canonical form in the field. load_metadata.py stores the
            # reporter citation and the neutral citation together ("... | 2020 INSC 395"),
            # and a citing judgment may use either.
            for canon in normalise_metadata_citations(citation):
                if canon not in by_citation:
                    by_citation[canon] = case_id
        k = name_key(title)
        if k and k not in by_name:
            by_name[k] = case_id
        if pet and resp:
            k2 = name_key(f"{pet} v {resp}")
            if k2 and k2 not in by_name:
                by_name[k2] = case_id

    rep.section("Resolution index")
    rep.stat("cases_in_db", len(rows))
    rep.stat("cases_with_citation_populated", citation_populated)
    rep.stat("canonical_citations_indexed", len(by_citation))
    rep.stat("name_keys_indexed", len(by_name))

    if citation_populated == 0:
        rep.note("STOP: cases.citation is empty for every row. Run load_metadata.py first — "
                 "nothing can be resolved and the resolution rate below will be 0%.")
        print("\n[ERROR] cases.citation is empty. Run load_metadata.py first.\n")
        rep.save()
        await engine.dispose()
        return

    # ── 2. Scan documents ─────────────────────────────────────────────────
    files = sorted(txt_dir.glob("*.txt"))
    if args.limit:
        files = files[: args.limit]
    corpus_ids = {r[0] for r in rows}

    edges: dict[tuple[str, str], int] = defaultdict(int)
    graded: dict[tuple[str, str], int] = {}
    total_cites = 0
    resolved_by_citation = 0
    resolved_by_name = 0
    unresolved = 0
    out_of_scope = 0
    docs_scanned = 0
    docs_with_edges = 0
    unresolved_examples = Counter()

    log = EventLog("extract_citations_per_doc", data)
    print(f"[info] scanning {len(files)} documents ...")

    for n, path in enumerate(files, 1):
        case_id = path.stem
        if case_id not in corpus_ids:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.write(case_id=case_id, status="unreadable", error=str(e))
            continue

        docs_scanned += 1
        res = find_citations(text)
        out_of_scope += res.out_of_scope
        total_cites += len(res.citations)

        doc_edges = 0
        for c in res.citations:
            target = by_citation.get(c.canonical)
            how = "citation"
            if target is None:
                unresolved += 1
                unresolved_examples[c.raw[:40]] += 1
                continue
            resolved_by_citation += 1
            if target == case_id:
                continue                        # self-citation
            key = (case_id, target)
            edges[key] += 1
            graded[key] = max(graded.get(key, 1), 2 if c.discussed else 1)
            doc_edges += 1

        if args.use_names:
            for nm in res.case_names:
                k = name_key(nm)
                target = by_name.get(k) if k else None
                if target and target != case_id:
                    key = (case_id, target)
                    if key not in edges:
                        resolved_by_name += 1
                        edges[key] += 1
                        graded.setdefault(key, 1)
                        doc_edges += 1

        if doc_edges:
            docs_with_edges += 1
        log.write(case_id=case_id, citations_found=len(res.citations),
                  edges_created=doc_edges, out_of_scope=res.out_of_scope)

        if n % 500 == 0:
            print(f"[info] {n}/{len(files)} docs, {len(edges)} edges ...", end="\r")

    log.close()

    resolution_rate = 100 * resolved_by_citation / max(total_cites, 1)

    rep.section("Extraction results")
    rep.stat("documents_scanned", docs_scanned)
    rep.stat("sc_citations_found", total_cites)
    rep.stat("mean_citations_per_document", round(total_cites / max(docs_scanned, 1), 2))
    rep.stat("out_of_scope_citations", out_of_scope, "High Court / other reporters (excluded)")
    rep.stat("resolved_by_canonical_citation", resolved_by_citation)
    rep.stat("resolved_by_case_name", resolved_by_name)
    rep.stat("unresolved", unresolved)
    rep.stat("in_corpus_resolution_rate_pct", round(resolution_rate, 2),
             "THE number that determines whether ground truth is viable (Q19, Q51)")
    rep.stat("edges", len(edges))
    rep.stat("documents_with_at_least_one_edge", docs_with_edges)
    rep.stat("mean_out_degree", round(len(edges) / max(docs_with_edges, 1), 2))

    if unresolved_examples:
        rep.table("Most common UNRESOLVED citation strings (diagnose mapping gaps here)",
                  ["citation_string", "occurrences"],
                  [[k, v] for k, v in unresolved_examples.most_common(25)])

    grade_counts = Counter(graded.values())
    rep.table("Edge grades (Q52)", ["grade", "meaning", "edges"],
              [[2, "cited AND discussed", grade_counts.get(2, 0)],
               [1, "cited in passing", grade_counts.get(1, 0)]])

    if resolution_rate < 1:
        rep.note("Resolution rate below 1%: citation-derived ground truth will not work "
                 "on this corpus. See IMPLEMENTATION_PLAN.md Step 4 fallbacks.")
    elif resolution_rate < 5:
        rep.note("Low resolution rate: expect very few labels per query. Widen the corpus "
                 "year range, or check the unresolved-strings table above for a reporter "
                 "format the extractor is missing.")

    if args.dry_run:
        rep.note("Dry run: no rows written to `citations`.")
        print(f"\n[dry-run] would write {len(edges)} edges")
        rep.save()
        await engine.dispose()
        return

    # ── 3. Write edges ────────────────────────────────────────────────────
    print(f"\n[info] writing {len(edges)} edges to `citations` ...")
    async with engine.begin() as conn:
        if args.truncate:
            await conn.execute(sa_text("DELETE FROM citations"))
        stmt = sa_text("""
            INSERT INTO citations (citing_case_id, cited_case_id, citation_count)
            VALUES (:citing, :cited, :count)
            ON CONFLICT (citing_case_id, cited_case_id)
            DO UPDATE SET citation_count = EXCLUDED.citation_count
        """)
        rows_payload = [{"citing": a, "cited": b, "count": c} for (a, b), c in edges.items()]
        for i in range(0, len(rows_payload), args.batch_size):
            await conn.execute(stmt, rows_payload[i: i + args.batch_size])
            print(f"[info] wrote {min(i+args.batch_size, len(rows_payload))}/{len(rows_payload)}", end="\r")

    # Persist grades separately for the golden set (the table has no grade column).
    grade_path = data / "eval" / "citation_grades.tsv"
    grade_path.parent.mkdir(parents=True, exist_ok=True)
    grade_path.write_text(
        "\n".join(f"{a}\t{b}\t{g}" for (a, b), g in graded.items()) + "\n", encoding="utf-8"
    )

    async with engine.connect() as conn:
        n_edges = (await conn.execute(sa_text("SELECT count(*) FROM citations"))).scalar() or 0
        top = (await conn.execute(sa_text("""
            SELECT cited_case_id, count(*) AS indeg FROM citations
            GROUP BY cited_case_id ORDER BY indeg DESC LIMIT 20
        """))).fetchall()
    await engine.dispose()

    rep.section("Citation graph (Q18)")
    rep.stat("graph_nodes", len(rows), "cases")
    rep.stat("graph_edges", int(n_edges))
    rep.stat("grades_file", str(grade_path))
    rep.table("Most-cited cases (in-degree) — sanity-check these are landmark judgments",
              ["cited_case_id", "in_degree"], [[r[0], r[1]] for r in top])
    rep.note("Eyeball the table above. If the most-cited cases are not recognisable "
             "landmark judgments, the resolution is matching the wrong things.")

    print(f"\n[done] {n_edges} edges in the citation graph")
    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract citations and build the citation graph")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--database-url", type=str, default=None)
    ap.add_argument("--limit", type=int, default=None, help="scan only N documents (smoke test)")
    ap.add_argument("--batch-size", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--truncate", action="store_true", help="clear `citations` before writing")
    ap.add_argument("--use-names", action="store_true",
                    help="enable case-name fallback matching (higher recall, lower precision)")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
