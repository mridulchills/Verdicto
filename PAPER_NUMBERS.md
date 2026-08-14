# Verdicto — Final Numbers for the Paper

**Assembled:** 14 August 2026 · **Commit:** `282360d` · **Corpus:** 7,096 Indian SC judgments, 2016–2024
**Hardware for every latency figure:** Apple M5, macOS 26.5.2 arm64, 10 cores, 16 GB RAM, no CUDA
**Evaluation:** 984 query cases, 3,635 citation-derived judgements, strict temporal split, graded relevance
**Scoring:** `ir_measures`, paired bootstrap, 10,000 resamples, seed 42
**Agent-level:** 30 queries driven end-to-end, local `qwen2.5:7b-instruct` via Ollama, threshold 0.85

Everything below is regenerated from the artefacts in `data/reports/` and `data/eval/` as of today.
Where a number differs from `RESULTS_V3.md`, this file is authoritative and the difference is flagged.

**Stale-artefact warnings, so you don't cite the wrong file:**

- `data/reports/paper_tables.txt` was generated at 01:15 against a partial trace run of **12**
  queries. Its retrieval and corpus blocks agree with this file; its
  `AGENT-LEVEL CHARACTERISATION` block does **not**. Use §8.2 below, not that block.
- **The model is `qwen2.5:7b-instruct`.** `config.py:73` declares `deepseek-r1:8b`, but `.env`
  sets `OLLAMA_MODEL=qwen2.5:7b-instruct` and pydantic gives the env file precedence — verified by
  resolving `get_settings().ollama_model`. `RESULTS_V3.md` §8 was right. Any claim about
  `<think>`-trace overhead is a deepseek property and does **not** apply to these runs; the
  `<think>`-stripping code in `gemini_client.py:158` exists but never fires.
- **The 13 Aug trace run (§8.2) is superseded** — see §8.2.0. It was measured with the FAISS index
  silently unloaded and with a broken coverage metric. Numbers below are from the 14 Aug re-run.

---

## 0. Read this before you write the results section

**The v3 headline as written in `RESULTS_V3.md` is true only for 33-word queries.** Until today the
v3 system had been evaluated on exactly one query regime (`queries_short.json`). It has now been run
on all four. The effect is strongly regime-dependent, and in the regime that most resembles a real
"here is my case, find precedent" input — the long one — the system **significantly loses** at the
top of the ranking.

Δ = `hybrid_cite` − `bm25_grid` (tuned BM25), test split, n = 394, on nDCG@10:

| Regime | Query length | Δ nDCG@10 | 95 % CI | Significant |
|---|---|---|---|---|
| keyword | 14 words | **+0.0036** | [−0.0023, +0.0097] | no |
| short | 33 words | **+0.0049** | [−0.0013, +0.0111] | no |
| medium | 96 words | **−0.0019** | [−0.0089, +0.0054] | no |
| long | 360 words | **−0.0039** | [−0.0114, +0.0036] | no |

The gain is monotone in query brevity, and it crosses zero. §3 gives the full metric-by-metric
picture, which is sharper than nDCG@10 alone and is the honest basis for the paper's claim.

### 0.1 The five claims the evidence actually supports

Everything in this file reduces to these. Each is measured, each has a section, and each has its
limit stated in the same sentence — write the paper from this list.

| # | Claim | Evidence | Section |
|---|---|---|---|
| 1 | Citation propagation gives **consistent, significant gains in recall and mid-depth precision** across all four query regimes — R@20 up in 4/4 (significant in 3), P@10 up in 4/4 (significant in 2). | Paired bootstrap, 10k resamples, n=394 | §3.2 |
| 2 | It **improves the top of the ranking only for short queries**, and for 360-word queries unweighted RRF **significantly degrades** P@1 (−0.0244) and MRR (−0.0161) against tuned BM25. | Same table | §3.2, §3.3 |
| 3 | The system's **cost is entirely in the LM layer**: retrieval answers in 3.8 ms, the agent pipeline takes 59,607 ms median, 83.9 % of it in a 7-call sequential debate. 8.0 LM calls per query, all local, zero API cost. | 30 end-to-end traces | §8.1, §8.2.1 |
| 4 | **Adversarial debate reordered the top-3 slate in 43.3 % of queries** (13/30), i.e. it changed which precedent is shown first. Whether the new ordering is *better* is unadjudicated. | 30 traces + 13 worked examples | §8.2.2 |
| 5 | **Metric-directed re-scheduling converges 30/30** at mean 1.10 iterations: 28 queries need no remedy, the 2 that do gain **+0.18 confidence** and then converge. Targeted re-runs cost no extra LM calls. | 30 traces, before/after ablation | §8.2.3 |

