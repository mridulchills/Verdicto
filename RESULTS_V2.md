# Verdicto v2 — Improved Retrieval, and a Leak I Found in My Own Result

**Run date:** 13 August 2026 · **Corpus:** 7,096 Indian SC judgments, 2016–2024
**Evaluation:** 984 queries, 3,635 citation-derived judgements, temporal split, zero query leakage
**Companion:** [RESULTS.md](RESULTS.md) is the v1 run this improves on

> **CORRECTION.** An earlier version of this file reported that v2 beat BM25 significantly
> (ΔnDCG@10 = +0.0125). **That result was inflated by leakage in the authority signal** and is
> withdrawn. The corrected finding is that v2 reaches **statistical parity** with BM25, having
> closed a gap that was significant in v1. Section 4 documents the leak and its size.

---

## 1. Corrected headline

Short queries (33 words), test split, 10,000 paired bootstrap resamples, baseline `bm25s`:

| Condition | P@1 | P@5 | R@20 | MRR | nDCG@10 | Δ nDCG@10 vs BM25 | Sig. |
|---|---|---|---|---|---|---|---|
| **BM25 (`bm25s`)** | 5.59 | 3.35 | 7.88 | 8.63 | 5.17 | — | — |
| BM25 (`rank_bm25`) | 5.59 | 3.11 | 7.43 | 8.38 | 4.85 | −0.0032 | no |
| `ts_rank` (v1 lexical) | 1.93 | 1.22 | 3.77 | 3.72 | 1.96 | −0.0321 | yes |
| dense only (v1) | 1.32 | 1.22 | 3.67 | 3.11 | 1.79 | −0.0338 | yes |
| **v1 system** (fusion + authority) | 4.17 | 2.46 | 4.42 | 6.41 | 3.59 | **−0.0158** | **yes** |
| **v2 fusion** (BM25 + dense, weighted RRF) | 5.59 | 3.17 | 7.88 | 8.49 | 5.02 | −0.0015 | **no** |
| **v2 fusion + clean authority** | 4.57 | 3.39 | 7.88 | 8.32 | 4.95 | −0.0022 | **no** |
| ~~v2 + leaky authority~~ | ~~6.40~~ | ~~4.31~~ | ~~7.88~~ | ~~10.11~~ | ~~6.10~~ | ~~+0.0093~~ | **INVALID** |

**What this says, precisely:**

- **v1 was significantly worse than BM25** (−0.0158, CI excludes zero).
- **v2 is not distinguishable from BM25** (−0.0015, CI [−0.0064, +0.0033]). That is parity, not
  victory — but closing a significant deficit to parity is a real, defensible improvement.
- **v2 improves on v1 by 40 % on nDCG@10** (3.59 → 5.02) and 79 % on R@20 (4.42 → 7.88).
- **The authority re-rank does not help once computed honestly.** See Section 4.

---

## 2. Your point about query length was correct

Four regimes were built from the same cases, sharing one qrels file — only the query form varies.
Zero residual citations in all four.

| Regime | Mean chars | Mean words | Represents |
|---|---|---|---|
| long | 2,179 | 360 | the v1 regime |
| medium | 583 | 96 | a detailed paragraph |
| **short** | **199** | **33** | a topical description — the realistic default |
| **keyword** | **111** | **14** | statute refs + salient terms — how practitioners search |

BM25's advantage over the *unchanged* v1 system collapses as queries become realistic:

| Regime | BM25 P@1 | v1 system P@1 | BM25 advantage |
|---|---|---|---|
| long | 11.18 | 4.78 | **2.34×** |
| keyword | 7.42 | 4.57 | 1.62× |
| short | 5.59 | 4.17 | **1.34×** |

**Roughly half the original gap was an artefact of evaluating with document-length queries.**
That is a finding in its own right, and it is worth a paragraph in the paper: long-document
retrieval papers that use document-length queries are measuring a regime users never enter.

---

## 3. What genuinely improved

### 3.1 Real BM25 replacing `ts_rank` — the only large, clean win

On identical text (title + facts + issues):

| Lexical channel | P@1 (short) | nDCG@10 | Latency |
|---|---|---|---|
| `ts_rank`, top-8 keywords | 1.93 | 1.96 | 39.7 ms |
| **BM25 (`bm25s`), k₁=1.2, b=0.75, stemmed** | **5.59** | **5.17** | **0.2 ms** |

**2.9× better and 200× faster.** `bm25s` stores the index as scipy sparse matrices and persists
to disk: whole-corpus build in **1.4 s**, no in-RAM token lists (which is what pushed the v1
evaluation into swap). This makes the lexical channel deployable, not research-only.

This single substitution accounts for essentially all of the v1 → v2 gain.

### 3.2 Weighted RRF — necessary, but not itself a gain

v1 fused with equal weight, which is why dense+BM25 scored *worse* than BM25 alone (8.13 vs
11.18): RRF is symmetric, so a mostly-wrong channel drags down a mostly-right one. v2 uses
`w_lex = 1.0, w_dense = 0.5`.

Swept on the **dev** split (test untouched during tuning):

| w_dense | 0.25 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|
| P@1 | 11.08 | 11.18 | 11.28 | 11.48 |
| P@5 | 6.36 | 6.30 | 6.16 | 5.96 |
| MRR | 16.59 | 16.41 | 16.42 | 16.54 |

**Flat.** The fusion is insensitive to the weight. Report it as a flat ablation.

