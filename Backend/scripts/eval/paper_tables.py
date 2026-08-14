"""
Assemble every measurement report into the paper's tables.

Reads <data-dir>/reports/*.json and emits, in one place, every number the paper needs:
corpus construction, ground truth, the citation graph, the per-regime retrieval tables,
the cross-regime significance table, and the agent-level characterisation.

Anything not backed by a report file prints as TODO and is counted at the end. Nothing
here is hard-coded — if a value is missing, the fix is to run the measurement, not to
type the number in.

Usage (from Backend/):
    python -m scripts.eval.paper_tables --data-dir ../data
    python -m scripts.eval.paper_tables --data-dir ../data --latex
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# The four query regimes, shortest first — the axis the v3 result depends on.
REGIMES = [("_keyword", "keyword", "14w"), ("_short", "short", "33w"),
           ("_medium", "medium", "96w"), ("_long", "long", "360w")]

# Conditions in the order the paper's retrieval table lists them.
RETRIEVAL_ROWS = [
    ("bm25s",       r"BM25$_{\mathrm{sum}}$ title+facts+issues, $k_1{=}1.2$"),
    ("bm25_full",   r"BM25$_{\mathrm{full}}$ full text, $k_1{=}1.2$"),
    ("bm25_grid",   r"BM25$_{\mathrm{tuned}}$ full text, $k_1{=}12$, $b{=}0.65$"),
    ("cite_prop",   r"CP\phantom{ii} citation propagation alone"),
    ("hybrid_cite", r"\textbf{HC} \textbf{RRF(BM25}$_{\mathrm{tuned}}$\textbf{, CP)}"),
]
METRICS = ["P@1", "P@5", "R@20", "RR", "nDCG@10", "P@10", "nDCG@20"]


def _load(reports: Path, name: str) -> dict[str, Any] | None:
    p = reports / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _stat(rep: dict[str, Any] | None, key: str, default: Any = "TODO") -> Any:
    if not rep:
        return default
    return rep.get("stats", {}).get(key, default)


def _table(rep: dict[str, Any] | None, needle: str) -> dict[str, dict[str, str]]:
    """Pull a report table into {row_key: {column: value}}."""
    out: dict[str, dict[str, str]] = {}
    if not rep:
        return out
    for block in rep.get("blocks", []):
        if block.get("type") == "table" and needle in block.get("title", "").lower():
            cols = block["columns"]
            for row in block["rows"]:
                out[str(row[0])] = {c: row[i] for i, c in enumerate(cols) if i > 0}
    return out


def _pct(v: Any) -> str:
    try:
        return f"{float(v) * 100:.2f}"
    except (TypeError, ValueError):
        return "TODO"


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble paper tables from reports")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--latex", action="store_true", help="emit LaTeX table bodies")
    args = ap.parse_args()

    reports = Path(args.data_dir) / "reports"
    out_lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        out_lines.append(s)

    corpus = _load(reports, "corpus_stats")
    seg = _load(reports, "segment_text")
    extract = _load(reports, "extract_text")
    dedup = _load(reports, "dedup")
    cites = _load(reports, "extract_citations")
    golden = _load(reports, "build_golden_set")
    qsets = _load(reports, "build_query_sets")
    audit = _load(reports, "audit_cite_prop")
    trace = _load(reports, "trace_stats")
    meta = _load(reports, "load_metadata")

    emit("=" * 92)
    emit("  PAPER VALUES — regenerated from data/reports/")
    emit("=" * 92)

    # ── Corpus construction ───────────────────────────────────────────────
    emit("\n## Corpus construction\n")
    for label, val in [
        ("PDFs downloaded", _stat(corpus, "1_pdfs_downloaded")),
        ("Text extracted", _stat(corpus, "2_text_extracted_txt")),
        ("Extraction failures", _stat(extract, "failed")),
        ("Segmented, heading-based", _stat(seg, "regex_segmented")),
        ("Segmented, positional fallback", _stat(seg, "positional_fallback")),
        ("Fallback rate (%)", _stat(seg, "fallback_rate_pct")),
        ("Embedded", _stat(corpus, "4_embedded_npy")),
        ("Vectors in FAISS index", _stat(corpus, "5_vectors_in_faiss_index")),
        ("Rows in cases table", _stat(corpus, "7_rows_in_cases_table")),
        ("Rows in citations table", _stat(corpus, "8_rows_in_citations_table")),
    ]:
        emit(f"  {label:36s} {val}")

    emit("\n## Corpus description\n")
    for label, val in [
        ("Year range", f"{_stat(corpus,'year_min')}-{_stat(corpus,'year_max')}"),
        ("Distinct years", _stat(corpus, "distinct_years")),
        ("Words mean / median", f"{_stat(corpus,'words_mean')} / {_stat(corpus,'words_median')}"),
        ("Words P10 / P90 / max",
         f"{_stat(corpus,'words_p10')} / {_stat(corpus,'words_p90')} / {_stat(corpus,'words_max')}"),
        ("Chars mean / median",
         f"{_stat(extract,'chars_mean')} / {_stat(extract,'chars_median')}"),
        ("MiniLM tokens mean / median",
         f"{_stat(corpus,'tokens_mean')} / {_stat(corpus,'tokens_median')}"),
        ("Docs over the 256-token limit (%)", _stat(corpus, "docs_over_256_tokens_pct")),
        ("Truncation applied (chars)", _stat(corpus, "truncation_chars")),
        ("Mean fraction embedded (%)", _stat(corpus, "mean_fraction_embedded_pct")),
        ("Median fraction embedded (%)", _stat(corpus, "median_fraction_embedded_pct")),
        ("Docs embedded in full (%)", _stat(corpus, "docs_fully_embedded_pct")),
        ("Near-duplicate pairs >=0.90", _stat(dedup, "pairs_at_0_9")),
        ("Near-duplicate pairs >=0.95", _stat(dedup, "pairs_at_0_95")),
        ("Near-duplicate pairs >=0.98", _stat(dedup, "pairs_at_0_98")),
        ("Metadata rows updated", _stat(meta, "rows_updated")),
    ]:
        emit(f"  {label:36s} {val}")

    # ── Citation graph ────────────────────────────────────────────────────
    emit("\n## Citation graph\n")
    for label, val in [
        ("SC citations found", _stat(cites, "sc_citations_found")),
        ("Mean citations per document", _stat(cites, "mean_citations_per_document")),
        ("Out-of-scope (High Court etc.)", _stat(cites, "out_of_scope_citations")),
        ("Resolved by canonical citation", _stat(cites, "resolved_by_canonical_citation")),
        ("Resolved by case name", _stat(cites, "resolved_by_case_name")),
        ("Unresolved", _stat(cites, "unresolved")),
        ("IN-CORPUS RESOLUTION RATE (%)", _stat(cites, "in_corpus_resolution_rate_pct")),
        ("Graph nodes / edges",
         f"{_stat(cites,'graph_nodes')} / {_stat(cites,'edges')}"),
        ("Docs with >=1 outgoing edge", _stat(cites, "documents_with_at_least_one_edge")),
        ("Mean out-degree", _stat(cites, "mean_out_degree")),
    ]:
        emit(f"  {label:36s} {val}")

    # ── Evaluation set ────────────────────────────────────────────────────
    emit("\n## Evaluation set\n")
    for label, val in [
        ("Cases with >= min citations", _stat(golden, "cases_with_at_least_min_citations")),
        ("Q (query cases)", _stat(golden, "Q_queries")),
        ("Total relevance judgements", _stat(golden, "total_judgements")),
        ("Mean relevant per query", _stat(golden, "mean_relevant_per_query")),
        ("Median relevant per query", _stat(golden, "median_relevant_per_query")),
        ("Dev queries", f"{_stat(golden,'dev_queries')} ({_stat(golden,'dev_year_range')})"),
        ("Test queries", f"{_stat(golden,'test_queries')} ({_stat(golden,'test_year_range')})"),
        ("Residual leakage (must be 0)", _stat(golden, "queries_with_residual_citations")),
    ]:
        emit(f"  {label:36s} {val}")

    emit("\n  Query regimes (mean words / mean chars, leakage must be 0):")
    for _, name, _ in REGIMES:
        emit(f"    {name:10s} {_stat(qsets, f'{name}_mean_words'):>8} w  "
             f"{_stat(qsets, f'{name}_mean_chars'):>8} ch  "
             f"leakage={_stat(qsets, f'{name}_residual_leakage')}")

    # ── Retrieval tables, one per regime ──────────────────────────────────
    emit("\n" + "=" * 92)
    emit("  RETRIEVAL — test split, one block per query regime (values x100)")
    emit("=" * 92)
    for tag, name, length in REGIMES:
        score = _load(reports, f"score{tag}")
        agg = _table(score, "effectiveness")
        emit(f"\n## {name} ({length})"
             + ("" if agg else "   *** NO score%s.json — run the sweep ***" % tag))
        if not agg:
            emit("  TODO")
            continue
        emit(f"  {'condition':14s}" + "".join(f"{m:>10s}" for m in METRICS))
        for key, _ in RETRIEVAL_ROWS:
            vals = agg.get(key)
            cells = ("".join(f"{_pct(vals.get(m)):>10s}" for m in METRICS)
                     if vals else f"{'TODO':>10s}")
            emit(f"  {key:14s}{cells}")

    # ── Dev split at the final configuration ──────────────────────────────
    dev = _load(reports, "score_devf")
    emit("\n## Dev split at the final configuration (parameter selection lives here)\n")
    dev_agg = _table(dev, "effectiveness")
    if dev_agg:
        emit(f"  {'condition':14s}" + "".join(f"{m:>10s}" for m in METRICS))
        for key, _ in RETRIEVAL_ROWS:
            vals = dev_agg.get(key)
            if vals:
                emit(f"  {key:14s}" + "".join(f"{_pct(vals.get(m)):>10s}" for m in METRICS))
        for cond, row in _table(dev, "significance").items():
            if cond == "hybrid_cite":
                emit(f"\n  hybrid_cite vs bm25_grid: {row}")
    else:
        emit("  TODO — run score with --tag _devf --split dev")

    # ── Cross-regime significance ─────────────────────────────────────────
    emit("\n" + "=" * 92)
    emit("  SIGNIFICANCE — hybrid_cite vs bm25_grid (tuned BM25), paired bootstrap")
    emit("=" * 92)
    sig_path = reports / "regime_significance.json"
    if sig_path.exists():
        sig = json.loads(sig_path.read_text(encoding="utf-8"))
        for label, rows in sig.items():
            emit(f"\n## {label}")
            emit(f"  {'metric':10s}{'system':>9s}{'baseline':>10s}{'delta':>10s}"
                 f"{'95% CI':>22s}{'P(better)':>11s}  sig")
            for r in rows:
                ci = f"[{r['ci_low']:+.4f}, {r['ci_high']:+.4f}]"
                emit(f"  {r['metric']:10s}{r['hybrid_cite']:>9.4f}{r['bm25_grid']:>10.4f}"
                     f"{r['delta']:>+10.4f}{ci:>22s}{r['p_better']:>11.3f}"
                     f"  {'YES' if r['significant'] else 'no'}")
    else:
        emit("  TODO — regime_significance.json not found")

    # ── Leakage audit ─────────────────────────────────────────────────────
    emit("\n## Leakage audit — cite_prop\n")
    emit(f"  {'Split audited':36s} {_stat(audit, 'split')}")
    emit(f"  {'Queries audited':36s} {_stat(audit, 'queries_audited')}")
    emit(f"  {'VERDICT (must be CLEAN)':36s} {_stat(audit, 'VERDICT')}")
    emit(f"  {'Coverage (%)':36s} {_stat(audit, 'coverage_pct')}")
    emit(f"  {'Mean voting edges per query':36s} {_stat(audit, 'mean_voting_edges_per_query')}")

    # ── Agent-level characterisation ──────────────────────────────────────
    emit("\n" + "=" * 92)
    emit("  AGENT-LEVEL CHARACTERISATION")
    emit("=" * 92 + "\n")
    hw = (trace or {}).get("hardware", {}) or (corpus or {}).get("hardware", {})
    emit(f"  Hardware: {hw.get('platform','TODO')} | {hw.get('cpu_count','?')} cores | "
         f"{hw.get('ram_gb') or '?'} GB RAM | GPU: {hw.get('gpu_name','none detected')}")
    records = _stat(trace, "total_query_records", 0)
    emit(f"  {'Query records mined':36s} {records}")
    if not records or records == "TODO":
        emit("\n  *** No query records. Every value below is unmeasured. Run:")
        emit("  ***   python -m scripts.eval.run_agent_traces --n 30")
        emit("  ***   python -m scripts.eval.trace_stats --data-dir ../data")
    for label, key in [
        ("LM calls per query (median)", "median_llm_calls"),
        ("Prompt tokens per query (median)", "median_prompt_tokens"),
        ("Generated tokens per query (median)", "median_completion_tokens"),
        ("Planner JSON parse-failure rate (%)", "planner_failure_rate_pct"),
        ("Median end-to-end latency (ms)", "median_total_ms"),
        ("95th percentile latency (ms)", "p95_total_ms"),
        ("Mean scheduler iterations", "mean_iterations"),
        ("Fraction hitting the cap", "fraction_hitting_cap"),
        ("Debate changed top precedent (%)", "debate_change_rate_pct"),
    ]:
        emit(f"  {label:36s} {_stat(trace, key)}")
    emit(f"  {'External API calls':36s} 0 (local Ollama)")
    emit(f"  {'Monetary cost per query':36s} 0 (local Ollama)")

    # ── LaTeX ─────────────────────────────────────────────────────────────
    if args.latex:
        emit("\n" + "=" * 92)
        emit("  LaTeX bodies")
        emit("=" * 92)
        for tag, name, length in REGIMES:
            agg = _table(_load(reports, f"score{tag}"), "effectiveness")
            if not agg:
                continue
            emit(f"\n%% {name} ({length}) — test split")
            for key, label in RETRIEVAL_ROWS:
                vals = agg.get(key)
                if vals:
                    emit(f"{label} & " + " & ".join(_pct(vals.get(m)) for m in METRICS)
                         + r" \\")

    missing = [ln for ln in out_lines if "TODO" in ln]
    emit("\n" + "=" * 92)
    emit(f"  {len(missing)} value(s) still missing.")
    for m in missing:
        emit(f"    {m.strip()}")
    emit("=" * 92)

    out = reports / "paper_tables.txt"
    out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\n[written] {out}")


if __name__ == "__main__":
    main()