Two framings to avoid, both of which a reviewer will catch: do **not** claim a general retrieval win
over tuned BM25 (claim 2 forbids it), and do **not** present the 43.3 % debate rate as an accuracy
improvement (claim 4 forbids it).

Three results are also worth stating as negative findings rather than burying: **three of six** v3
components were removed for hurting (§6), the dev→test gain **collapsed** from +0.0209 to +0.0049 on
the same regime (§4), and two silent measurement defects — an unloaded FAISS index and a coverage
metric that was structurally always 0 — invalidated the first agent-level run (§8.2.0).

---

## 1. Corpus construction

| Stage | Count |
|---|---|
| PDFs downloaded | 7,096 |
| Text extracted | 7,096 (0 failures, 0.0 %) |
| Segmented — heading-based regex | 7,094 |
| Segmented — positional fallback | 2 (0.03 %) |
| Embedded | 7,096 |
| Vectors in FAISS index | 7,096 |
| Entries in FAISS mapping | 7,096 |
| Rows in `cases` table | 7,096 |
| Rows in `citations` table | 4,891 |

**Document length** (n = 7,096)

| Statistic | Words | Characters |
|---|---|---|
| Mean | 8,449.4 | 48,861.1 |
| Median | 5,261.0 | 30,243.0 |
| P10 / P90 | 1,937 / 16,270 | — |
| Max | 412,737 | — |

**Embedding coverage** — the number that justifies the chunked-dense line of work

| Quantity | Value |
|---|---|
| Model | `all-MiniLM-L6-v2`, 384-d |
| Tokens per document (MiniLM tokeniser), mean / median / P90 | 13,311.8 / 7,381.0 / 25,494 |
| Documents exceeding the 256-token encoder limit | **100.0 %** |
| Truncation applied | first 1,000 characters |
| Mean fraction of document embedded | **4.689 %** |
| Median fraction embedded | 3.305 % |
| Documents embedded in full | 0.04 % |
| Encoding throughput | 386.2 docs/s, 0.31 min total |

**Near-duplicates** (cosine over document vectors, 6 neighbours each)

| Threshold | Pairs |
|---|---|
| ≥ 0.90 | 100 |
| ≥ 0.95 | 14 |
| ≥ 0.98 | 5 (blocklisted) |

**Metadata load:** 9 Parquet files, 7,100 rows, 7,098 matched to a case, 2 unmatched.

---

## 2. Ground truth

Relevance is **citation-derived**: case *A* is relevant to query case *Q* if *Q* cites *A*. The
query text has every citation to its own gold set stripped before use (`residual_citations = 0`).

| Quantity | Value |
|---|---|
| Cases with ≥ 2 in-corpus citations | 1,001 |
| **Q (query cases)** | **984** |
| Dropped — query too short after stripping | 6 |
| Dropped — no text | 11 |
| **Total relevance judgements** | **3,635** |
| Mean relevant per query | 3.69 |
| Median relevant per query | 3.0 |
| Graded relevance | yes |
| **Dev split** | **590** queries, 2017–2023 |
| **Test split** | **394** queries, 2023–2024 |
| Residual leakage (must be 0) | **0** |

### 2.1 Citation graph

| Quantity | Value |
|---|---|
| SC citations found in text | 164,653 |
| Mean citations per document | 23.2 |
| Out-of-scope (High Court and below) | 4,096 |
| Resolved by canonical citation | 15,212 |
| Resolved by case name | 0 |
| Unresolved | 149,441 |
| **In-corpus resolution rate** | **9.24 %** |
| Graph nodes / edges | 7,096 / **4,891** |
| Documents with ≥ 1 outgoing edge | 2,221 |
| Mean out-degree | 2.2 |

> The 9.24 % resolution rate is a corpus-coverage artefact, not an extractor defect: the corpus is
> 2016–2024, so the overwhelming majority of cited authorities pre-date it and cannot resolve to an
> in-corpus node. Extractor precision/recall is still unmeasured — see §8.

### 2.2 Query regimes

All four are derived from the same 984 query cases, so every regime is scored against identical
qrels and is directly comparable. Leakage is 0 in all four.

| Regime | Mean words | Mean chars | File |
|---|---|---|---|
| keyword | 14.2 | 111 | `queries_keyword.json` |
| short | 33.2 | 199 | `queries_short.json` |
| medium | 95.9 | 583 | `queries_medium.json` |
| long | 359.9 | 2,179 | `queries_long.json` |

---

## 3. MAIN RESULT — retrieval effectiveness, test split (n = 394)

All conditions below were run today on identical queries within each regime, so each block is one
internally consistent table. **Baseline for significance is `bm25_grid`** — full-text BM25 at the
dev-tuned `k1 = 12, b = 0.65`. Never report against `bm25s`; that is the broken 20 %-coverage index.

### 3.1 The four regimes

