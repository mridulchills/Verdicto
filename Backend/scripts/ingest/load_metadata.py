"""
Load Parquet metadata into the `cases` table — THE ROOT UNBLOCK.

populate_db.py writes only case_id, year, title and the four text segments. Every
other column (citation, bench, decision_date, disposal_nature, acts_sections,
petitioner, respondent) is left NULL. The consequences:

  * cases.citation is NULL  -> no citation can ever be resolved to a case_id
                            -> the citation graph cannot be built
                            -> the 0.35 authority weight is identically zero
                            -> citation-derived ground truth is impossible
  * cases.bench is NULL     -> _extract_bench_size() returns its default of 2 for every
                               case -> the 0.20 bench weight is a constant 0.06
                            -> the Constitution-Bench distinction, the most meaningful
                               authority signal in an SC-only corpus, is inert

Together that is 0.55 of the nominal 1.0 authority weight doing nothing.

The Parquet schema is whatever the AWS bucket publishes, so this script DISCOVERS
columns rather than assuming them. Run --inspect first; it prints the real column
names and a sample row, and writes them to the report. Then run for real.

Usage (from Backend/):
    python -m scripts.ingest.load_metadata --data-dir ../data --inspect
    python -m scripts.ingest.load_metadata --data-dir ../data --dry-run
    python -m scripts.ingest.load_metadata --data-dir ../data
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from typing import Any

from scripts.lib.report import Report

# Candidate source column names for each target column, in priority order.
#
# VERIFIED against the real AWS bucket (metadata/parquet/year=*/metadata.parquet,
# 18 columns). Two traps that only surfaced once the real data was inspected:
#
#   1. The parquet's own `case_id` column is the NEUTRAL CITATION ("2020 INSC 395"),
#      NOT the corpus identifier. The corpus case_id comes from the PDF filename,
#      which is the `path` column plus a language suffix:
#           path "2020_4_552_564"  ->  case_id "2020_4_552_564_EN"
#      So `path` is listed FIRST for case_id. Getting this wrong silently matches
#      zero rows.
#   2. The bench column is called `judge`, and it usually names only the presiding
#      or authoring judge rather than the full bench — see the note in main().
COLUMN_CANDIDATES: dict[str, list[str]] = {
    "case_id":        ["path", "filename", "file_name", "doc_id", "id"],
    "citation":       ["citation", "citations", "cite", "reporter_citation"],
    "neutral_citation": ["case_id", "nc_display", "neutral_citation", "neutral_cite"],
    "title":          ["title", "case_title", "case_name", "name_of_case"],
    "bench":          ["judge", "judges", "bench", "coram", "judge_names", "author_judge"],
    "decision_date":  ["decision_date", "judgment_date", "date", "date_of_judgment", "dt"],
    "disposal_nature": ["disposal_nature", "disposal", "status", "nature_of_disposal"],
    "petitioner":     ["petitioner", "appellant", "petitioner_name", "party1"],
    "respondent":     ["respondent", "respondent_name", "party2"],
    "acts_sections":  ["acts", "acts_sections", "statutes", "act", "sections"],
}

UPDATABLE = ["citation", "bench", "decision_date", "disposal_nature",
             "petitioner", "respondent", "acts_sections", "title"]


def _find_column(df_columns: list[str], target: str) -> str | None:
    lowered = {c.lower().strip(): c for c in df_columns}
    for cand in COLUMN_CANDIDATES.get(target, []):
        if cand in lowered:
            return lowered[cand]
    # substring fallback
    for cand in COLUMN_CANDIDATES.get(target, []):
        for lc, orig in lowered.items():
            if cand in lc:
                return orig
    return None


def _clean(v: Any) -> Any:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none", "null", "nat"}:
        return None
    return s


def _to_date(v: Any):
    s = _clean(v)
    if s is None:
        return None
    import datetime as dt
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            return dt.datetime.strptime(s[:len(fmt) + 4], fmt).date()
        except Exception:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return None


def _to_list(v: Any) -> list[str] | None:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        out = [str(x).strip() for x in v if _clean(x)]
        return out or None
    s = _clean(v)
    if s is None:
        return None
    parts = [p.strip() for p in re.split(r"[;|]|,\s(?=[A-Z])", s) if p.strip()]
    return parts or [s]


def _normalise_case_id(raw: Any, suffix: str = "_EN") -> str | None:
    """
    Corpus case_ids are the PDF filenames without extension, e.g. '2020_4_552_564_EN'
    (confirmed against data/tar/year=2020/english/english.index.json).

    The parquet `path` column carries '2020_4_552_564', so the language suffix is
    appended unless it is already present.
    """
    s = _clean(raw)
    if s is None:
        return None
    s = s.replace("\\", "/").split("/")[-1]
    for ext in (".pdf", ".txt", ".json", ".PDF", ".TXT", ".JSON"):
        if s.endswith(ext):
            s = s[: -len(ext)]
    if suffix and not s.endswith(suffix):
        s = s + suffix
    return s or None


async def run(args: argparse.Namespace) -> None:
    import pandas as pd

    data = Path(args.data_dir)
    meta_root = data / "raw" / "metadata"
    if not meta_root.exists():
        raise SystemExit(
            f"No metadata directory at {meta_root}.\n"
            "Download it first:  python -m scripts.ingest.download_dataset "
            "--year-from <Y1> --year-to <Y2> --output-dir ../data/raw"
        )

    files = sorted(meta_root.rglob("*.parquet"))
    if not files:
        raise SystemExit(f"No .parquet files under {meta_root}.")

    print(f"[info] reading {len(files)} parquet files ...")
    frames = []
    for f in files:
        try:
            frames.append(pd.read_parquet(f))
        except Exception as e:
            print(f"[warn] unreadable {f.name}: {e}")
    if not frames:
        raise SystemExit("No readable parquet files.")
    df = pd.concat(frames, ignore_index=True)
    cols = list(df.columns)

    rep = Report("load_metadata", data, args)
    rep.section("Parquet schema discovered")
    rep.stat("parquet_files", len(files))
    rep.stat("parquet_rows", len(df))
    rep.raw("parquet_columns", cols)
    rep.table("Columns present", ["column", "non_null", "example"],
              [[c, int(df[c].notna().sum()), str(df[c].dropna().iloc[0])[:60] if df[c].notna().any() else ""]
               for c in cols])

    mapping = {t: _find_column(cols, t) for t in COLUMN_CANDIDATES}
    if args.map:
        for pair in args.map:
            t, _, src = pair.partition("=")
            mapping[t.strip()] = src.strip()

    rep.section("Column mapping")
    rep.table("target <- source", ["target_column", "parquet_column", "status"],
              [[t, s or "-", "OK" if s else "NOT FOUND"] for t, s in mapping.items()])

    print("\n=== PARQUET COLUMNS ===")
    for c in cols:
        print(f"  {c}")
    print("\n=== MAPPING ===")
    for t, s in mapping.items():
        print(f"  {t:16s} <- {s or '(not found)'}")

    if args.inspect:
        print("\n=== SAMPLE ROW ===")
        if len(df):
            for k, v in df.iloc[0].items():
                print(f"  {k:24s} = {str(v)[:100]}")
        rep.note("Inspect mode: nothing written. Re-run without --inspect (add --map "
                 "target=source for any column mapped incorrectly).")
        rep.save()
        return

    if not mapping.get("case_id"):
        raise SystemExit(
            "Could not identify a case_id column. Re-run with --inspect, then pass e.g.\n"
            "  --map case_id=<the right column name>"
        )

    # ── Build the update payload ──────────────────────────────────────────
    id_col = mapping["case_id"]
    nc_col = mapping.get("neutral_citation")
    payload: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        rd = row._asdict() if hasattr(row, "_asdict") else dict(zip(df.columns, row))
        cid = _normalise_case_id(rd.get(id_col), args.id_suffix)
        if not cid:
            continue
        rec: dict[str, Any] = {"case_id": cid}
        for target in UPDATABLE:
            src = mapping.get(target)
            if not src or src not in rd:
                rec[target] = None
                continue
            v = rd[src]
            if target == "decision_date":
                rec[target] = _to_date(v)
            elif target == "acts_sections":
                rec[target] = _to_list(v)
            else:
                rec[target] = _clean(v)

        # Store BOTH citation forms, separated by " | ".
        # The bucket gives each case a reporter citation ("[2020] 4 S.C.R. 552") and a
        # neutral one ("2020 INSC 395"). A citing judgment may use either, so indexing
        # both roughly doubles the achievable resolution rate (extract_citations.py
        # reads every form present in this field).
        if nc_col and nc_col in rd:
            neutral = _clean(rd[nc_col])
            if neutral:
                rec["citation"] = f"{rec['citation']} | {neutral}" if rec.get("citation") else neutral
        if rec.get("citation"):
            rec["citation"] = rec["citation"][:200]     # column is VARCHAR(200)
        payload.append(rec)

    rep.stat("payload_rows", len(payload))
    filled = {t: sum(1 for r in payload if r.get(t) is not None) for t in UPDATABLE}
    rep.table("Values available per column", ["column", "rows_with_value", "share_of_payload"],
              [[t, n, f"{100*n/max(len(payload),1):.1f}%"] for t, n in filled.items()])

    if args.dry_run:
        rep.note("Dry run: nothing written to the database.")
        print("\n[dry-run] would update these columns:")
        for t, n in filled.items():
            print(f"  {t:16s} {n} rows")
        rep.save()
        return

    # ── Apply to Postgres ─────────────────────────────────────────────────
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url

    engine = create_async_engine(db_url)
    updated = 0
    unmatched = 0
    async with engine.begin() as conn:
        existing = {r[0] for r in (await conn.execute(sa_text("SELECT case_id FROM cases"))).fetchall()}
        print(f"[info] {len(existing)} cases in DB, {len(payload)} metadata rows")

        batch = [r for r in payload if r["case_id"] in existing]
        unmatched = len(payload) - len(batch)

        # Every bound parameter carries an explicit CAST.
        #
        # Without them, asyncpg raises "could not determine data type of parameter $N"
        # whenever a column is NULL for every row — Postgres cannot infer a type for an
        # untyped NULL inside COALESCE. This bites hardest on `acts_sections`, which the
        # AWS bucket does not publish at all, so it is NULL for all 7,100 rows. The
        # failure aborts the whole load and leaves the table untouched, which is easy to
        # miss because the script otherwise looks like it ran.
        stmt = sa_text("""
            UPDATE cases SET
                citation        = COALESCE(CAST(:citation        AS varchar), citation),
                bench           = COALESCE(CAST(:bench           AS text),    bench),
                decision_date   = COALESCE(CAST(:decision_date   AS date),    decision_date),
                disposal_nature = COALESCE(CAST(:disposal_nature AS varchar), disposal_nature),
                petitioner      = COALESCE(CAST(:petitioner      AS text),    petitioner),
                respondent      = COALESCE(CAST(:respondent      AS text),    respondent),
                acts_sections   = COALESCE(CAST(:acts_sections   AS text[]),  acts_sections),
                title           = CASE
                                    WHEN CAST(:title AS text) IS NOT NULL
                                     AND length(CAST(:title AS text)) > 5
                                    THEN CAST(:title AS text) ELSE title
                                  END
            WHERE case_id = CAST(:case_id AS varchar)
        """)
        if not batch:
            raise SystemExit(
                f"NO case_id MATCHED. {len(payload)} metadata rows, {len(existing)} DB rows, "
                f"zero overlap.\n"
                f"  metadata example: {payload[0]['case_id'] if payload else '(none)'}\n"
                f"  database example: {next(iter(existing), '(none)')}\n"
                "Adjust --id-suffix or --map case_id=<column>."
            )

        for i in range(0, len(batch), args.batch_size):
            chunk = batch[i: i + args.batch_size]
            try:
                await conn.execute(stmt, chunk)
            except Exception as e:
                # Fail loudly. A silent abort here leaves every downstream step
                # (citation graph, ground truth, every metric) quietly empty.
                raise SystemExit(
                    f"\nUPDATE FAILED on rows {i}-{i+len(chunk)}: {type(e).__name__}: {e}\n"
                    f"  first row of the failing chunk: {chunk[0]}\n"
                ) from e
            updated += len(chunk)
            print(f"[info] updated {updated}/{len(batch)} ...", end="\r")

    # Post-load verification — this is what makes the next steps possible or not.
    async with engine.connect() as conn:
        checks = {}
        for col in ("citation", "bench", "decision_date", "disposal_nature", "acts_sections"):
            n = (await conn.execute(
                sa_text(f"SELECT count(*) FROM cases WHERE {col} IS NOT NULL"))).scalar() or 0
            checks[col] = int(n)
        total = (await conn.execute(sa_text("SELECT count(*) FROM cases"))).scalar() or 0
    await engine.dispose()

    rep.section("Post-load verification")
    rep.stat("rows_updated", updated)
    rep.stat("metadata_rows_without_matching_case", unmatched)
    rep.table("Non-NULL after load", ["column", "rows", "share_of_cases"],
              [[c, n, f"{100*n/max(total,1):.1f}%"] for c, n in checks.items()])
    if checks.get("citation", 0) == 0:
        rep.note("CRITICAL: cases.citation is still empty. extract_citations.py cannot "
                 "resolve anything and ground truth cannot be built. Re-run with --inspect "
                 "and map the citation column explicitly.")
    if checks.get("bench", 0) == 0:
        rep.note("cases.bench is still empty — the 0.20 bench-size authority signal "
                 "remains a constant.")

    print(f"\n[done] updated {updated} rows; {unmatched} metadata rows had no matching case_id")
    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Load Parquet metadata into the cases table")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--database-url", type=str, default=None)
    ap.add_argument("--batch-size", type=int, default=500)
    ap.add_argument("--inspect", action="store_true", help="print schema and exit")
    ap.add_argument("--dry-run", action="store_true", help="build payload but do not write")
    ap.add_argument("--id-suffix", type=str, default="_EN",
                    help="language suffix appended to the parquet `path` to form the "
                         "corpus case_id (default _EN, matching english.tar filenames)")
    ap.add_argument("--map", action="append", default=[],
                    help="override a mapping, e.g. --map citation=neutral_cite (repeatable)")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
