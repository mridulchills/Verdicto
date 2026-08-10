# Verdicto — Implementation Plan to Get Every Number

**Companion to** [PAPER_ANSWERS_ICMLDE.md](PAPER_ANSWERS_ICMLDE.md), which says what is true today.
This document says what to run, in what order, to turn every `NO DATA` in that file into a measured number.

**Target:** one Elsevier/Procedia paper — the full system, with retrieval ablations as the core evidence.

---

## What already exists

Confirmed from the repository and from what you've described:

- The corpus is downloaded, extracted, segmented, embedded, and indexed — the whole AWS bucket.
- Postgres is running with the `cases` table populated. (It must be: `POST /query` writes a `QueryRecord` before doing anything else, so a missing database would have failed immediately rather than returning results.)
- The pipeline has run end to end, demonstrated on a local frontend and backend.

So Steps 1 and 2 of the old ingestion plan are **done**. What is missing is not the corpus — it's the *metadata on top of it*, the *citation graph*, and *any evaluation at all*.

## What I have added to the repository

Everything below is written, compiles, and is unit-tested where it can be tested without data.

| Path | Purpose |
|---|---|
| `Backend/scripts/lib/report.py` | Shared reporting. Every script writes `<data>/reports/<name>.json` **and** a paste-ready `.md`, stamped with timestamp, git commit, and **auto-detected hardware** (Q67). |
| `Backend/scripts/lib/citations.py` | Indian SC citation extraction, canonical normalisation, and `strip_leakage()`. **Tested** — see "Verification" below. |
| `Backend/scripts/eval/probe_citations.py` | **Run this first.** Feasibility probe, needs no DB. |
| `Backend/scripts/ingest/load_metadata.py` | Parquet → `cases`. The root unblock. |
| `Backend/scripts/ingest/extract_citations.py` | Builds the citation graph. |
| `Backend/scripts/eval/build_golden_set.py` | Queries + TREC qrels, with leakage stripping. |
| `Backend/scripts/eval/run_eval.py` | Six retrieval conditions → TREC run files. **No LLM.** |
| `Backend/scripts/eval/score.py` | `ir_measures` + paired bootstrap → the results table. |
| `Backend/scripts/eval/corpus_stats.py` | Attrition, lengths, truncation loss, year coverage. |
| `Backend/scripts/eval/dedup.py` | Near-duplicate detection over existing vectors. |
| `Backend/scripts/eval/trace_stats.py` | Mines `agent_trace` for latency, iterations, debate impact. |

Modified: `extract_text.py`, `segment_text.py`, `build_embeddings.py` (now log to files), and `app/agents/scheduler.py` (records per-query token usage).

### Two performance bugs fixed in `build_embeddings.py`

1. **Removed `await asyncio.sleep(0.5)` per document** — rate-limiting left over from the Gemini API era. There is no API to rate-limit; the model is local. On 20,000 documents that was 2.8 hours of sleeping.
2. **Batched the encoder.** It called `encode()` once per document; `SentenceTransformer.encode()` takes a list and batches on the GPU. Typically 10–50×.

Relevant only if you re-embed. You probably won't need to unless you adopt chunk-and-pool (Step 10).

---

## Install once

```bash
cd Backend
pip install ir_measures rank_bm25 numpy pandas pyarrow
pip install psutil          # optional — adds RAM to the hardware stamp
```

All commands below are run **from `Backend/`**, with `--data-dir` pointing at your data root (`../data` if it sits beside `Backend/`, otherwise an absolute path like `D:\Verdicto\data`).

---

# Step 0 — Baseline measurements (free, run today)

Nothing depends on these; they are pure reads of what you already have. Run them now so the corpus section of the paper stops being adjectives.

```bash
python -m scripts.eval.corpus_stats --data-dir ../data --database-url postgresql+asyncpg://verdicto:verdicto_secret@localhost:5433/verdicto
python -m scripts.ingest.segment_text --data-dir ../data --rescan
python -m scripts.eval.dedup --data-dir ../data
python -m scripts.eval.trace_stats --data-dir ../data
```

**Answers:** Q5, Q27, Q28, Q31, Q33, Q36, Q37, Q42, Q44, Q45, Q46.

Note `segment_text.py --rescan` — I added it so you can produce the segmentation-quality report from the corpus you already segmented, without re-segmenting anything.

**Read `reports/corpus_stats.md` carefully.** It cross-checks `cases` row count against FAISS vector count. If those disagree, `populate_db.py` and `build_faiss_index.py` saw different file sets, the `case_id` ↔ vector mapping is skewed, and retrieval has been returning wrong case_ids. Fix that before anything else.

---

# Step 1 — The feasibility probe (run before building anything)