| Condition | P@1 | P@5 | R@20 | MRR | **nDCG@10** | P@10 | nDCG@20 |
|---|---|---|---|---|---|---|---|
| **keyword — 14 words** | | | | | | | |
| `bm25s` (v2 index, 20 % coverage) | 7.42 | 3.94 | 9.29 | 10.78 | 6.24 | 2.82 | 6.94 |
| `bm25_full` (full text, k1=1.2) | 6.61 | 4.59 | 10.32 | 10.69 | 6.64 | 3.18 | 7.48 |
| `bm25_grid` (full text, **tuned**) | 8.43 | 4.82 | 10.95 | 12.10 | 7.38 | 3.52 | 8.15 |
| `cite_prop` (citation channel alone) | 2.13 | 2.62 | 7.64 | 5.97 | 3.51 | 2.00 | 4.52 |
| **`hybrid_cite` (the system)** | **8.43** | **5.28** | **12.51** | **12.19** | **7.74** | **3.79** | **8.75** |
| **short — 33 words** | | | | | | | |
| `bm25s` | 5.59 | 3.35 | 7.88 | 8.63 | 5.17 | 2.44 | 5.70 |
| `bm25_full` | 7.01 | 3.94 | 8.99 | 10.04 | 6.11 | 2.88 | 6.70 |
| `bm25_grid` | 6.91 | 4.37 | 9.90 | 10.21 | 6.58 | 3.16 | 7.24 |
| `cite_prop` | 2.13 | 2.42 | 6.94 | 5.60 | 3.23 | 1.85 | 4.18 |
| **`hybrid_cite`** | **7.32** | **4.80** | **11.13** | **10.97** | **7.07** | **3.40** | **7.94** |
| **medium — 96 words** | | | | | | | |
| `bm25s` | 9.45 | 4.96 | 11.32 | 13.14 | 7.94 | 3.48 | 8.76 |
| `bm25_full` | 10.26 | 6.30 | 13.56 | 14.46 | 9.51 | 4.27 | 10.41 |
| `bm25_grid` | **11.48** | 6.67 | 14.69 | **15.82** | **10.26** | 4.59 | **11.28** |
| `cite_prop` | 2.34 | 2.95 | 8.79 | 6.31 | 3.84 | 2.30 | 5.04 |
| `hybrid_cite` | 9.86 | **6.69** | **15.53** | 14.93 | 10.07 | **4.86** | 11.18 |
| **long — 360 words** | | | | | | | |
| `bm25s` | 10.87 | 5.83 | 13.76 | 14.74 | 9.11 | 4.14 | 10.22 |
| `bm25_full` | 13.11 | 6.99 | 15.94 | 16.95 | 10.87 | 4.81 | 12.18 |
| `bm25_grid` | **13.72** | **7.89** | 16.86 | **18.14** | **11.81** | 5.29 | **13.03** |
| `cite_prop` | 3.15 | 3.29 | 9.39 | 7.16 | 4.29 | 2.47 | 5.54 |
| `hybrid_cite` | 11.28 | 7.80 | **16.92** | 16.53 | 11.42 | **5.61** | 12.45 |

*(values ×100; bold = best in block)*

Legacy v1/v2 conditions, long regime, for the record: `bm25` (rank_bm25, title+facts+issues,
k1=1.2, b=0.75) 9.16 · `dense` 3.43 · `tsrank` 2.30 · `tsrank_conj` 0.93 · `hybrid` 3.70 ·
`hybrid_bm25` 7.45 · `hybrid_auth` 4.59 nDCG@10. Every one of them is significantly below
`bm25_grid`.

### 3.2 Significance — `hybrid_cite` vs tuned BM25, every metric, every regime

Paired bootstrap, 10,000 resamples. **This table is the paper's real result.**

| Regime | P@1 | P@5 | R@20 | MRR | nDCG@10 | P@10 | nDCG@20 |
|---|---|---|---|---|---|---|---|
| keyword | +0.0000 | **+0.0047** ✓ | **+0.0156** ✓ | +0.0009 | +0.0036 | **+0.0027** ✓ | **+0.0061** ✓ |
| short | +0.0041 | +0.0043 | **+0.0122** ✓ | +0.0076 | +0.0049 | +0.0024 | **+0.0070** ✓ |
| medium | −0.0163 | +0.0002 | **+0.0084** ✓ | −0.0089 | −0.0019 | +0.0026 | −0.0011 |
| long | **−0.0244** ✗ | −0.0008 | +0.0006 | **−0.0161** ✗ | −0.0039 | **+0.0032** ✓ | −0.0059 |

✓ = significant gain (95 % CI excludes 0) · ✗ = **significant loss** · blank = not detectable

Full intervals are in `data/reports/regime_significance.json`. The three that matter:

- **R@20, keyword:** +0.0156, CI [+0.0083, +0.0232], P(better) 1.000
- **R@20, short:** +0.0122, CI [+0.0048, +0.0200], P(better) 1.000
- **P@1, long:** −0.0244, CI [−0.0447, −0.0041], P(better) 0.007 — *a significant regression*

### 3.3 What this means, stated so a reviewer cannot reframe it

Citation propagation retrieves precedents that **do not share the query's vocabulary**. That has two
consequences, and both are visible:

1. **It adds candidates, in every regime.** R@20 improves in all four (significantly in three), and
   P@10 improves in all four (significantly in two). Depth-oriented gains are robust.
2. **What it costs at rank 1 depends on how strong the lexical channel already is.** With a 14- or
   33-word query the lexical channel is starved and the citation channel is a net addition. With a
   360-word query the lexical channel is already strong, and fusing a noisier second channel under
   **unweighted** RRF displaces correct top hits — P@1 −0.0244 and MRR −0.0161, both significant.

**Defensible claim for the paper:** *citation propagation yields consistent, significant gains in
recall and mid-depth precision across query regimes, and improves top-of-ranking quality only for
short queries; for long queries, unweighted fusion significantly degrades P@1 and MRR relative to a
tuned BM25 baseline.*

**Do not claim** a general win over tuned BM25. The v3 system is not one.

> The obvious remedy — a query-length-dependent or learned fusion weight instead of unweighted RRF —
> is **untested**. It would have to be fitted on dev and is the natural next experiment. Note that
> §5 already shows `w_cite` has a sharp dev optimum at exactly 1.0 on the short regime, so a
> per-regime weight is likely to matter more than a single retuned constant.

---

## 4. Dev-split result at the final configuration

Re-run today from scratch; reproduces `RESULTS_V3.md` §4 exactly. Short regime, n = 590.

| Condition | P@1 | P@5 | R@20 | MRR | nDCG@10 | nDCG@20 |
|---|---|---|---|---|---|---|
| `bm25s` | 8.74 | 4.55 | 14.08 | 13.23 | 9.02 | 10.16 |
| `bm25_full` | 9.35 | 5.89 | 16.98 | 14.95 | 10.61 | 11.99 |
| `bm25_grid` | 11.59 | 6.52 | 19.02 | 17.19 | 12.49 | 13.82 |
| `cite_prop` | 5.79 | 3.94 | 14.79 | 10.79 | 7.12 | 9.10 |
| **`hybrid_cite`** | **12.30** | **7.87** | **23.25** | **19.20** | **14.57** | **16.18** |

`hybrid_cite` vs `bm25_grid`: **Δ nDCG@10 +0.0209, CI [+0.0118, +0.0302], P(better) 1.000 —
significant.**

**The dev gain does not transfer:** +0.0209 (dev, significant) → +0.0049 (test, not significant) on
the same regime. Test queries are 2023–24, so the candidate pool is larger and every condition drops
by roughly a third. This must be stated in the paper; it is the kind of gap a reviewer will compute.

---

## 5. Parameter selection — all on dev, none on test

| Parameter | Chosen | Dev evidence (nDCG@10) |
|---|---|---|
| BM25 `k1` | **12.0** | 1.2→0.1061 · 4→0.1192 · **12→0.1245** · 20→0.1218 (turns over) |
| BM25 `b` | **0.65** | flat plateau 0.65–0.75 |
| `w_full : w_cite` | **1.0 : 1.0** | 0.8→0.1352 · **1.0→0.1457** · 1.2→0.1149 (sharp peak) |
| `cite_neighbours` | **100** | 20→0.1408 · 50→0.1435 · **100→0.1457** · 200/400→0.1453 (plateau) |
| `cite_rr_k` | **10** | flat 5–10, mild decline to 60 |
| Passage-channel weight | **0.0 (removed)** | 1.0→0.1355 · 0.5→0.1362 · **0.0→0.1408** |
| RRF constant `k` | 60 (default) | 10/20/60 → 0.1096 / 0.1091 / 0.1092 — flat |

Two caveats to report, not hide:

1. The `w_cite` optimum is a **sharp peak at exactly 1.0**, i.e. the system is plain unweighted RRF
   rather than a weight fitted to dev. Reassuring in one sense, fragile in another — and §3 shows it
   is the wrong constant for long queries.
2. `cite_neighbours` by contrast has a broad, smooth plateau, so that choice is robust.

---

## 6. Negative results — every "did you try…?" a reviewer will ask

All measured on **dev**, short regime.

