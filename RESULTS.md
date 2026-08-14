# Verdicto — Measured Results

**Run date:** 13 August 2026 · **Corpus:** live AWS Open Data bucket, English judgments 2016–2024
**Hardware:** macOS (Apple Silicon), 10 cores, no CUDA GPU · Postgres 15 in Docker
**Reproducibility:** every number below is regenerable from `Backend/scripts/`; raw reports in `data/reports/`

> **Scope note.** These are *real* numbers on a *real* 7,096-judgment corpus, produced end to end
> on this machine. They are not the numbers from your Windows box: this corpus is 2016–2024 only,
> whereas yours is the whole bucket (1950–2025). Everything here is directly reproducible on your
> machine with the same commands, and the *shape* of the findings will hold. The absolute values
> will change with corpus size — in particular, citation resolution and every retrieval metric
> should **improve** with a wider year range.

---

## 1. Corpus construction

| Stage | Documents | Loss |
|---|---|---|
| PDFs downloaded | 7,096 | — |
| Text extracted | 7,096 | **0 failures** |
| Segmented, heading-based | 7,094 | — |
| Segmented, positional fallback | 2 | no headings found |
| Embedded | 7,096 | — |
| Indexed and loaded | 7,096 | — |
| Rows in `cases` | 7,096 | — |

**Fallback rate: 0.03 %.** This *corrects* my earlier concern. I expected the regex segmenter to
fall back to blind quartering often; on this corpus it fires on 2 documents out of 7,096. The
heading-based segmentation is working, and the "positional fallback" limitation I flagged is not
a material weakness of this corpus. Extraction had **zero** failures — no scanned, encrypted or
corrupt PDFs in the 2016–2024 English set.

| Corpus property | Value |
|---|---|
| N (documents indexed) | 7,096 |
| Year range | 2016–2024 (9 years) |
| Mean / median length | 8,449 / 5,261 words |
| Median length in encoder tokens | 7,381 |
| **Documents exceeding the 256-token encoder limit** | **100.0 %** |
| **Mean fraction of a document that reaches its vector** | **4.69 %** |
| Median fraction embedded | 3.31 % |
| Documents embedded in full | 0.04 % |
| Near-duplicate pairs (cos ≥ 0.95) | 14 pairs, 25 documents, 0.35 % |
| Near-duplicate pairs (cos ≥ 0.90) | 100 pairs, 79 documents, 1.11 % |

**The truncation limitation is now quantified: a judgment is represented in the vector space by
4.7 % of itself.** Every document in the corpus exceeds the encoder's limit. This is the single
most important number for interpreting the dense channel's performance below.

---

## 2. Metadata and the citation graph

The Parquet metadata was loaded for the first time — this is the step that had never been run.

| Column | Non-NULL after load |
|---|---|
| `citation` | 7,096 / 7,096 |
| `decision_date` | 7,096 / 7,096 |
| `bench` | 7,087 / 7,096 |
| `disposal_nature` | 6,904 / 7,096 |
| `acts_sections` | **0** — the bucket does not publish this column |

**Consequence: the two dead authority signals are now live.** Citation count (weight 0.35) and
bench size (0.20) were previously identically zero and constant respectively. They now carry real
values, so the authority re-rank is measured here as a fully-live component — unlike in the
deployed system.

| Citation extraction | Value |
|---|---|
| SC citations found | 164,653 |
| Mean per document | 23.2 |
| Out-of-scope (High Court etc., correctly excluded) | 4,096 |
| Resolved to an in-corpus case | 15,212 |
| **In-corpus resolution rate** | **9.24 %** |
| Unique graph edges | 4,891 |
| Documents with ≥ 1 outgoing edge | 2,221 |
| Mean out-degree | 2.2 |

### Why resolution is capped at ~19 %, and why widening the corpus only partly fixes it

Reporter breakdown over a 300-document sample:

| Reporter | Share of all citations | Of which fall in corpus years |
|---|---|---|
| **SCC** | **48.6 %** | 640 |
| SCR | 41.2 % | 1,156 |
| AIR | 5.2 % | 9 |
| INSC | 3.5 % | 92 |
| SCC OnLine | 1.6 % | 83 |

**The bucket publishes SCR and neutral (INSC) citations. Indian judgments predominantly cite SCC.**
Nearly half of all citations are therefore unresolvable *by construction*, no matter how wide the
corpus, because there is no SCC identifier anywhere in the metadata to match against. The
theoretical ceiling on this corpus is roughly 19 %; we achieved 9.24 %, about half of it.

This is a genuine, reportable limitation and it belongs in the paper. Closing it would require an
SCC ↔ SCR crosswalk, which the AWS dataset does not provide.

### Validation: the graph recovers the actual landmark judgments

Top cases by in-degree, unprompted:

| Case | In-degree |
|---|---|
| Indore Development Authority v. Manoharlal (land acquisition, Constitution Bench) | 90 |
| Swiss Ribbons v. Union of India (IBC constitutionality) | 53 |
| **Justice K.S. Puttaswamy v. Union of India (privacy, 9-judge)** | 52 |
| Innoventive Industries v. ICICI Bank (foundational IBC) | 40 |
| National Insurance v. Pranay Sethi (compensation, Constitution Bench) | 32 |
| Modern Dental College (Constitution Bench) | 27 |
| Ssangyong Construction v. NHAI (arbitration) | 27 |