Everything downstream rests on one assumption: *judgments cite earlier judgments, and enough of those cited cases are inside the corpus to serve as labels.* Test it before investing.

```bash
python -m scripts.eval.probe_citations --data-dir ../data --sample 300
```

Needs no database and no metadata. Reads the extracted `.txt` files directly.

The headline is **"% of citations whose target year exists in the corpus"** — a strict upper bound on resolution, measurable today:

| Result | Action |
|---|---|
| **> 20%** | Proceed to Step 2. |
| **5–20%** | Proceed, but expect few labels per query. Lead with nDCG@10 and MRR, not P@10. |
| **1–5%** | Check the "cited years missing from corpus" table — you may have a gap. |
| **< 1%** | Stop. Go to Step 4's fallbacks. |

With the whole bucket ingested I expect this to come back healthy — that is exactly the condition the approach needs.

---

# Step 2 — Load the metadata (the root unblock)

Every missing number traces back through this chain:

```
Parquet metadata downloaded but never loaded
   → cases.citation, .bench, .decision_date are NULL for every row
        → no citation can resolve to a case_id  → no citation graph
             → the 0.35 authority weight is identically zero
             → no citation-derived ground truth → no metrics at all
        → bench is NULL → the 0.20 bench weight is a constant
```

`populate_db.py` writes only `case_id`, `year`, `title`, and the four segments. Everything else was left NULL.

**2a. Discover the real schema.** The Parquet columns are whatever the bucket publishes, so the script prints them rather than guessing:

```bash
python -m scripts.ingest.load_metadata --data-dir ../data --inspect
```

**2b. Dry run**, checking the mapping table in the output:

```bash
python -m scripts.ingest.load_metadata --data-dir ../data --dry-run
```

If a column mapped wrongly, override it — repeatable:

```bash
python -m scripts.ingest.load_metadata --data-dir ../data --dry-run --map citation=neutral_cite --map bench=coram
```

**2c. Apply:**

```bash
python -m scripts.ingest.load_metadata --data-dir ../data
```

**Success criterion:** `reports/load_metadata.md` shows a high non-NULL share for `citation`. If it is 0, Step 3 cannot work — go back to `--inspect`.

**Answers:** Q21 (bench distribution), Q43 (subject matter, if the Parquet carries one), and unblocks everything below.

---

# Step 3 — Build the citation graph

```bash
python -m scripts.ingest.extract_citations --data-dir ../data --limit 500 --dry-run   # smoke test
python -m scripts.ingest.extract_citations --data-dir ../data --dry-run               # full dry run
python -m scripts.ingest.extract_citations --data-dir ../data --truncate              # apply
```

**Watch `in_corpus_resolution_rate_pct`.** This is the real number the probe estimated.

The report includes a **most-common-unresolved-strings** table. If a reporter format you recognise appears there repeatedly, add its pattern to `scripts/lib/citations.py` and re-run — that is the single highest-yield tuning loop available.

It also prints the **20 most-cited cases by in-degree**. Eyeball them: if they aren't recognisable landmark judgments, resolution is matching the wrong things. That check takes ten seconds and catches a whole class of silent errors.

`--use-names` enables case-name fallback matching: higher recall, lower precision. Try both and report which you used.

**Answers:** Q18 (nodes and edges), Q19, Q20.

### Validate the extractor — 2 hours, and the paper needs it

Hand-annotate every citation in 20 judgments, run the extractor over the same 20, report precision and recall. Keep **two** recall figures separate:
- recall of citation *strings* in the text;
- the share that *resolve to an in-corpus case*.

The second is much lower and is the one that actually bounds your ground truth.

---

# Step 4 — Build the golden set

```bash
python -m scripts.eval.build_golden_set --data-dir ../data --graded
```

Produces `queries.json`, `qrels.txt` (TREC format), and `leakage_samples.txt`.

**Three things to check in the report before continuing:**

1. **`queries_with_residual_citations` must be 0.** Anything higher means the stripper missed a reporter format. Do not run the evaluation until it is zero.
2. **Read `data/eval/leakage_samples.txt` by hand.** Confirm no case names or citations survive. Put one stripped query in the paper's appendix — it pre-empts the first question any reviewer asks.
3. **Check `mean_relevant_per_query`.** Under 5 and P@10 has a ceiling below 0.5 — lead with nDCG@10 and MRR. The report says which to use.

The split is **temporal**: queries sorted by year, earliest 60% dev, latest 40% test. More defensible than random, and it eliminates the Q56 leak automatically.

**Answers:** Q47, Q48, Q50, Q51, Q52, Q53, Q54.

### If Step 3's resolution rate was too low

In order of preference:

1. **Look for an existing benchmark** — an ILDC-derived or COLIEE-style Indian set. Half an hour of searching. If one exists you skip the leakage minefield entirely and compare against published numbers.
2. **Hand-annotate 30–50 queries.** Slow, but a guaranteed floor and what the PRD originally planned.
3. **Report without relevance metrics** — corpus construction, system description, latency, qualitative examples, inter-channel agreement. Weaker, but publishable as a system paper.

---

# Step 5 — Run the retrieval conditions

```bash
python -m scripts.eval.run_eval --data-dir ../data --split test
```

Six conditions: `dense`, `tsrank`, `bm25`, `hybrid`, `hybrid_bm25`, `hybrid_auth`.

**No LLM is involved.** The retriever reads `reformulated_queries` from its input, and an empty list is simply empty — so the Query Planner is bypassed entirely. **The paper's core evidence is therefore deterministic, reproducible, and completely unaffected by the local 8B model's quality.** That is the strongest structural advantage this project has; lean on it.

Leakage controls applied on **every** condition:
- temporal filter (`year < query_year`) on **both** channels — including FAISS, which the application itself does not do;
- self-exclusion of the query case;
- **rank renumbering after filtering** — RRF consumes ranks, so filtering without renumbering would silently corrupt the fusion.

Two conditions worth noting. `tsrank` is what the deployed system actually uses — and it is **not BM25**, it is Postgres's own ranking, with no k₁ or b. `bm25` is a true BM25 baseline via `rank_bm25` (k₁=1.5, b=0.75 — report these). Having both means you can describe the system honestly *and* compare against something reviewers recognise.

---

# Step 6 — Score and test significance

```bash
python -m scripts.eval.score --data-dir ../data --baseline bm25 --primary nDCG@10
```

Produces the **main results table**, paste-ready, plus a paired bootstrap (10,000 resamples) against the baseline with 95% CIs.

Also writes `per_query_scores.json` and prints the **largest hybrid-over-dense wins** (Step 9's material) and the **largest losses** (Step 8's material).

Metrics come from `ir_measures`, never from `app/agents/evaluator.py`. The in-repo evaluator computes nDCG over the system's *own* scores with the "ideal" being those same scores re-sorted — so it is ≈1.0 by construction and measures whether the list is sorted, not whether it is relevant. Keep it for the scheduler's gating decision; never report it.

**Answers:** Q57, Q60, Q63.

**A correction to my earlier note:** I previously said the rank-1–3 score floor in `scheduler.py:309` must be removed before any measurement. That was over-stated. The harness scores from `rrf_score` and `authority_score` directly and never touches `final_score`, so the floor cannot contaminate the reported numbers. It still matters if you ever report the in-pipeline evaluator's output — which you shouldn't — and it is still worth removing for honesty in the UI, but it is **not** a blocker. I've moved it out of the critical path.

---

# Step 7 — Agent-level conditions

These need the scheduler in the loop, and therefore the LLM. Smaller N is fine — 30–50 queries is enough for latency and iteration statistics.

Before running, two one-line changes:

**Fix the seed** in `gemini_client.py:139-143`:
```python
"options": {"temperature": temperature, "num_predict": 1024, "seed": 42},
```

**Consider switching models.** The problem with `deepseek-r1:8b` isn't raw capability, it's **JSON adherence** — it emits `<think>` traces and prose around its JSON, which is exactly why `debate.py` needs a four-stage regex recovery ladder. An instruction-tuned model (`qwen2.5:14b-instruct`, `llama3.1:8b-instruct`) with Ollama's constrained JSON mode would be far more reliable at similar latency, because you stop paying for discarded reasoning tokens. Note that `format: "json"` is **already implemented** in the client and simply never triggered — no agent passes `response_schema`.

Then run queries through the API and mine the traces:

```bash
python -m scripts.eval.trace_stats --data-dir ../data
```

**Read the iteration distribution first.** My prediction from Q23: because refinement iterations are byte-identical to the first, confidence cannot change between passes, so queries either stop at 1 or run to the cap — **a bimodal distribution with nothing at 2**. The script flags this automatically. If it appears, that is a legitimate reportable negative result about naive iteration, and it is a genuine finding rather than a gap.

**Answers:** Q27, Q28, Q31, Q33, Q36, Q37, Q67.

### Optional: make the scheduler claim testable

To measure scheduling rather than repetition, vary the input per iteration — in `scheduler.py`, inside the while loop:

```python
reforms = plan_result.get("reformulated_queries", [])
retriever_input = {
    **plan_result,
    "filters": filters,
    "reformulated_queries": reforms[iteration - 1: iteration],   # cycle, don't repeat
}
```

This reuses the reformulations the planner already generates and the retriever currently discards, so it fixes Q7 and Q58 with one change. **Optional now** — with one paper, reporting the null result honestly (Step 7 above) is a legitimate alternative.