| Lever | Result | Why it failed |
|---|---|---|
| **Passage-level BM25**, max-pooled (95,470 passages) | 0.0974 vs 0.1061 doc-level — **removed** | Citation prediction depends on aggregate topical match across the whole judgment; one best passage discards that evidence. |
| **RM3 pseudo-relevance feedback** | 0.1057 vs 0.1061; no (α, terms, docs) setting beat plain BM25 | Feedback documents are entire judgments, so expansion terms are generic legal boilerplate. |
| **Summary-field fusion** (BM25F-like, 3 lexical views) | 0.1067 | The views are the same text in different windows — highly correlated, so RRF gains little. |
| **Cross-encoder rerank** (`ms-marco-MiniLM-L-6-v2`) | P@1 4.27 vs 5.59 — **hurts** | Trained for "does this passage answer the query"; here relevance means "this case cites that one". No transfer. |
| **Dense channel** (single-vector, 4.7 % coverage) | 0.1389 at w=0.25 vs 0.1457 without — **hurts** | A weak channel drags a symmetric fusion down. **See the caveat in §8.1 — this is a proxy, not a verdict on chunked dense.** |
| **Authority re-rank** (global in-degree) | withdrawn | Inflated by the label edge — leakage. `RESULTS_V2.md` §4. |
| **Authority as fused prior** | dev-only gain, did not transfer | Global in-degree is near-independent of the query. |

**Three of the six components built for v3 earned their way out.** The shipped system is two
channels, not five — that is a result worth stating plainly.

---

## 7. Leakage audit — `cite_prop`, both splits

`scripts/eval/audit_cite_prop.py`. Every violation count must be 0, and is.

| Check | dev | test |
|---|---|---|
| Query case present in its own neighbour set | 0 | 0 |
| Neighbour decided after the query year | 0 | 0 |
| Voting edge from a case decided after the query year | 0 | 0 |
| Voting edge whose `citing_case_id == qid` (**the label edge**) | 0 | 0 |
| **Verdict** | **CLEAN** | **CLEAN** |
| Coverage (queries with ≥ 1 vote) | 95.9 % | 99.7 % (393/394) |
| Mean voting edges per query | — | 30.1 |
| Voting edges hitting a relevant case | — | 692 |

The channel never reads the edge `Q → C`. It infers C from *other* cases' citations — prediction,
not leakage.

---

## 8. System characterisation

### 8.1 Retrieval-side (measured today, 394 test queries, short regime)

| Component | Median query latency |
|---|---|
| `bm25s` (summary index) | **0.1 ms** |
| `bm25_grid` (full-text, tuned) | **0.2 ms** |
| `cite_prop` (100 neighbours + graph vote) | **2.4 ms** |
| **`hybrid_cite` (full system)** | **3.8 ms** |

| Index | Units | Build time |
|---|---|---|
| `bm25` — title+facts+issues, k1=1.2, b=0.75 | 7,096 docs | 1.4 s |
| `bm25_chunk` — passage mode | 95,470 passages (mean 13.45/doc) | 149.2 s |
| `bm25_full` — doc mode, full text (mean 47,080 chars/doc) | 7,096 docs | ~120 s † |
| FAISS document index | 7,096 × 384-d | 0.31 min encode |

† The doc-mode build report on disk was overwritten by the later passage build. 120 s is carried
over from `RESULTS_V3.md` §3.1 and is **not currently backed by a report file** — re-run
`build_bm25_full_index --mode doc` if you want to cite it.

### 8.2.0 Which trace run to cite — the 13 Aug run is withdrawn

Two runs exist. **Cite only the 14 Aug one.**

| | 13 Aug (withdrawn) | **14 Aug (authoritative)** |
|---|---|---|
| Confidence threshold | 0.55 | **0.85** |
| Scheduler | re-ran the whole pipeline | **adaptive: re-runs the diagnosed agent** |
| FAISS dense channel | **silently dead** | loaded, 7,096 vectors |
| Coverage metric | **structurally always 0** | content-word overlap |
| Archive | `data/traces/archive_thresh055_n30.json` | `data/traces/run_thresh085.jsonl` |

Two defects invalidated the 13 Aug agent numbers. Both are worth a line in the reproducibility
appendix, because neither raised an error:

1. **FAISS was never loaded.** `get_faiss_index().load()` is called only in `app/main.py:52`, the
   API's startup lifespan. `run_agent_traces.py` invokes `SchedulerAgent` directly and bypassed it,
   so `retriever.py:79` logged `faiss_not_loaded` and returned `[]` from the dense channel on every
   query. The agent pipeline was running on Postgres `ts_rank` alone — the condition that scores
   **2.30** nDCG@10 in §3.1's legacy row, the weakest channel measured. The runner now loads the
   index explicitly and fails loudly.
2. **Coverage was always 0.** `evaluator.py` tested `issue.lower()[:20] in all_case_text` — an exact
   20-character prefix match of an LM-generated issue against concatenated case text, which
   essentially never fires. Coverage carries weight 0.2, so confidence was capped at
   **0.80 = 0.3 + 0.3 + 0.2**, and *any* threshold above 0.80 was unreachable by construction. It is
   now a content-word overlap test.

