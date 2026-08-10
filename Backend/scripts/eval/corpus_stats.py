"""
Corpus statistics — answers Q42, Q44, Q46, and the measurable half of Q5.

Produces, in one run:
  * the ingestion attrition chain (PDFs -> text -> segmented -> embedded -> indexed -> DB)
  * document length distribution, in words and in encoder tokens
  * the FRACTION OF EACH DOCUMENT THAT SURVIVES the 1000-char embedding truncation (Q9)
  * the regex vs positional-fallback segmentation split (Q5)
  * per-year corpus distribution (Q42)

No LLM, no network. The database is optional — pass --database-url to include the
final row of the attrition chain, omit it to skip that row.

Usage (from Backend/):
    python -m scripts.eval.corpus_stats --data-dir ../data
    python -m scripts.eval.corpus_stats --data-dir ../data --database-url postgresql+asyncpg://verdicto:verdicto_secret@localhost:5433/verdicto
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics as st
from collections import Counter
from pathlib import Path

from scripts.lib.report import Report

TRUNCATION_CHARS = 1000  # embedding_service.py:27 — text[:1000]


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


async def _db_count(database_url: str) -> tuple[int, int]:
    """Return (cases, citations) row counts. Returns (-1, -1) on failure."""
    try:
        from sqlalchemy import text as sa_text
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(database_url)
        async with engine.connect() as conn:
            cases = (await conn.execute(sa_text("SELECT count(*) FROM cases"))).scalar() or 0
            try:
                cites = (await conn.execute(sa_text("SELECT count(*) FROM citations"))).scalar() or 0
            except Exception:
                cites = 0
        await engine.dispose()
        return int(cases), int(cites)
    except Exception as e:
        print(f"[warn] database count failed: {e}")
        return -1, -1


def main() -> None:
    ap = argparse.ArgumentParser(description="Corpus statistics for the paper")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--database-url", type=str, default=None,
                    help="Optional; adds the DB row of the attrition chain")
    ap.add_argument("--token-sample", type=int, default=500,
                    help="documents to tokenise for the token-length distribution")
    ap.add_argument("--skip-tokens", action="store_true",
                    help="skip tokenisation (avoids loading sentence-transformers)")
    args = ap.parse_args()

    data = Path(args.data_dir)
    rep = Report("corpus_stats", data, args)

    # ── 1. Attrition chain (Q46) ──────────────────────────────────────────
    pdfs = list((data / "raw" / "pdfs").glob("*.pdf")) if (data / "raw" / "pdfs").exists() else []
    txts = list((data / "processed").glob("*.txt"))
    segs = list((data / "processed" / "segmented").glob("*.json"))
    npys = list((data / "embeddings").glob("*.npy"))

    index_n = 0
    mapping_n = 0
    idx_path = data / "index" / "cases.index"
    map_path = data / "index" / "cases_mapping.json"
    if idx_path.exists():
        try:
            import faiss
            index_n = faiss.read_index(str(idx_path)).ntotal
        except Exception as e:
            print(f"[warn] could not read FAISS index: {e}")
    if map_path.exists():
        try:
            mapping_n = len(json.loads(map_path.read_text(encoding="utf-8")))
        except Exception:
            pass

    db_cases = db_cites = -1
    if args.database_url:
        db_cases, db_cites = asyncio.run(_db_count(args.database_url))

    chain = [
        ["1. PDFs downloaded", len(pdfs)],
        ["2. Text extracted (.txt)", len(txts)],
        ["3. Segmented (.json)", len(segs)],
        ["4. Embedded (.npy)", len(npys)],
        ["5. Vectors in FAISS index", index_n],
        ["6. Entries in FAISS mapping", mapping_n],
    ]
    if db_cases >= 0:
        chain.append(["7. Rows in `cases` table", db_cases])
        chain.append(["8. Rows in `citations` table", db_cites])

    rep.section("Ingestion attrition chain (Q46)")
    rep.table("Documents surviving each stage", ["stage", "count"], chain)
    for label, val in chain:
        rep.stat(re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_"), val, label)

    if index_n and mapping_n and index_n != mapping_n:
        rep.note("MISMATCH: FAISS index size != mapping size. The case_id -> vector mapping "
                 "is broken; retrieval will return wrong case_ids. Rebuild the index.")
    if db_cases >= 0 and index_n and db_cases != index_n:
        rep.note(f"MISMATCH: {db_cases} rows in `cases` but {index_n} vectors indexed. "
                 "populate_db.py and build_faiss_index.py saw different file sets. "
                 "Retrieval can return case_ids absent from the DB (they will be dropped silently).")

    # ── 2. Segmentation method split (Q5) ─────────────────────────────────
    methods = Counter()
    empty_sections = Counter()
    for p in segs:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            methods["unreadable"] += 1
            continue
        methods[d.get("segmentation_method", "missing")] += 1
        for k in ("facts", "issues", "reasoning", "outcome"):
            if not (d.get(k) or "").strip():
                empty_sections[k] += 1

    if methods:
        tot = sum(methods.values())
        rep.section("Segmentation quality (Q5) — no annotation required")
        rep.table("Segmentation method",
                  ["method", "documents", "share"],
                  [[k, v, f"{100*v/tot:.1f}%"] for k, v in methods.most_common()])
        fb = methods.get("heuristic_fallback", 0)
        rep.stat("fallback_rate_pct", round(100 * fb / max(tot, 1), 2),
                 "documents cut into equal quarters rather than segmented (Q6)")
        rep.table("Documents with an EMPTY section",
                  ["section", "documents", "share"],
                  [[k, empty_sections.get(k, 0), f"{100*empty_sections.get(k,0)/max(tot,1):.1f}%"]
                   for k in ("facts", "issues", "reasoning", "outcome")])
        rep.note("The fallback rate is the honest ceiling on structural quality. A "
                 "fallback document presents its arbitrary second quarter to the Debate "
                 "agent as 'the legal issues of the case'.")

    # ── 3. Document lengths + truncation loss (Q44, Q9) ────────────────────
    word_lens: list[int] = []
    for p in txts:
        try:
            word_lens.append(len(p.read_text(encoding="utf-8", errors="ignore").split()))
        except Exception:
            continue

    if word_lens:
        rep.section("Document length (Q44)")
        rep.stat("documents_measured", len(word_lens))
        rep.stat("words_mean", round(st.mean(word_lens), 1))
        rep.stat("words_median", round(st.median(word_lens), 1))
        rep.stat("words_p10", round(_quantile(word_lens, 0.10), 1))
        rep.stat("words_p90", round(_quantile(word_lens, 0.90), 1))
        rep.stat("words_max", max(word_lens))

    # Fraction of the concatenated segments that survives truncation
    fractions: list[float] = []
    combined_lens: list[int] = []
    for p in segs:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        full = " ".join((d.get(k) or "") for k in ("facts", "issues", "reasoning", "outcome")).strip()
        if not full:
            continue
        combined_lens.append(len(full))
        fractions.append(min(TRUNCATION_CHARS, len(full)) / len(full))

    if fractions:
        rep.section("Embedding truncation loss (Q9) — quantifies the key limitation")
        rep.stat("truncation_chars", TRUNCATION_CHARS, "embedding_service.py:27 -> text[:1000]")
        rep.stat("mean_fraction_embedded_pct", round(100 * st.mean(fractions), 3))
        rep.stat("median_fraction_embedded_pct", round(100 * st.median(fractions), 3))
        rep.stat("docs_fully_embedded_pct",
                 round(100 * sum(1 for f in fractions if f >= 1.0) / len(fractions), 2),
                 "documents short enough to be embedded in full")
        rep.stat("combined_text_chars_median", round(st.median(combined_lens), 0))
        rep.note("Each judgment is represented in the vector space by approximately its "
                 "first paragraph of facts. Issues, reasoning and outcome reach the vector "
                 "only for documents whose facts section is under 1000 characters.")

    # ── 4. Encoder token lengths (Q44) ────────────────────────────────────
    if not args.skip_tokens and segs:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            tok = model.tokenizer
            sample = segs[: args.token_sample]
            tok_lens = []
            for p in sample:
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                full = " ".join((d.get(k) or "") for k in
                                ("facts", "issues", "reasoning", "outcome")).strip()
                if full:
                    tok_lens.append(len(tok(full, truncation=False)["input_ids"]))
            if tok_lens:
                rep.section("Encoder tokens (all-MiniLM-L6-v2, 256-token limit)")
                rep.stat("token_sample_size", len(tok_lens))
                rep.stat("tokens_mean", round(st.mean(tok_lens), 1))
                rep.stat("tokens_median", round(st.median(tok_lens), 1))
                rep.stat("tokens_p90", round(_quantile(tok_lens, 0.90), 1))
                rep.stat("docs_over_256_tokens_pct",
                         round(100 * sum(1 for t in tok_lens if t > 256) / len(tok_lens), 2),
                         "documents exceeding the encoder limit")
        except Exception as e:
            print(f"[warn] tokenisation skipped: {e}")

    # ── 5. Year distribution (Q42) ────────────────────────────────────────
    years = Counter()
    for p in segs or txts:
        m = re.match(r"^(\d{4})_", p.stem)
        if m:
            years[int(m.group(1))] += 1
    if years:
        rep.section("Corpus coverage (Q42)")
        rep.stat("year_min", min(years))
        rep.stat("year_max", max(years))
        rep.stat("distinct_years", len(years))
        rep.table("Documents per year", ["year", "documents"],
                  [[y, years[y]] for y in sorted(years)])
        rep.note("`year` is parsed from the filename prefix, i.e. the bucket's partition "
                 "year, which may differ from the decision date. Loading decision_date "
                 "(load_metadata.py) upgrades any temporal split to day granularity.")

    rep.save()


if __name__ == "__main__":
    main()
