# Verdicto v3 — Beating BM25, and Discovering Our Baseline Was Wrong

**Run date:** 13 August 2026 · **Corpus:** 7,096 Indian SC judgments, 2016–2024
**Evaluation:** 984 queries, 3,635 citation-derived judgements, temporal split, zero query leakage
**Hardware:** Apple M5, 10 cores, 16 GB RAM (all latencies measured here)
**Companions:** [RESULTS.md](RESULTS.md) (v1) · [RESULTS_V2.md](RESULTS_V2.md) (v2, reports parity with BM25)

---

## 1. Headline

Two findings, and the second one is why the first is smaller than it looks.

**(a) The system now beats BM25.** Against the BM25 baseline that RESULTS_V2 reported
parity with, `hybrid_cite` improves nDCG@10 by **+0.0190 (+36.8 % relative), CI
[+0.0113, +0.0269]** — significant, on the held-out test split.

**(b) That baseline was much weaker than anyone had measured.** Two defects, both ours:

| Defect | Effect |
|---|---|
| The lexical index covered `title + facts + issues` = **20 % of each judgment**. The reasoning section (47.7 %), where courts actually discuss precedent, was never indexed. | +0.0094 nDCG@10 once fixed, **significant** |
| `k1 = 1.2` — a default calibrated on ~500-word news articles — applied to **47,000-character** judgments. The dev optimum is **k1 ≈ 12**. | +0.0047 nDCG@10 further |

So most of (a) is us repairing our own baseline. Against BM25 rebuilt properly —
full text, tuned parameters — the honest result is narrower, and is stated in §2.

---

## 2. The result that matters: vs a *properly tuned* BM25

Test split, 394 queries, 10,000 paired bootstrap resamples. Baseline is full-text BM25
at the dev-tuned k1 = 12, b = 0.65.

| Condition | P@1 | P@5 | R@20 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| `bm25s` — the v2 lexical channel (20 % coverage, k1=1.2) | 5.59 | 3.35 | 7.88 | 8.63 | 0.0517 |
| `cite_prop` — citation propagation alone | 2.13 | 2.42 | 6.94 | 5.60 | 0.0323 |
| `bm25_full` — full text, default k1=1.2 | 7.01 | 3.94 | 8.99 | 10.04 | 0.0611 |
| **`bm25_grid`** — full text, **tuned** k1=12, b=0.65 | 6.91 | 4.37 | 9.90 | 10.21 | 0.0658 |
| **`hybrid_cite`** — **the v3 system** | **7.32** | **4.80** | **11.13** | **10.97** | **0.0707** |

`hybrid_cite` is ahead of the tuned baseline on *every* metric. Significance is mixed,
and the pattern is the interesting part:

| Metric | Δ vs tuned BM25 | 95 % CI | P(better) | Significant |
|---|---|---|---|---|
| **R@20** | **+0.0122** | [+0.0048, +0.0200] | 1.000 | **yes** |
| **nDCG@20** | **+0.0070** | [+0.0013, +0.0129] | 0.992 | **yes** |
| P@5 | +0.0043 | [−0.0002, +0.0089] | 0.970 | no (marginal) |
| nDCG@10 | +0.0049 | [−0.0013, +0.0111] | 0.939 | no |
| MRR | +0.0076 | [−0.0044, +0.0196] | 0.893 | no |

**The defensible claim:** *the v3 system significantly outperforms a tuned full-text
BM25 on recall-oriented and deeper-ranking measures (R@20, nDCG@20), and is directionally
but not significantly better at the very top of the ranking (nDCG@10, MRR).*

This is coherent rather than lucky. Citation propagation retrieves precedents that
**do not share the query's vocabulary** — that is exactly its purpose — so it adds
candidates BM25 never had, which shows up in recall and in depth-20 measures before it
shows up at rank 1. Claiming a top-of-ranking win here would misdescribe the mechanism.

---

## 3. What the system is

Two channels, fused with **plain unweighted RRF**:

```
hybrid_cite = RRF( BM25(full judgment, k1=12, b=0.65),
                   cite_prop(100 nearest earlier judgments) )
```

### 3.1 Full-text lexical channel

Indexes `title + facts + issues + reasoning + outcome` from the segmented JSON, OCR-cleaned.
7,096 documents, mean 47,080 characters. Build: 120 s. Query: 0.2 ms median.

### 3.2 Citation propagation — the system's actual contribution

> Recommend a precedent because **cases like this one cited it.**

1. Retrieve the 100 text-nearest judgments decided **before** the query year.
2. Score candidate C by `Σ over neighbours N of  1/(10 + rank(N)) · 1[N cites C]`.

If past cases on the same question relied on C, this case probably should too. This is
the structure citation-derived ground truth actually encodes.

