"""
FEASIBILITY PROBE — run this before building anything else.

The entire ground-truth plan rests on one assumption:
    judgments cite earlier judgments, and enough of those cited cases are
    INSIDE our corpus to serve as relevance labels.

This script tests that assumption on a sample, in about a minute, and tells you
whether to proceed, widen the corpus, or switch to a different labelling strategy.

It needs NO database and NO metadata load — it works directly off the extracted
text files, so it can be run the moment the corpus exists.

Usage (from Backend/):
    python -m scripts.eval.probe_citations --data-dir ../data --sample 200

Reads:  <data-dir>/processed/*.txt
Writes: <data-dir>/reports/probe_citations.{json,md}

Interpreting the headline number (in-corpus resolution rate):
    > 20%   Excellent — proceed with citation-derived ground truth.
    5-20%   Workable — proceed, but expect few labels per query; lead with nDCG/MRR.
    1-5%    Marginal — widen the corpus year range before continuing.
    < 1%    Does not work — go to the fallbacks in IMPLEMENTATION_PLAN.md Step 4.
"""
from __future__ import annotations

import argparse
import random
import re
from collections import Counter
from pathlib import Path

from scripts.lib.citations import find_citations, name_key
from scripts.lib.report import Report


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe citation-derived ground-truth feasibility")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--sample", type=int, default=200, help="documents to sample")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    txt_dir = data_dir / "processed"
    if not txt_dir.exists():
        raise SystemExit(f"No extracted text at {txt_dir}. Run extract_text.py first.")

    all_txt = sorted(txt_dir.glob("*.txt"))
    if not all_txt:
        raise SystemExit(f"No .txt files in {txt_dir}.")

    # The corpus universe: every case_id we could possibly resolve a citation TO.
    corpus_ids = {p.stem for p in all_txt}
    corpus_years = Counter()
    for cid in corpus_ids:
        m = re.match(r"^(\d{4})_", cid)
        if m:
            corpus_years[int(m.group(1))] += 1

    rng = random.Random(args.seed)
    sample = rng.sample(all_txt, min(args.sample, len(all_txt)))

    rep = Report("probe_citations", data_dir, args)
    rep.section("Corpus universe")
    rep.stat("corpus_documents", len(corpus_ids), "documents available as citation targets")
    if corpus_years:
        rep.stat("corpus_year_min", min(corpus_years), "earliest year")
        rep.stat("corpus_year_max", max(corpus_years), "latest year")
        rep.stat("corpus_year_span", max(corpus_years) - min(corpus_years) + 1, "year span")
        rep.table(
            "Documents per year",
            ["year", "documents"],
            [[y, corpus_years[y]] for y in sorted(corpus_years)],
        )

    # ── Scan the sample ───────────────────────────────────────────────────
    total_cites = 0
    total_out_of_scope = 0
    total_names = 0
    discussed = 0
    per_doc_counts: list[int] = []
    cited_years = Counter()
    reporter_mix = Counter()
    docs_with_zero = 0

    # Target-year resolution: for each cited YEAR, is that year in our corpus at all?
    # This is a strict UPPER BOUND on in-corpus resolution — we cannot resolve a
    # citation to a year we never ingested. It requires no metadata, which is the
    # point: it is measurable today.
    resolvable_by_year = 0

    for path in sample:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        res = find_citations(text)
        n = len(res.citations)
        per_doc_counts.append(n)
        total_cites += n
        total_out_of_scope += res.out_of_scope
        total_names += len(res.case_names)
        if n == 0:
            docs_with_zero += 1
        for c in res.citations:
            cited_years[c.year] += 1
            reporter_mix[c.reporter] += 1
            if c.discussed:
                discussed += 1
            if c.year in corpus_years:
                resolvable_by_year += 1

    n_sampled = len(per_doc_counts)
    mean_cites = total_cites / max(n_sampled, 1)
    upper_bound = 100 * resolvable_by_year / max(total_cites, 1)

    rep.section("Citation extraction on the sample")
    rep.stat("documents_sampled", n_sampled)
    rep.stat("sc_citations_found", total_cites, "in-scope Supreme Court citations")
    rep.stat("mean_citations_per_document", round(mean_cites, 2))
    rep.stat("documents_with_zero_citations", docs_with_zero)
    rep.stat("out_of_scope_citations", total_out_of_scope, "High Court / other reporters (excluded)")
    rep.stat("case_name_mentions", total_names, "'X v. Y' strings (fallback matching)")
    rep.stat("discussed_fraction", round(discussed / max(total_cites, 1), 4),
             "cited AND discussed -> grade 2 under graded relevance (Q52)")

    if reporter_mix:
        rep.table("Reporter mix", ["reporter", "count"],
                  [[k, v] for k, v in reporter_mix.most_common()])

    rep.section("HEADLINE — can we build ground truth from citations?")
    rep.stat("target_year_in_corpus_pct", round(upper_bound, 2),
             "% of citations whose target YEAR exists in the corpus (UPPER BOUND)")

    if cited_years:
        span = [[y, cited_years[y], "yes" if y in corpus_years else "NO"]
                for y in sorted(cited_years, reverse=True)[:40]]
        rep.table("Most-cited years (top 40) — 'in corpus?' drives everything",
                  ["cited_year", "times_cited", "in_corpus"], span)
        missing = sorted({y for y in cited_years if y not in corpus_years})
        if missing:
            rep.stat("cited_years_missing_from_corpus", len(missing))
            rep.raw("missing_years", missing)

    # ── Verdict ───────────────────────────────────────────────────────────
    if upper_bound > 20:
        verdict = ("EXCELLENT — proceed with citation-derived ground truth "
                   "(IMPLEMENTATION_PLAN.md Step 3 onwards).")
    elif upper_bound > 5:
        verdict = ("WORKABLE — proceed, but expect few labels per query. "
                   "Lead with nDCG@10 and MRR rather than P@10 (Q51).")
    elif upper_bound > 1:
        verdict = ("MARGINAL — widen the corpus year range before continuing. "
                   "The years listed as 'NO' above are what you are missing.")
    else:
        verdict = ("DOES NOT WORK as-is — go to the fallbacks in "
                   "IMPLEMENTATION_PLAN.md Step 4 (existing benchmark, or hand annotation).")

    rep.note(f"VERDICT: {verdict}")
    rep.note(
        "This percentage is an UPPER BOUND, not the final answer. It only checks that the "
        "cited YEAR exists in the corpus. Exact citation-string matching (Step 3) will be "
        "lower, because cases.citation must also be populated and must match. Treat anything "
        "under ~10% here as a warning that the real rate will be very small."
    )

    print(f"\n{'='*72}")
    print(f"  Documents sampled ............ {n_sampled}")
    print(f"  SC citations found ........... {total_cites}  ({mean_cites:.1f}/doc)")
    print(f"  Target year in corpus ........ {upper_bound:.1f}%   <-- HEADLINE (upper bound)")
    print(f"  VERDICT: {verdict}")
    print(f"{'='*72}")
    rep.save()


if __name__ == "__main__":
    main()