These are the genuinely most-cited Indian Supreme Court judgments of the period. The extractor is
recovering real precedent structure, not noise.

---

## 3. Evaluation set

| Quantity | Value |
|---|---|
| Q (query cases) | 984 |
| Total relevance judgements | 3,635 |
| Mean relevant per query | 3.69 |
| Median relevant per query | 3.0 |
| Split (temporal) | 590 dev / 394 test |
| **Queries with residual citations after stripping** | **0** |
| Grading | 2 = cited and discussed, 1 = cited in passing |

Leakage controls: citation strings and case names stripped from every query; query case excluded
from its own pool; **temporal filter (`year < query_year`) applied to both channels**, including
FAISS, which the deployed system does not do.

Mean relevant/query is 3.69, below 5 — **so nDCG@10 and MRR lead; P@10 has a ceiling below 0.5
and should be reported only as secondary.**

---

## 4. Retrieval results (test split, 394 queries, no LLM)

All values ×100. Deterministic, exactly reproducible, no language model in the loop.

| Condition | P@1 | P@5 | R@20 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| **BM25 Okapi (k₁=1.2, b=0.75)** | **11.18** | **5.83** | **13.49** | **15.28** | **9.32** |
| L-conj conjunctive `tsquery` | 1.63 | 0.49 | 0.86 | 1.85 | 0.93 |
| L disjunctive `tsquery` | 2.95 | 1.32 | 3.58 | 4.51 | 2.28 |
| D dense only | 3.86 | 2.26 | 5.36 | 6.41 | 3.54 |
| F rank fusion (dense + `ts_rank`) | 4.57 | 2.52 | 6.07 | 7.03 | 3.70 |
| F+A fusion and authority | 4.78 | 3.17 | 6.07 | 7.97 | 4.60 |
| *(extra)* dense + BM25 fusion | 8.13 | 4.90 | 12.80 | 12.45 | 7.44 |

### Paired bootstrap vs BM25, nDCG@10, 10,000 resamples

| Condition | mean Δ | 95 % CI | P(better) | Significant |
|---|---|---|---|---|
| dense + BM25 fusion | −0.0189 | [−0.0248, −0.0129] | 0.000 | yes |
| fusion + authority | −0.0472 | [−0.0578, −0.0365] | 0.000 | yes |
| rank fusion | −0.0562 | [−0.0667, −0.0459] | 0.000 | yes |
| dense only | −0.0579 | [−0.0688, −0.0474] | 0.000 | yes |
| disjunctive `tsquery` | −0.0705 | [−0.0816, −0.0593] | 0.000 | yes |
| conjunctive `tsquery` | −0.0839 | [−0.0956, −0.0723] | 0.000 | yes |

**Every condition is significantly worse than BM25. Every confidence interval excludes zero.**

---

## 5. What the results actually say

**5.1 A plain BM25 baseline beats the full system by 2.3× on P@1 (11.18 vs 4.78), and the gap is
statistically unambiguous.** This is the headline finding and it must be reported. Two causes, both
already documented and now quantified:

- The dense channel sees **4.7 % of each judgment** (Section 1). An encoder with no legal
  pretraining, reading one paragraph of facts, cannot compete with full-text lexical matching.
- The system's lexical channel is `ts_rank` over **at most 8 keywords**. BM25 uses every term in
  the query against every term in the document. The 8-keyword cap was chosen for recall against
  `plainto_tsquery`, not against a real BM25.

**5.2 The internal ablations are all in the right direction, and they are the system's defence.**
Within the architecture as designed, every component earns its place:

- Fusion beats both of its own channels: 4.57 vs 3.86 dense, vs 2.95 lexical.
- The authority re-rank adds on top: 4.78 P@1, 3.17 P@5 (+26 % over fusion), 7.97 MRR.
  Note this is with citation count and bench size **live** for the first time.
- The disjunctive `tsquery` nearly doubles the conjunctive one (2.95 vs 1.63 P@1) and, more
  starkly, **the conjunctive variant returns nothing at all for 220 of 394 queries** while the
  disjunctive returns results for all 394. This validates a real design decision with data.

So the architecture is coherent; its *components* are the problem, not its *structure*.

**5.3 Fusing a weak channel with a strong one destroys the strong one.** Dense + BM25 scores 8.13
P@1 — worse than BM25 alone at 11.18. RRF is rank-based and symmetric, so a channel that is
mostly wrong actively drags down a channel that is mostly right. This is a genuinely interesting
result and it is the most useful thing in the table for a reader: **it argues that fusion is only
worth it when both channels are individually competitive.**

**5.4 The obvious remedy is the one already identified.** Chunk-and-pool embeddings (Tier 3, item 1
in the plan) would raise the dense channel from 4.7 % document coverage to full coverage. Given
that dense+BM25 fusion already reaches 12.80 R@20 against BM25's 13.49, a competent dense channel
should push fusion past BM25. That is the natural next experiment and the paper can name it.