**Why this works where the v2 authority re-rank failed.** The authority stage scored a
candidate by its **global in-degree** — how famous it is — which is nearly independent of
the query. Citation propagation is **query-conditional**: it asks what *these particular*
similar cases relied on. Same graph, opposite result:

| Use of the citation graph | Mechanism | Test nDCG@10 | Verdict |
|---|---|---|---|
| Authority re-rank (v2) | global in-degree | — | inflated by the label edge; **withdrawn** |
| Authority as fused prior | global in-degree, fused | — | dev-only gain, did not transfer |
| **Citation propagation (v3)** | *cases like Q* cite C | **0.0707 fused** | **audited clean, transfers** |

### 3.3 Leakage audit

RESULTS_V2 §4 documents a result withdrawn for citation leakage. Any channel touching the
graph is guilty until proven innocent, so `cite_prop` was audited directly on **both**
splits (`scripts/eval/audit_cite_prop.py`):

| Check | dev | test |
|---|---|---|
| Query case present in its own neighbour set | **0** | **0** |
| Neighbour decided after the query year | **0** | **0** |
| Voting edge from a case decided after the query year | **0** | **0** |
| Voting edge whose `citing_case_id == qid` (**the label edge**) | **0** | **0** |
| Coverage (queries with ≥1 vote) | 95.9 % | 99.7 % |

The channel never reads the edge `Q → C`. It infers C from *other* cases' citations,
which is prediction, not leakage.

---

## 4. Parameter selection

**Every parameter was chosen on dev. The test split was used only for the final table.**

| Parameter | Chosen | Dev evidence |
|---|---|---|
| BM25 `k1` | **12.0** | 1.2→0.1061, 4→0.1192, **12→0.1245**, 20→0.1218 (turns over) |
| BM25 `b` | **0.65** | flat plateau 0.65–0.75 |
| `w_full : w_cite` | **1.0 : 1.0** | 0.8→0.1352, **1.0→0.1457**, 1.2→0.1149 |
| `cite_neighbours` | **100** | 20→0.1408, 50→0.1435, **100→0.1457**, 200/400→0.1453 (plateau) |
| `cite_rr_k` | **10** | flat 5–10, mild decline to 60 |
| Passage channel weight | **0.0 (removed)** | 1.0→0.1355, 0.5→0.1362, **0.0→0.1408** |

Dev result at this configuration: **nDCG@10 0.1457 vs tuned-BM25 0.1249 (+16.7 % rel).**

**Two honest caveats.**

1. **The dev gain did not transfer in full**: +0.0208 on dev became +0.0049 on test
   (nDCG@10). Test queries are 2023–24, so the candidate pool is larger and the task is
   harder; every condition roughly halves. With n=394 there is also less power. The
   recall-oriented gains *did* transfer and remain significant.
2. **The `w_cite` optimum is a sharp peak at exactly 1.0** (0.1352 / **0.1457** / 0.1149
   at 0.8 / 1.0 / 1.2). It sits precisely at the equal-weight point, i.e. the system is
   plain unweighted RRF rather than a weight tuned to the dev set — reassuring, but the
   sharpness should be reported, not hidden. `cite_neighbours` by contrast has a broad,
   smooth plateau.

---

## 5. Negative results

Every one of these is a "did you try…?" a reviewer will ask. All measured on dev.

| Lever | Result | Why it failed |
|---|---|---|
| **Passage-level BM25**, max-pooled (95,470 passages) | 0.0974 vs 0.1061 doc-level; **removed from the system** | Citation prediction depends on aggregate topical match across the whole judgment; one best passage discards that evidence. |
| **RM3 pseudo-relevance feedback** | 0.1057 vs 0.1061; no setting of (α, terms, docs) beat plain BM25 | Feedback documents are entire judgments, so expansion terms are generic legal boilerplate, not case-specific language. |
| **Summary-field fusion** (BM25F-like, 3 lexical views) | 0.1067; raises P@1 to 9.65 but costs P@5 | The views are highly correlated — same text, different windows — so RRF gains little. |
| **RRF constant** k = 10 / 20 / 60 | 0.1096 / 0.1091 / 0.1092 — flat | Report as a flat ablation. |
| **Cross-encoder reranking** (ms-marco-MiniLM-L-6-v2) | P@1 4.27 vs 5.59 — **hurts** | Trained for "does this passage answer the query"; here relevance means "this case cites that one". No transfer. |
| **Authority re-rank / authority prior** | withdrawn / did not transfer | See §3.2 and RESULTS_V2 §4. |
| **Dense channel** (single-vector index, 4.7 % coverage) | 0.1389 at w=0.25 vs **0.1457** without — **hurts** | A weak channel drags a strong fusion down; RRF is symmetric. This is the v1/v2 dense index, *not* the chunked one — see the caveat below. |

