"""
Build realistic query sets in several length regimes.

WHY THIS EXISTS
The first evaluation used 2,500-character judgment excerpts as queries. That is not
how anyone uses the system: a lawyer types a sentence, not three paragraphs. Long
queries also flatter lexical matching (more terms, more evidence) and penalise the
dense channel twice over, because get_embedding truncates the QUERY to 1,000
characters as well as the document. Measuring only that regime tells us little.

This produces the same queries in four styles, sharing one qrels file, so retrieval
can be measured as a function of query length and form:

  long      ~2500 chars   the original regime, kept for comparison
  medium    ~600 chars    a detailed paragraph
  short     ~200 chars    a topical description — the realistic default
  keyword   ~90 chars     statute references + salient legal terms, i.e. how
                          practitioners actually search

OCR CLEANING
The corpus is extracted from SCR PDFs, which carry margin markers (isolated A-H
letters), running headers (CASE NAME v. OTHER 353) and page numbers. Left in, these
become query terms that match nothing and dilute the signal. All four styles are
cleaned; `long` is cleaned too, so the comparison against the original run isolates
length rather than confounding it with noise.

Leakage controls are unchanged: citation strings and case names are stripped from
every style (Q48).

Usage (from Backend/):
    python -m scripts.eval.build_query_sets --data-dir ../data
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics as st
from pathlib import Path

from scripts.lib.citations import find_citations, strip_leakage
from scripts.lib.report import Report

# ── OCR noise specific to this corpus ────────────────────────────────────────
_MARGIN_LETTER = re.compile(r"(?<=\s)[A-H](?=\s)")          # SCR margin markers
_RUNNING_HEADER = re.compile(
    r"[A-Z][A-Z .,&'()/-]{8,}\s+(?:v\.?|vs\.?|versus)\s+[A-Z][A-Z .,&'()/-]{8,}\s*\d*",
    re.I,
)
_PAGE_NUM = re.compile(r"(?<=\s)\d{1,4}(?=\s)")
_PARA_NUM = re.compile(r"^\s*\d{1,3}\.\s+")

# Statutory references — the highest-signal tokens a practitioner would type
_STATUTE = re.compile(
    r"(?:Article|Articles|Section|Sections|Sec\.?|Art\.?|Order|Rule|Regulation)\s*"
    r"\d+[A-Z]?(?:\s*\(\s*\d+\s*\))?"
    r"(?:\s+(?:of|,)\s+the\s+[A-Z][A-Za-z ]{3,50}?\s+(?:Act|Code|Constitution|Rules))?",
    re.I,
)
_ACT_NAME = re.compile(
    r"\b(?:[A-Z][A-Za-z]+\s+){1,5}(?:Act|Code|Constitution)\b(?:,?\s*\d{4})?"
)

_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "been", "were",
    "they", "their", "what", "when", "where", "which", "under", "into", "upon", "also",
    "such", "case", "court", "high", "supreme", "india", "indian", "appeal", "appellant",
    "respondent", "petitioner", "learned", "counsel", "judgment", "order", "hon", "ble",
    "shall", "would", "could", "should", "said", "same", "any", "all", "not", "but",
    "was", "are", "his", "her", "him", "she", "who", "whom", "then", "than", "there",
    "here", "made", "make", "held", "view", "para", "paragraph", "page", "vol",
}


def clean_ocr(text: str) -> str:
    """Strip SCR margin markers, running headers, page numbers, collapse whitespace."""
    t = _RUNNING_HEADER.sub(" ", text)
    t = _MARGIN_LETTER.sub(" ", t)
    t = _PAGE_NUM.sub(" ", t)
    t = re.sub(r"[^\S\n]+", " ", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;:])\s+|\s+[-–—]\s+", text)
    return [_PARA_NUM.sub("", p).strip() for p in parts if len(p.strip()) > 25]


def make_query(issues: str, facts: str, style: str) -> str:
    """Build one query in the requested style. Leakage stripping applied last."""
    issues_c = clean_ocr(issues or "")
    facts_c = clean_ocr(facts or "")
    # Prefer the issues section: in SCR judgments it is a human-written headnote and
    # reads like a topical description of the legal question.
    body = issues_c if len(issues_c) > 150 else facts_c
    if not body:
        body = facts_c or issues_c

    if style == "long":
        out = (facts_c[:1500] + " " + issues_c[:1000]).strip()
    elif style == "medium":
        out = " ".join(_sentences(body))[:600]
    elif style == "short":
        out = " ".join(_sentences(body))[:200]
    elif style == "keyword":
        source = f"{issues_c} {facts_c}"
        statutes = [m.group(0).strip() for m in _STATUTE.finditer(source)][:2]
        acts = [m.group(0).strip() for m in _ACT_NAME.finditer(source)][:1]
        words = re.findall(r"\b[a-zA-Z]{5,}\b", body.lower())
        seen: set[str] = set()
        terms: list[str] = []
        for w in words:
            if w in _STOP or w in seen:
                continue
            seen.add(w)
            terms.append(w)
            if len(terms) >= 10:
                break
        out = " ".join(dict.fromkeys(statutes + acts + terms))[:160]
    else:
        raise ValueError(style)

    return strip_leakage(out)


async def run(args: argparse.Namespace) -> None:
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    data = Path(args.data_dir)
    eval_dir = data / "eval"
    base = json.loads((eval_dir / "queries.json").read_text(encoding="utf-8"))
    qids = [q["qid"] for q in base]
    split_of = {q["qid"]: q.get("split", "test") for q in base}
    year_of = {q["qid"]: q.get("year", 0) for q in base}

    db_url = args.database_url
    if not db_url:
        from app.core.config import get_settings
        db_url = get_settings().database_url

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        rows = (await conn.execute(sa_text(
            "SELECT case_id, issues_text, facts_text FROM cases WHERE case_id = ANY(:ids)"
        ), {"ids": qids})).fetchall()
    await engine.dispose()
    src = {r[0]: (r[1] or "", r[2] or "") for r in rows}

    rep = Report("build_query_sets", data, args)
    rep.section("Query sets")
    rep.note("Same qrels for every style — only the query text changes, so differences "
             "in the results are attributable to query form alone.")

    summary = []
    for style in ("long", "medium", "short", "keyword"):
        out = []
        lengths = []
        residual = 0
        for qid in qids:
            issues, facts = src.get(qid, ("", ""))
            text = make_query(issues, facts, style)
            if len(text) < args.min_chars:
                continue
            if find_citations(text, mark_discussed=False).citations:
                residual += 1
            lengths.append(len(text))
            out.append({"qid": qid, "text": text, "year": year_of.get(qid, 0),
                        "split": split_of.get(qid, "test"), "style": style})
        path = eval_dir / f"queries_{style}.json"
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        words = [len(q["text"].split()) for q in out]
        summary.append([style, len(out),
                        round(st.mean(lengths), 0) if lengths else 0,
                        round(st.mean(words), 1) if words else 0, residual])
        rep.stat(f"{style}_queries", len(out))
        rep.stat(f"{style}_mean_chars", round(st.mean(lengths), 0) if lengths else 0)
        rep.stat(f"{style}_mean_words", round(st.mean(words), 1) if words else 0)
        rep.stat(f"{style}_residual_leakage", residual)

    rep.table("Query sets produced",
              ["style", "queries", "mean chars", "mean words", "residual leakage"], summary)
    if any(r[4] for r in summary):
        rep.note("WARNING: residual citations found. Fix scripts/lib/citations.py before "
                 "running the evaluation.")

    print(f"\n{'style':10s}{'queries':>9s}{'chars':>8s}{'words':>8s}{'leak':>6s}")
    for r in summary:
        print(f"{r[0]:10s}{r[1]:9d}{r[2]:8.0f}{r[3]:8.1f}{r[4]:6d}")

    # Show one example of each so the query form is inspectable.
    print("\n--- examples (same case, four styles) ---")
    ex = qids[0]
    issues, facts = src.get(ex, ("", ""))
    for style in ("keyword", "short", "medium"):
        print(f"\n[{style}] {make_query(issues, facts, style)[:300]}")

    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Build query sets in several length regimes")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--database-url", type=str, default=None)
    ap.add_argument("--min-chars", type=int, default=40)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
