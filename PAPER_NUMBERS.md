# Verdicto — Final Numbers for the Paper

**Assembled:** 14 August 2026 · **Commit:** `282360d` · **Corpus:** 7,096 Indian SC judgments, 2016–2024
**Hardware for every latency figure:** Apple M5, macOS 26.5.2 arm64, 10 cores, 16 GB RAM, no CUDA
**Evaluation:** 984 query cases, 3,635 citation-derived judgements, strict temporal split, graded relevance
**Scoring:** `ir_measures`, paired bootstrap, 10,000 resamples, seed 42
**Agent-level:** 30 natural-language queries, `qwen2.5:7b-instruct`, threshold 0.85 (percentile-calibrated), k_max 5

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
- **Both earlier trace runs are superseded** — see §8.2.0. The 13 Aug run had the FAISS index
  silently unloaded and a coverage metric that was always 0; the first 14 Aug run had a
  self-referential confidence score that saturated near 1.0. §8.2 reports the third run
  (`--tag natural085v2`): natural-language queries, QPP confidence, percentile calibration.

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
| 3 | The system's **cost is entirely in the LM layer**: retrieval answers in 3.8 ms, the agent pipeline takes 73,981 ms median, dominated by a 7-call sequential debate. 8.0 LM calls per query, all local, zero API cost. | 30 end-to-end traces | §8.1, §8.2.1 |
| 4 | **Adversarial debate reordered the top-3 slate in 56.7 % of queries** (17/30), i.e. it changed which precedent is shown first. Whether the new ordering is *better* is unadjudicated. | 30 traces + 17 worked examples | §8.2.2 |
| 5 | **Signal-directed re-scheduling helps, via one remedy of four.** Re-retrieval lifts the delivered result **+0.0715 mean confidence** (16/24 improved, max +0.2545) and carries **3 queries over the 0.85 bar**; 9/30 converge at mean 2.30 iterations. Re-weighting is **counter-productive** (−0.055 on the signal it owns) and two remedies never fire. | 30 traces + dev calibration | §8.2.3 |

Two framings to avoid, both of which a reviewer will catch: do **not** claim a general retrieval win
over tuned BM25 (claim 2 forbids it), and do **not** present the 56.7 % debate rate as an accuracy
improvement (claim 4 forbids it).

Four results are worth stating as negative findings rather than burying: **three of six** v3
components were removed for hurting (§6); the dev→test gain **collapsed** from +0.0209 to +0.0049 on
the same regime (§4); the `reweight` remedy **lowers** the signal it is selected to raise (§8.2.3);
and **three** successive measurement defects invalidated three agent-level runs — an unloaded FAISS
index, a coverage metric structurally pinned at 0, and a self-referential confidence score whose
threshold coincided with a subset sum of its own weights (§8.2.0, §8.2.3). Each was silent, and each
made the system look better than it was.

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
| **natural** | **25.3** | **156** | `queries_natural.json` (30 test queries only) |

The **natural** regime is different in kind and must be described as such. The other four are
verbatim spans lifted out of the query case itself, so they share vocabulary, spelling and even OCR
artefacts with the corpus — an advantage no real user query has, and one that flatters the lexical
channel. The natural regime replaces the text with the question a lawyer would actually type, while
**keeping the qid**, so the citation-derived qrels apply unchanged and it stays comparable.

Two disclosures: it covers **30 test queries only** (built for the agent-level traces, not for the
retrieval tables in §3), and the questions are **model-authored by Claude** from each case's title
and issues text — not written by a practising lawyer, and not generated by the pipeline's own model.
A separate set of 40 **dev** natural queries (`queries_natural_dev.json`) was generated by
`qwen2.5:7b-instruct` and used **only** to calibrate the confidence threshold (§8.2.3).

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