**Three of the six components built for v3 earned their way out of the system.** The final
system is two channels, not five.

---

## 6. Reproducing

```bash
cd Backend
pip install bm25s PyStemmer ir_measures

# indexes
python -m scripts.ingest.build_bm25_full_index --data-dir ../data --mode doc
python -m scripts.ingest.tune_bm25_params      --data-dir ../data --grid "12.0:0.65"

# leakage audit — run this before trusting any number below
python -m scripts.eval.audit_cite_prop --data-dir ../data --split test

# final test table
python -m scripts.eval.run_eval --data-dir ../data --split test \
    --queries queries_short.json --tag _t4 --conditions bm25_grid \
    --grid-index bm25_full_k120_b065
python -m scripts.eval.run_eval --data-dir ../data --split test \
    --queries queries_short.json --tag _t4 --conditions cite_prop,hybrid_cite \
    --lex-index bm25_full_k120_b065 \
    --w-lex 0.0 --w-full 1.0 --w-cite 1.0 --cite-neighbours 100 --cite-rr-k 10
python -m scripts.eval.score --data-dir ../data --tag _t4 --baseline bm25_grid
```

**Report `hybrid_cite` against `bm25_grid`, never against `bm25s`.** `bm25s` is the
20 %-coverage, untuned index; beating it is not evidence of anything except that the v2
index was broken. The tuned `bm25_grid` is the baseline a reviewer will build.

---

## 7. Two defects found and fixed during this run

Recorded because both silently corrupted results and neither would have shown up as an error.

1. **Neighbourhood cap.** `bm25_pooled` truncated its output at `top_k = 20`, so
   `cite_prop`'s "50 neighbours" was always 20, and a sweep over 25/50/100/200 returned
   four *identical* rows. Fixing it moved test Δ nDCG@10 from +0.0032 to +0.0049.
   The identical-rows symptom is what exposed it — a sweep that does nothing is a bug,
   not a flat ablation.
2. **Chunk-index corruption.** A resumed encoding run mixed vectors encoded at
   `--max-chunks 8` (54,542 chunks) with an `owner.json` regenerated at `--max-chunks 16`
   (95,350). The FAISS index would have mapped vectors to the *wrong cases* and returned
   plausible-looking scores. Caught by the count mismatch; the parts were wiped and
   re-encoded, and `build_faiss_from_parts` now asserts `len(owner) == len(vectors)`.

---

## 8. Still outstanding

| Gap | Needs |
|---|---|
| **Chunked dense channel — still genuinely untested** | See the caveat immediately below. A CUDA box, or an idle machine with ≥32 GB RAM. |
| Agent-level results (Table 2), system characterisation (Table 3) | Ollama + ~30 queries through the API, then `trace_stats.py`. `qwen2.5:7b-instruct` is installed and verified (planner: 11.8 s, clean JSON at confidence 0.9). |
| Citation extractor precision/recall | ~2 h annotating 20 judgments (human) |
| Failure analysis, 30 cases | ~half a day (human) |
| medium / long / keyword regimes for v3 | one `run_eval` invocation each |
| Full corpus (1950–2025) | every number moves; citation resolution should improve, retrieval gets harder |

### 8.1 Caveat on the dense channel — do not over-read the negative result

The chunked dense index was **not** completed. Encoding reached 24,000 of 95,350 chunks
and then collapsed from 34 chunks/s to roughly 2 chunks/s: this is a 16 GB machine, and
between the encoder, Postgres, an Ollama 7B model and the browser it went into sustained
swap thrash (9.5 GB of 10 GB swap in use; the Postgres container was OOM-killed twice).
It was stopped rather than left to run for hours.

What §5 reports instead is a **proxy**: fusing the *old single-vector* dense index
(4.7 % document coverage — the v1/v2 index) into the final system, which **hurt**
(0.1389 vs 0.1457 at w = 0.25). That is genuine evidence that the fusion is not starved
for a third channel, and it is consistent with every other channel tried here. It is
**not** evidence that a properly chunked dense channel would hurt — the two differ by
20× in document coverage, and RESULTS_V2 §5 identifies chunked dense as the change with
real remaining upside. Treat the dense question as **open**.

To settle it: run `build_chunk_embeddings --max-chunks 16` to completion on a CUDA box
(it logs `encoding complete`), then `build_faiss_from_parts` — which now **refuses** to
build from an incomplete parts directory rather than silently truncating — then evaluate
`hybrid_v7` on **dev** before touching test.

---

**Test-set usage disclosure:** the test split was evaluated **twice** — once on the
2-channel configuration before the neighbourhood-cap fix (Δ nDCG@10 +0.0032), and once
after (+0.0049, §2). Both are reported. No parameter was ever selected on test.
All parameter selection, and the dense-channel decision, used dev only.