---

# Step 8 — Failure analysis

From `score.py`'s "Top 10 hybrid LOSSES", take the 30 worst queries and categorise each:

| Category | Diagnostic signal |
|---|---|
| Segmentation error | `segmentation_method == "heuristic_fallback"` on the retrieved case |
| Truncation miss | Relevant content beyond the 1000-char cut |
| Lexical miss | Query terms absent from the top-8 keyword list |
| Lexical blind spot | Relevant content only in `reasoning_text` — **not indexed** |
| Authority mis-weighting | Only recency/domain were live before Step 2 |
| Debate error | Synthesis promoted a weaker case |
| Planner error | `confidence == 0.3` marks the JSON-degradation path |
| **Missing from corpus** | Gold case not in `cases` at all |

That last row matters more than it looks: some "failures" will be cases never ingested, and separating those from genuine retrieval misses changes the story considerably.

---

# Step 9 — Qualitative examples

`score.py` prints the largest hybrid-over-dense wins. For the top three, report the gold case's rank in the dense run versus the lexical run.

The mechanism is predictable and easy to narrate: a query containing a **specific statutory token** — a section number, an Act name, an Article — which the lexical channel matches exactly and the dense channel misses, because `all-MiniLM-L6-v2` has no legal pretraining and because the document vector covers only the first ~1000 characters. Your own smoke-test query (*"Can an unstamped arbitration agreement be enforced under the Arbitration and Conciliation Act 1996?"*) is exactly this shape.

Present as: query → gold case → dense rank → lexical rank → fused rank → one sentence of mechanism.

---

# Step 10 — Optional improvements, in value order

| # | Change | Why |
|---|---|---|
| 1 | **Chunk-and-pool embeddings** (~250-token windows, mean-pool) | Likely the largest retrieval-quality gain available. Requires re-embedding — now fast, given the batching fix. |
| 2 | **Index `reasoning_text` + `outcome_text`** in the tsvector | The lexical channel currently sees roughly half of each document. A new Alembic migration. |
| 3 | **PageRank** over the citation graph | `pip install networkx`, substitute for raw citation count, report both as conditions. |
| 4 | **RRF k sweep** (10 … 100) | A real fusion parameter, standard to report. One loop over `run_eval.py`. |
| 5 | **Weight grid search** on the dev split | Report hand-set vs fitted as two rows. |

---

# Ordering, and what blocks what

```
Step 0  baseline measurements ─────────────► independent, run now
Step 1  feasibility probe ─────────────────► gates everything below
Step 2  load metadata ─────────────────────► THE root unblock
   └──► Step 3  citation graph
           └──► Step 4  golden set
                   └──► Step 5  run conditions
                           └──► Step 6  score  ──► Steps 8, 9
Step 7  agent-level runs ──────────────────► independent of 2-6
Step 10 improvements ──────────────────────► after a baseline exists
```

Steps 0, 1 and 7 can run at any time. Steps 2 → 6 are strictly serial. Step 2 is the bottleneck: if the Parquet mapping doesn't work, nothing after it does.

---

# Verification already done

- All 15 files compile.
- `citations.py` tested against a synthetic judgment: 5 SC citations across AIR / SCC (both orderings) / SCR / INSC correctly extracted and normalised; 1 High Court citation correctly excluded as out-of-scope; 2 case names detected; discussion-context flagging works for graded relevance.
- **`strip_leakage()` verified to leave zero residual citations and zero residual case names** — the Q48 control works.
- `name_key()` maps "X Versus Y" and "X v. Y" to the same key.
- `report.py` writes valid JSON + Markdown and auto-detects hardware.

**Not tested:** anything touching the database, FAISS, or Parquet — no data on this machine. Expect to iterate on the Parquet column mapping in Step 2a; that's what `--inspect` and `--dry-run` are for.

---

# One open question

`load_metadata.py` matches Parquet rows to `cases` on `case_id`, normalising away paths and extensions. But your `case_id` values come from segmented filenames (`2024_1_1_10_EN`) and the Parquet may key on something else entirely — a docket number, a URL, a diary number.

Run Step 2a and check `metadata_rows_without_matching_case` in the dry-run report. If it's high, tell me what the Parquet's identifier column actually looks like and I'll write the join. This is the one place where I'm working blind and the answer isn't guessable from the code.


```bash
cd Backend
pip install ir_measures rank_bm25 numpy pandas pyarrow

python -m scripts.eval.probe_citations --data-dir ../data --sample 300      # gates everything
python -m scripts.eval.corpus_stats    --data-dir ../data --database-url <url>
python -m scripts.ingest.segment_text  --data-dir ../data --rescan
python -m scripts.eval.trace_stats     --data-dir ../data
```