| | 13 Aug (withdrawn) | 14 Aug #1 (withdrawn) | **14 Aug #2 (authoritative)** |
|---|---|---|---|
| Queries | judgment spans | judgment spans | **natural language** |
| Confidence threshold | 0.55 | 0.85 | **0.85, dev-calibrated** |
| Confidence signal | self-referential | self-referential | **QPP (§8.2.3)** |
| Scheduler | re-ran everything | re-ran diagnosed agent | re-runs diagnosed agent |
| `k_max` | 3 | 3 | **5** |
| FAISS dense channel | **silently dead** | loaded | loaded, 7,096 vectors |
| Coverage metric | **always 0** | content-word overlap | content-word overlap |
| Archive | `archive_thresh055_n30.json` | `run_thresh085.jsonl` | **`run_natural085v2.jsonl`** |

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

A third defect, found after the first 14 Aug run and fatal to it, is documented in §8.2.3: the
confidence score was computed from the ranker's own output, so nDCG was identically 1.0, MRR was
1.0 in 33/33 queries, and "30/30 converged" measured nothing. All three defects share a shape —
a metric that cannot fail, and therefore cannot inform.

### 8.2 Agent-level — **MEASURED**, n = 30 queries

`scripts/eval/run_agent_traces.py --n 30 --queries queries_natural.json --tag natural085` drove 30
test-split queries end-to-end
through `SchedulerAgent` (the same path the API's BackgroundTask takes), then
`scripts/eval/trace_stats.py` mined the persisted traces. **30/30 completed; 0 failed.**

**Model: `qwen2.5:7b-instruct`**, served locally by Ollama. Note that `config.py:73` declares
`deepseek-r1:8b`; `.env` overrides it and pydantic gives the env file precedence. Verified by
resolving `get_settings().ollama_model` and by 0 `<think>` traces in 240 completions.
Source: `data/reports/trace_stats.json`, raw traces in `data/traces/run_natural085v2.jsonl`.

**8.2.1 End-to-end latency** — the headline is that this system is *slow*, and the reason is legible

| Stage | n | Median (ms) | P95 (ms) | Max (ms) | Share of median |
|---|---|---|---|---|---|
| `query_planner` (1 LM call) | 30 | 9,716 | 12,641 | 18,948 | 13.1 % |
| `retriever` (FAISS + ts_rank) | 30 | 550 | 3,232 | 3,537 | 0.7 % |
| `precedent_weighting` | 30 | 144 | 835 | 1,956 | 0.2 % |
| **`debate` (7 LM calls)** | 30 | **62,891** | 73,761 | 77,304 | **85.0 %** |
| `evaluator` | 30 | 3 | 32 | 70 | 0.004 % |
| **`scheduler` (total)** | 30 | **73,981** | **91,987** | 111,615 | 100 % |

Per-agent medians sum to less than the scheduler total because the retriever, weighter and
evaluator run **once per iteration** (mean 2.30) while the table reports the median of a single
invocation. Debate runs once per query — it is guarded to the first pass unless `redebate` is
selected, which never happened here.

Read against the retrieval-side latencies in §8.1: **`hybrid_cite` answers in 3.8 ms; the agent layer
around it costs ~74,000 ms.** That ratio — roughly 19,000× — is the paper's most quotable systems
number, and it is entirely LM-bound. 8 of 8 LM calls are local; **zero external API calls, zero
monetary cost per query.**

- **PRD NFR-02 (P95 < 60 s) is missed at P95 = 92.0 s**, and the earlier P95 < 8 s target is missed
  by ~8×. Report the real distribution and revise the NFR; do not quietly restate the target.
- Debate's 7 calls are **deliberately sequential** (`app/agents/debate.py:8–13`): Ollama on a single
  GPU queues concurrent requests and each then times out waiting. State this, or a reader assumes a
  parallelism that was consciously rejected. It also means debate is ~7× parallelisable in principle
  on multi-GPU hardware — the obvious engineering headroom.

**8.2.2 Debate impact (the Q31 paragraph)**

| Quantity | Value |
|---|---|
| Queries with a usable debate trace | 30 / 30 |
| **Debate changed the top precedent** | **17 / 30 = 56.7 %** |
| Worked examples saved | 17, in `data/reports/debate_examples.json` |

> This has moved with every run — 66.7 % → 43.3 % → 30.0 % → **56.7 %** — because it depends on the
> candidate list debate is handed, which changed each time. It is **not** a stable system constant.
> Cite **56.7 %** with the run tag (`natural085v2`) attached, and say plainly that the rate varies
> with retrieval quality rather than presenting it as a property of the debate stage alone.

**State the scope precisely, because it is narrower than 56.7 % sounds.** Debate runs on iteration 1
only and sees only the **top 3** retrieved cases, so it can never promote a case ranked 4th or lower.
The rate is over the 3! = 6 reachable permutations of a 3-item list, not over the full result list.
Phrased honestly: *adversarial debate reordered the top-3 slate in two thirds of queries, changing
which precedent is presented first.*

A narratable example (`debate_examples.json[0]`) — query: *"Can a government department issue an
office memorandum or executive instruction that conflicts with statutory service rules?"*

- **was_top** `2018_7_1_378_EN` (*Government of NCT of Delhi v. Union of India*) — demoted. Opposing
  counsel: "does not directly address the issue of whether a government department can issue an
  office memorandum or executive instruction that conflicts…"
- **now_top** `2022_15_847_898_EN` (*State of Himachal Pradesh v. Raj Kumar*) — promoted. Advocate:
  "directly addresses the issue of whether executive instructions or memoranda…"
- **Synthesis rationale:** "The 2022 case directly addresses the issue of executive instructions
  versus statutory rules, making it the most relevant."

*Government of NCT of Delhi* is the Delhi services constitutional case — one of the most heavily
cited judgments in the corpus, which is exactly why the lexical and authority signals float it to
rank 1, and exactly why it is wrong here. Argumentation demotes it for a narrower, on-point
authority. That is the failure mode the debate stage exists to catch, and it is the example to
narrate.

Caveat for the write-up: no human adjudicated whether the *new* top case is actually better.
**56.7 % is a change rate, not an accuracy gain.** Do not present it as one.

**8.2.3 Scheduler behaviour — signal-directed re-scheduling**

*Run: `--tag natural085v2`, 30 natural-language test queries, threshold 0.85, `k_max` = 5.*

**How confidence is computed, and why it was rebuilt twice.** The evaluator used to report P@5,
nDCG@10 and MRR computed against *its own output scores*, because at inference time there are no
relevance labels. That is circular and it degenerated completely: the weighter sorts by score before
the evaluator sees the list, so `_ndcg` compared the list against its own sort and returned
**identically 1.0**; MRR was **1.0 in 33/33** traced queries; P@5 took **three distinct values ever**.
Any "converged" count built on that is vacuous, and the 14 Aug figure of 30/30 at 0.9877 is withdrawn.

Confidence is now a weighted sum of four post-retrieval **query-performance-prediction** signals —
clarity/NQC/WIG family — none of which the ranker can inflate by rescaling its own scores. Each is
owned by exactly one agent, so the routing policy *is* the confidence decomposition:

| Signal | w | What it measures | Owner remedy |
|---|---|---|---|
| `channel_agreement` | 0.30 | fraction of the shown top-10 that FAISS **and** `ts_rank` both retrieved | `rewiden` → retriever → weighter → evaluator |
| `issue_coverage` | 0.25 | the query's issues are grounded in the retrieved text | `replan` → planner → … → evaluator |
| `ranking_decisiveness` | 0.35 | NQC: `std(top-k) / mean(pool)` — does the ranking commit? | `reweight` → weighter → evaluator |
| `debate_consensus` | 0.10 | 1 − advocate disagreement rate | `redebate` → debate → evaluator |

Unmeasurable signals are **dropped and the remaining weights renormalised** — never scored 0, which
is what capped the old formula at 0.80 — and the scheduler keeps the **best** pass, not the last.

> `ranking_decisiveness` merges two signals that were originally separate (`score_dispersion` and
> `top_margin`), both owned by `reweight`, which moved them in **opposite** directions (+0.324 and
> −0.334 across 29 queries) so the remedy fought itself for a net ≈ +0.015. One signal per remedy is
> now enforced.

**Calibration — percentile rank, and why not min-max.** QPP signals are collection-specific and none
saturates: on the raw scale the best confidence attainable here is **0.713**, so an uncalibrated 0.85
is unreachable by construction. Signals are calibrated against the **dev** empirical CDF
(`scripts/eval/fit_confidence_threshold.py`, 40 dev queries, `data/eval/qpp_calibration.json`); a
calibrated value reads as "this query is at the Nth percentile of what the system achieves on this
collection". **No test data was used to fit it.**

The first calibrated attempt used **min-max against dev p05–p95 and manufactured its own result** —
this belongs in the reproducibility appendix:

- Hard clipping piled mass at exactly 1.0: `channel_agreement` hit 1.0 in **21/30** queries,
  `score_dispersion` in **13/30**, while `reweight` crushed `top_margin` to 0.0 in **14/30**.
- With `top_margin`'s weight at 0.15, the four remaining weights summed to **exactly 0.85** — the
  threshold. So **10 of 15 "converged" queries landed on precisely 0.8500**, and all 15 fell inside
  [0.8500, 0.8599]. Convergence was an arithmetic coincidence between the threshold and a subset sum
  of the weights.
- Apparent gains of +0.1298 were `0.20 × (1.0 − 0.35)` — a signal crossing p95 and snapping to 1.0,
  not a better ranking.

Percentile rank puts mass only at the true extremes. **Check the threshold against the weight subset
sums before setting it**: with the current weights those are 0.10/0.25/0.30/0.35/0.40/0.45/0.55/
0.60/0.65/0.70/0.75/0.90/1.00 — 0.85 is safely off the list. `fit_confidence_threshold.py` now
prints them.

| Quantity | Value |
|---|---|
| Mean iterations | **2.30** (1 iter: 6 · 2 iters: 9 · 3 iters: 15) |
| Max observed / cap | 3 / **5** — **0 %** hit the cap; the loop stops on exhausted headroom |
| **Converged** | **9 / 30 (30 %)** — 6 on the first pass, **3 via remediation** |
| Confidence, first pass | mean **0.7256**, median 0.7207, max 0.8841 |
| Confidence, best pass | mean **0.7828**, median 0.8100, max **0.9353** |
| **Best-pass − first-pass** (what the user receives), n = 24 | **+0.0715 mean**, +0.0504 median, **max +0.2545**, improved **16/24** |
| Last-pass − first-pass, n = 24 | +0.0122 mean, improved 13/24 |
| Final confidences landing on exactly 0.8500 | **0** (was 10/15) |
| Remedies invoked | `reweight` × 24, `rewiden` × 15, `replan` × 0, `redebate` × 0 |

**Does each remedy repair the signal it owns? One does, one does not.**

| Remedy | Signal it owns | n | Mean Δ | Improved |
|---|---|---|---|---|
| `rewiden` | `channel_agreement` | 15 | **+0.1383** | 9/15 |
| `reweight` | `ranking_decisiveness` | 24 | **−0.0545** | 11/24 |

**`reweight` is a failed remedy and must be reported as one.** Shifting the weighter onto factual
alignment compresses the spread *within* the top-10, and NQC is precisely a measure of that spread,
so the remedy lowers the signal it was selected to raise, more often than not (11/24 improved — worse
than chance). Two trajectories show it plainly: `0.5867 → 0.8412 → 0.5000` and
`0.6927 → 0.8392 → 0.6565`, where `rewiden` helps and `reweight` then destroys the gain. Keeping the
**best** pass rather than the last is therefore load-bearing, not a detail — without it the system
would ship the degraded ranking.

**What the scheduler is actually worth, stated conservatively:** re-retrieval works and lifts the
delivered result by **+0.0715 mean confidence on the 24 queries that iterated (16/24 improved, max
+0.2545)**, and carries **3 queries over the 0.85 bar** that would otherwise have failed. Six more
were already above it. The honest reading is that **one of four remedies is demonstrated, one is
counter-productive, and two never fired.**

**Two signals are saturated, so two remedies never ran.** `issue_coverage` and `debate_consensus`
were 1.000 on every query, leaving zero headroom, so `replan` and `redebate` were never selected —
correctly, since they could not have helped. Both definitions are too lenient: half of an issue's
content words appearing anywhere across ten concatenated judgments is a low bar, and debate almost
never flags disagreement. Tightening both is the first thing to do next, and it is also why the
5-iteration cap never binds.

**Ablation across the three runs.** An iteration loop is worth something only if the next iteration
differs **and** the metric judging it cannot be satisfied by construction:

| | 13 Aug (0.55) | 14 Aug #1 (0.85) | 14 Aug #2 (0.85, min-max) | **14 Aug #3 (0.85, percentile)** |
|---|---|---|---|---|
| Queries | judgment spans | judgment spans | natural | **natural** |
| Confidence signal | self-referential | self-referential | QPP, min-max clipped | **QPP, percentile** |
| Fatal defect | loop was a no-op | metric saturated | threshold = weight subset sum | **—** |
| Queries iterating | 0 % | 6.7 % | 96.7 % | **80 %** |
| Converged | — | 100 % | 50 % | **30 %** |
| Converged *via iteration* | — | 6.7 % | 46.7 % (inflated) | **10 %** |
| Mean iterations | 1.0 | 1.10 | 2.50 | **2.30** |

The convergence rate falls monotonically as each defect is removed. That trend is the evidence the
current number is the trustworthy one.

**8.2.4 LM output reliability and token usage**

| Quantity | Value |
|---|---|
| **LM invocations per query** | **8.0 exactly** — 240 calls / 30 queries |
| Breakdown | 30 planner + 90 advocate + 90 opposing + 30 synthesis |
| **LM output parse failures** | **0 / 240 (0.0 %)** — planner *and* debate |
| Median prompt tokens per query | **3,562** |
| Median completion tokens per query | **1,258** |
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
   `qwen2.5:7b-instruct` emits bare JSON and the recovery ladder never fires. The 1,258 median
   completion tokens are all useful output. Do not repeat the deepseek `<think>` framing — the
   hard-coded notes in older copies of `trace_stats.py` said so and were wrong.

---

## 9. Still outstanding

| Gap | What it needs | Blocking the draft? |
|---|---|---|
| ~~Agent-level table (§8.2)~~ | **DONE — 30 traces, 14 Aug, threshold 0.85** | No |
| ~~Debate-side JSON failure rate~~ | **DONE — 0 failures in 240 LM calls** | No |
| Debate *quality* (does the promoted case beat the demoted one?) | Human adjudication of the 9 reorderings in `debate_examples.json` — ~2 h | No, but §8.2.2 must be worded as a change rate until it exists |
| **`reweight` is a failed remedy** | It moves `ranking_decisiveness` **−0.055** (11/24 improved — worse than chance), because shifting weight onto factual alignment compresses spread within the top-10, which is what NQC measures. Either drop it and let `rewiden` carry the loop, or give the weighter a lever that increases within-top-k separation | **No — reported as a finding, by decision.** §8.2.3 states it plainly |
| **`issue_coverage` and `debate_consensus` are saturated** | Both 1.000 on all 30 queries, so `replan` and `redebate` never fire and their cost (+1 / +7 LM calls) is inferred, not measured. With two of four signals pinned, confidence has only ~2 effective degrees of freedom — the sharpest limit on what the scheduler can diagnose. Tighten both definitions | No — report as a limitation |
| Natural queries written by a lawyer | The 30 test questions are model-authored (§2.2). ~2 h of a practising lawyer's time would remove the caveat | No — disclose |
| Agent-level results at larger n | 30 queries; the retrieval tables use 394 | No — state the n |
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
$PY -m scripts.eval.build_natural_queries --data-dir ../data      # the 30 test questions
$PY -m scripts.eval.fit_confidence_threshold --n 40               # DEV calibration, writes
                                                                  # eval/qpp_calibration.json
$PY -m scripts.eval.run_agent_traces --n 30 --queries queries_natural.json \
    --tag natural085v2 --restart                                  # ~35 min, sequential
$PY -m scripts.eval.trace_stats --data-dir ../data
```

**Run `fit_confidence_threshold` before the traces.** Without `qpp_calibration.json` the evaluator
falls back to raw signals, whose ceiling on this corpus is 0.713 — every query would then iterate to
the cap and none would converge. The evaluator logs `calibration_loaded` or `calibration_missing` at
startup; check for it in the run log.

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