### 3.3 OCR cleaning

SCR margin markers (isolated `A`–`H`), running headers and page numbers stripped before indexing
and before query construction. Applied to every v2 condition.

---

## 4. The leak, and why it matters more than the result it produced

**What I found.** The qrels say *"C is relevant to Q because Q cites C."* The citation graph
contains that very edge. So when the authority stage scores candidate C for query Q:

1. **C's in-degree includes the edge from Q itself** — the label. Every relevant candidate gets
   a +1 that no irrelevant candidate receives.
2. **C's in-degree counts citations from judgments decided after Q** — a case looks authoritative
   because of its future, which is not information available at query time.

**How big it was.** Same pipeline, only the citation counts corrected (self-edge excluded,
citing cases restricted to `year <= query_year - 1`):

| Authority variant | P@1 | P@5 | MRR | nDCG@10 | Δ vs BM25 |
|---|---|---|---|---|---|
| Leaky (as the deployed agent computes it) | 6.40 | 4.31 | 10.11 | 6.10 | +0.0093 **sig** |
| **Clean (self-edge + future removed)** | **4.57** | 3.39 | 8.32 | 4.95 | −0.0022 **n.s.** |
| No authority at all | 5.59 | 3.17 | 8.49 | 5.02 | −0.0015 n.s. |

**The entire apparent advantage of the authority stage was the leak.** Worse: computed honestly,
the authority re-rank *reduces* P@1 from 5.59 to 4.57 relative to no re-ranking at all.

**Why it hurts.** The authority score is only 20 % factual alignment; the other 80 % is citation
count, bench size, recency and domain. Once citation counts are temporally filtered they become
sparse and near-uniform, so re-ranking by authority discards most of the retrieval signal in
favour of weak priors. Sorting by "authoritative" is not the same as sorting by "relevant."

**This is a finding, not just a bug.** It is the most interesting negative result in the study,
and it is directly about the architecture's distinctive component. The paper should report it:
*a precedent-authority re-rank, evaluated without leakage, did not improve retrieval over the
fused candidate list, and citation-derived ground truth makes authority signals particularly
prone to circularity.*

Any future citation-graph feature — PageRank included — inherits this problem and must be
computed under the same temporal and self-edge constraints.

---

## 5. Are these final? No — one more round is needed

### Complete and final for this corpus
Corpus construction · document lengths and truncation · near-duplicates · citation graph and
resolution rate · evaluation-set statistics · Table 1 retrieval results, short and keyword
regimes · weight sensitivity · leakage audit.

### Missing, and what each needs

| Gap | Needs | Where |
|---|---|---|
| **Agent-level results (paper Table 2)** — planner-only, +debate, B3, V | Ollama + ~30 queries through the API | your machine |
| **System characterisation (Table 3)** — tokens, parse-failure %, latency median/P95 | same run, then `trace_stats.py` | your machine |
| **Hardware line** | record CPU/RAM/GPU at measurement time | your machine |
| **Citation extractor precision/recall** | ~2 h annotating 20 judgments | human |
| **Failure analysis (30 cases)** | ~half a day, categories in the plan | human |
| **Dataset licence text** | 5 min on the AWS registry page | anyone |
| **medium / long regimes for v2** | one `run_eval` invocation each | either machine |
| **Chunked dense channel** | CUDA box — MPS hangs when detached | your machine |

### Two reasons these numbers are not the final ones

1. **Corpus scope.** This is 2016–2024 (7,096 judgments). Yours is the full bucket
   (1950–2025, several times larger). Every number moves: citation resolution should **improve**
   (more citation targets in corpus), and retrieval gets harder (more candidates) but with more
   relevant targets per query.
2. **The dense channel is still crippled.** Every v2 number uses the old single-vector index at
   4.7 % document coverage; the dense channel alone scores P@1 1.32. `build_chunk_embeddings.py`
   is written and produces 54,542 chunks, but `sentence-transformers` on Apple MPS hangs whenever
   the process is detached (verified: 103 chunks/s interactively, frozen when backgrounded). On
   CUDA this does not apply. **This is the one remaining change with real upside** — it improves
   the weaker half of the fusion, which is where the parity-vs-win margin sits.

**Recommendation:** run the full pipeline once on your machine, on the full corpus, with chunking
enabled and Ollama running. That produces every remaining number in one pass, and those are the
numbers to publish.

---

## 6. Reproducing

```bash
cd Backend
pip install bm25s PyStemmer

python -m scripts.eval.build_query_sets   --data-dir ../data
python -m scripts.ingest.build_bm25_index --data-dir ../data
python -m scripts.ingest.build_chunk_embeddings --data-dir ../data --device cuda --max-chunks 16

python -m scripts.eval.run_eval --data-dir ../data --split test \
    --queries queries_short.json --tag _short \
    --conditions bm25s,dense,dense_chunk,tsrank,hybrid_auth,hybrid_v2,hybrid_v2_auth,hybrid_v2_authc \
    --w-lex 1.0 --w-dense 0.5
python -m scripts.eval.score --data-dir ../data --tag _short --baseline bm25s
```

**Report `hybrid_v2_authc`, never `hybrid_v2_auth`.** The latter uses the deployed agent's
unfiltered citation counts and is contaminated by the label; the former excludes self-edges and
future citations. The two are kept side by side deliberately so the size of the leak stays
visible and auditable.