The second defect is why the 0.55 → 0.85 threshold change matters: at 0.85 against a 0.80 ceiling,
**no query could ever have converged** and every one would have run to the iteration cap.

### 8.2 Agent-level — **MEASURED**, n = 30 queries

`scripts/eval/run_agent_traces.py --n 30 --tag thresh085` drove 30 test-split queries end-to-end
through `SchedulerAgent` (the same path the API's BackgroundTask takes), then
`scripts/eval/trace_stats.py` mined the persisted traces. **30/30 completed; 0 failed.**

**Model: `qwen2.5:7b-instruct`**, served locally by Ollama. Note that `config.py:73` declares
`deepseek-r1:8b`; `.env` overrides it and pydantic gives the env file precedence. Verified by
resolving `get_settings().ollama_model` and by 0 `<think>` traces in 240 completions.
Source: `data/reports/trace_stats.json`, raw traces in `data/traces/run_thresh085.jsonl`.

**8.2.1 End-to-end latency** — the headline is that this system is *slow*, and the reason is legible

| Stage | n | Median (ms) | P95 (ms) | Max (ms) | Share of median |
|---|---|---|---|---|---|
| `query_planner` (1 LM call) | 30 | 7,648 | 10,457 | 11,022 | 12.8 % |
| `retriever` (FAISS + ts_rank) | 30 | 325 | 863 | 9,452 | 0.5 % |
| `precedent_weighting` | 30 | 153 | 285 | 417 | 0.3 % |
| **`debate` (7 LM calls)** | 30 | **49,990** | 56,600 | 75,087 | **83.9 %** |
| `evaluator` | 30 | 4 | 11 | 17 | 0.007 % |
| **`scheduler` (total)** | 30 | **59,607** | **66,295** | 86,339 | 100 % |

Read against the retrieval-side latencies in §8.1: **`hybrid_cite` answers in 3.8 ms; the agent layer
around it costs ~59,600 ms.** That ratio — roughly 15,000× — is the paper's most quotable systems
number, and it is entirely LM-bound. 8 of 8 LM calls are local; **zero external API calls, zero
monetary cost per query.**

- **PRD NFR-02 (P95 < 60 s) is missed at P95 = 66.3 s**, and the earlier P95 < 8 s target is missed
  by ~8×. Report the real distribution and revise the NFR; do not quietly restate the target.
- Debate's 7 calls are **deliberately sequential** (`app/agents/debate.py:8–13`): Ollama on a single
  GPU queues concurrent requests and each then times out waiting. State this, or a reader assumes a
  parallelism that was consciously rejected. It also means debate is ~7× parallelisable in principle
  on multi-GPU hardware — the obvious engineering headroom.

**8.2.2 Debate impact (the Q31 paragraph)**

| Quantity | Value |
|---|---|
| Queries with a usable debate trace | 30 / 30 |
| **Debate changed the top precedent** | **13 / 30 = 43.3 %** |
| Worked examples saved | 13, in `data/reports/debate_examples.json` |

> The 13 Aug run put this at 66.7 % (20/30). That run fed debate a candidate list built without
> the dense channel (§8.2.0), so debate had more bad top-3 slates to fix. **43.3 % is the number to
> cite** — a better retrieval stage leaves debate less to correct, which is the expected direction.

**State the scope precisely, because it is narrower than 43.3 % sounds.** Debate runs on iteration 1
only and sees only the **top 3** retrieved cases, so it can never promote a case ranked 4th or lower.
The rate is over the 3! = 6 reachable permutations of a 3-item list, not over the full result list.
Phrased honestly: *adversarial debate reordered the top-3 slate in two thirds of queries, changing
which precedent is presented first.*

A narratable example (`debate_examples.json[0]`) — query on whether the Arbitration and Conciliation
Act permits joinder of a **non-signatory** to an arbitration agreement:

- **was_top** `2020_3_1_328_EN` (*Indore Development Authority v. Manoharlal*) — demoted. Opposing
  counsel: "may not be the strongest precedent … The factual matrix of this case is distinct from
  those involving arbitration agreements and non-signatories."
- **now_top** `2024_11_2173_2328_EN` — promoted. Advocate: "directly addresses the issue of whether
  non-signatories can be joined to an arbitration agreement, which is precisely one of the ancillary
  issues in question."
- **Synthesis rationale:** "Case 2024_11_2173_2328_EN directly addresses non-signatories joining
  arbitration agreements, which is a key issue."

*Indore Development Authority* is a land-acquisition authority — a famous, heavily-cited judgment
that the lexical and authority signals rank highly, and that argumentation demotes as off-point.
That is exactly the failure mode the debate stage exists to catch, and it is the example to narrate.

Caveat for the write-up: no human adjudicated whether the *new* top case is actually better.
**43.3 % is a change rate, not an accuracy gain.** Do not present it as one.

**8.2.3 Scheduler behaviour — adaptive re-scheduling**

The scheduler no longer re-runs the whole pipeline on a low-confidence pass. It reads the
evaluator's four confidence components, picks the one with the largest **headroom**
(weight × shortfall), and re-runs only the agent that can move it, plus everything downstream:

| Deficient component | Diagnosis | Agents re-run |
|---|---|---|
| `coverage` (w 0.2) | the question is wrong | `replan` → planner, retriever, weighter, evaluator |
| `precision@5`, `nDCG@10` (w 0.3 each) | the candidate pool is wrong | `rewiden` → retriever (next reformulation, wider `top_k`), weighter, evaluator |
| `MRR` (w 0.2) | the ordering is wrong | `reweight` → weighter (alignment-weighted), evaluator |
| `disagreement_rate` > 0.3 | the argument is unsettled | `redebate` → debate, evaluator |

Each remedy is attempted at most once per query, and the scheduler keeps the **best** pass rather
than the last.

| Quantity | Value |
|---|---|
| Mean iterations | **1.10** |
| Max iterations | 3 |
| Iteration distribution | 1 iter: 28 (93.3 %) · 2 iters: 1 (3.3 %) · 3 iters: 1 (3.3 %) |
| Fraction hitting the cap (`k_max` = 3) | **3.3 %** |
| **Queries that converged** | **30 / 30 (100 %)** |
| Mean final confidence | **0.9877** (median 0.9982, min 0.8892) |
| Remedies invoked | `rewiden` × 2, `reweight` × 1 |
| **Confidence gain on the queries that iterated** | **+0.1805 mean** (+0.1811 max), 2 / 2 improved |

**This is the result to report.** 28/30 queries are good enough on the first pass and exit
immediately; the 2 that are not get a targeted remedy, and both improve substantially and then
converge. No query exhausted its remedies without converging. The loop is cheap because the
remedies that fired (`rewiden`, `reweight`) are pure retrieval and ranking — **no additional LM
calls** — which is why mean iterations rose to 1.10 while median latency moved only from 55.0 s to
59.6 s.

Contrast with the withdrawn 13 Aug run, where the same loop re-ran the entire pipeline and produced
byte-identical passes: `plan_result` was computed once *outside* the loop (`scheduler.py:69`), the
retriever always read `reformulated_queries[:1]` so the planner's other alternatives were dead code,
and `top_k` and the weighting coefficients were constants. Deterministic inputs re-derive identical
outputs, so iterating could only burn time. That contrast is the honest ablation — **an iteration
loop is worth something only if the next iteration actually differs.**

**8.2.4 LM output reliability and token usage**

| Quantity | Value |
|---|---|
| **LM invocations per query** | **8.0 exactly** — 240 calls / 30 queries |
| Breakdown | 30 planner + 90 advocate + 90 opposing + 30 synthesis |
| **LM output parse failures** | **0 / 240 (0.0 %)** — planner *and* debate |
| Median prompt tokens per query | **3,749** |
| Median completion tokens per query | **1,259** |
| `<think>` traces emitted | **0** (confirms `qwen2.5:7b-instruct`, not a reasoning model) |
| External API calls | **0** (all inference local) |
| Monetary cost per query | **0** |

Three things to note:

1. **The failure figure is now complete, not planner-only.** The planner rate comes from the trace
   sentinel (its degradation path returns exactly `confidence = 0.3`; no trace shows it). The
   debate side is not in the trace, so it was taken from the run log — `advocate_failed`,
   `opposing_failed`, `synthesis_failed` and `debate_failed` are **all 0** across the run
   (`data/traces/run_thresh085.log`). So: 0 failures in 240 LM calls.
2. **8.0 calls per query is exact, not nominal.** The two queries that iterated used `rewiden` and
   `reweight`, which touch retrieval and ranking only. Had `replan` or `redebate` fired they would
   have added 1 and 7 calls respectively — worth stating, since the adaptive scheduler *can* raise
   LM cost even though it did not here.
3. **No `<think>` overhead applies to these runs.** The stripping code in `gemini_client.py:158`,
   `debate.py:88` and `query_planner.py:77` exists for reasoning models such as `deepseek-r1`, but
   `qwen2.5:7b-instruct` emits bare JSON and the recovery ladder never fires. The 1,259 median
   completion tokens are all useful output. Do not repeat the deepseek `<think>` framing — the
   hard-coded notes in older copies of `trace_stats.py` said so and were wrong.

---

## 9. Still outstanding

| Gap | What it needs | Blocking the draft? |
|---|---|---|
| ~~Agent-level table (§8.2)~~ | **DONE — 30 traces, 14 Aug, threshold 0.85** | No |
| ~~Debate-side JSON failure rate~~ | **DONE — 0 failures in 240 LM calls** | No |
| Debate *quality* (does the promoted case beat the demoted one?) | Human adjudication of the 13 reorderings in `debate_examples.json` — ~2 h | No, but §8.2.2 must be worded as a change rate until it exists |
| Adaptive scheduler at larger n | Only 2/30 queries triggered a remedy, so the +0.18 gain rests on 2 observations. Run ~100 queries, or report n explicitly | No — but state the n |
| `replan` / `redebate` never fired | Neither remedy was exercised in this run; their cost (+1 and +7 LM calls) is inferred, not measured | No — say "not exercised" |
| Chunked dense channel | A CUDA box or ≥ 32 GB RAM — encoding collapsed at 24k/95,350 chunks under swap thrash | No — report as open |
| Citation extractor precision / recall | ~2 h annotating 20 judgments (human) | No — state as a limitation |
| Failure analysis, 30 cases | ~half a day (human); per-query deltas already in `data/eval/per_query_scores.json` | No |
| Query-length-adaptive fusion weight | One dev sweep — the direct answer to §3.3 | No, but it is the obvious reviewer question |
| Full corpus (1950–2025) | Every number moves; citation resolution improves, retrieval gets harder | No |

**Nothing on this list blocks the draft.** The two retrieval claims (§3.3) and the two agent claims
(§8.2.1 latency decomposition, §8.2.2 debate change rate) are all measured and reproducible.

---

## 10. Reproducing every number in this file

```bash
cd Backend
docker start verdicto-eval-db          # 7,096 cases, 4,891 citation edges
PY=./.venv-eval/bin/python
GRID=bm25_full_k120_b065

# leakage audit first — run this before trusting anything below
$PY -m scripts.eval.audit_cite_prop --data-dir ../data --split test

# one regime (repeat for queries_{keyword,short,medium,long}.json with matching --tag)
$PY -m scripts.eval.run_eval --data-dir ../data --split test \
    --queries queries_long.json --tag _long \
    --conditions bm25,tsrank,tsrank_conj,dense,hybrid,hybrid_bm25,hybrid_auth,bm25s,bm25_full
$PY -m scripts.eval.run_eval --data-dir ../data --split test \
    --queries queries_long.json --tag _long --conditions bm25_grid --grid-index $GRID
$PY -m scripts.eval.run_eval --data-dir ../data --split test \
    --queries queries_long.json --tag _long --conditions cite_prop,hybrid_cite \
    --lex-index $GRID --w-lex 0.0 --w-full 1.0 --w-cite 1.0 \
    --cite-neighbours 100 --cite-rr-k 10
$PY -m scripts.eval.score --data-dir ../data --tag _long --baseline bm25_grid

# dev-split result at the final configuration (§4) — same three calls with --split dev --tag _devf

# agent-level table (§8.2) — needs Postgres AND Ollama serving qwen2.5:7b-instruct
ollama serve &                          # OLLAMA_MODEL in .env, NOT the config.py default
$PY -m scripts.eval.run_agent_traces --n 30 --tag thresh085   # ~30 min, sequential
$PY -m scripts.eval.trace_stats --data-dir ../data
```

The trace runner writes an fsync'd JSONL sidecar (`data/traces/run_<tag>.jsonl`) after every query,
so an interrupted run loses at most the query in flight; re-running the same `--tag` resumes and
`--restart` starts over. `run_<tag>.meta.json` records the threshold, model and FAISS vector count
the run executed under — check it before trusting a number, since the 13 Aug run's defects (§8.2.0)
would both have been visible there.

The withdrawn 13 Aug run is preserved at `data/traces/archive_thresh055_n30.json` and is the
before-half of the scheduler ablation in §8.2.3.

Per-regime significance across all metrics (§3.2) is written by the helper that produced
`data/reports/regime_significance.json`; `score.py` bootstraps one primary metric at a time.

---

## 11. Test-set usage disclosure — put a version of this in the paper

The test split has now been evaluated **three times**:

1. the 2-channel configuration before the neighbourhood-cap fix (Δ nDCG@10 +0.0032),
2. after the fix (+0.0049, short regime — `RESULTS_V3.md` §2),
3. today's four-regime sweep (§3).

All three are reported. **No parameter was ever selected on test.** All parameter selection (§5) and
the dense-channel decision (§6) used dev only. The four regimes are alternative evaluation
conditions, not tuned settings — but the count is disclosed because a reviewer is entitled to it.

Two defects found and fixed during the v3 run, both of which silently corrupted results and neither
of which raised an error, are documented in `RESULTS_V3.md` §7 (neighbourhood cap truncating
`cite_prop` to 20 neighbours; a corrupted chunk index mixing vectors from two encoding runs). Keep
that section in the paper's reproducibility appendix — it is evidence of a real audit trail.