**5.5 A concrete fusion win (paper Section 6, qualitative example).**
Query `2024_10_425_444_EN` (a tender / power-of-attorney dispute), gold case `2022_19_523_562_EN`:

| Channel | Rank of the gold case |
|---|---|
| Dense only | 16 |
| Lexical only | 13 |
| **Rank fusion** | **1** |

Neither channel put it in the top ten; RRF's agreement bonus promoted it to first. ΔnDCG@10 =
+0.61 for this query. This is the textbook RRF mechanism, observed in the wild.

---

## 6. What could not be measured here, and why

**Agent-level results (paper Table 2) and system characterisation (Table 3) are not in this run.**
They require Ollama serving `deepseek-r1:8b`, which is not installed on this machine, and they
require queries submitted through the running API so that `agent_trace` rows exist. `trace_stats.py`
reports `total_query_records = 0`.

Everything needed is built and waiting. On your Windows box, with Ollama running:

```bash
python test_scores.py                      # or submit ~30 queries via the API
python -m scripts.eval.trace_stats --data-dir ../data
```

That single command fills: mean/max iterations, fraction hitting the cap, end-to-end median and
P95 latency, the per-agent latency breakdown, the debate-changed-the-top-precedent rate with
before/after examples, planner JSON parse-failure rate, and token counts.

Also unmeasured: citation-extractor precision/recall against a hand-annotated sample (needs ~2
hours of human annotation on 20 judgments), and segmentation accuracy against a labelled set
(~1 day on 50 documents). Both are described in the plan.

---

## 7. Bugs found and fixed by contact with real data

Each of these would have silently produced zeros or wrong numbers on your machine.

| # | Bug | Impact if unfixed |
|---|---|---|
| 1 | **Parquet join key.** The Parquet's own `case_id` column is the *neutral citation* (`2020 INSC 395`), not the corpus id. The real key is `path` + `_EN`. | Zero rows matched; metadata load a silent no-op |
| 2 | **Citation regex.** Real citations are `[2020] 4 S.C.R. 552` — square brackets, periods. The pattern expected `(2020) 4 SCR 552`. | Zero citations resolved; no graph, no ground truth |
| 3 | **Untyped NULL parameter.** `acts_sections` is absent from the bucket, so it is NULL for all rows; asyncpg raised `could not determine data type of parameter $8` and **aborted the entire load silently**. | Metadata table left untouched while the script appeared to run |
| 4 | **FAISS path.** `.env` had `./data/index/...`, but scripts run from `Backend/`, resolving to `Backend/data/`. | All four dense/fusion conditions failed |
| 5 | **BM25 memory.** 7k docs × ~2.5k tokens as Python strings pushed the process into swap, stalling every later condition in the same run. | Run appeared to hang indefinitely |
| 6 | **Self-matching `pgrep`** in an orchestration wait loop matched its own command string. | Pipeline stalled forever |

Two improvements also made: `extract_text.py` gained `--workers` (60 min → 14 min for 7k PDFs),
and `build_embeddings.py` lost a leftover `asyncio.sleep(0.5)` per document from the Gemini era
and now batches the encoder (7,096 documents embedded in **39 seconds**).

---

## 8. Reproducing this

```bash
cd Backend
pip install ir_measures rank_bm25 numpy pandas pyarrow sentence-transformers faiss-cpu

python -m scripts.ingest.download_dataset --year-from 2016 --year-to 2024 --output-dir ../data/raw
python -m scripts.ingest.extract_text  --input-dir ../data/raw/pdfs --output-dir ../data/processed --workers 8
python -m scripts.ingest.segment_text  --input-dir ../data/processed --output-dir ../data/processed/segmented
python -m scripts.ingest.populate_db   --segmented-dir ../data/processed/segmented
python -m scripts.ingest.load_metadata --data-dir ../data            # run --inspect first
python -m scripts.ingest.build_embeddings --input-dir ../data/processed/segmented --output-dir ../data/embeddings --batch-size 256
python -m scripts.ingest.build_faiss_index --embeddings-dir ../data/embeddings --output-dir ../data/index

python -m scripts.eval.probe_citations --data-dir ../data --sample 400
python -m scripts.ingest.extract_citations --data-dir ../data --truncate
python -m scripts.eval.build_golden_set --data-dir ../data --graded

# two passes — keeps the BM25 index out of memory for the other conditions
python -m scripts.eval.run_eval --data-dir ../data --split test --conditions dense,tsrank,tsrank_conj,hybrid,hybrid_auth
python -m scripts.eval.run_eval --data-dir ../data --split test --conditions bm25,hybrid_bm25

python -m scripts.eval.score        --data-dir ../data --baseline bm25 --primary nDCG@10
python -m scripts.eval.corpus_stats --data-dir ../data --database-url <url>
KMP_DUPLICATE_LIB_OK=TRUE python -m scripts.eval.dedup --data-dir ../data --write-blocklist
python -m scripts.eval.paper_tables --data-dir ../data --latex
```

`paper_tables.py` prints every value in the row order of `procs_icmlde_tiwari.tex` and lists any
that are still missing.
