# Verdicto — Complete Answers to the ICMLDE Open Questions

**Prepared:** 10 August 2026 · **Repository state:** commit `96210ee`, branch `main`
**Rule followed throughout:** every question is answered. Where a number does not exist, the answer states that plainly **and gives the exact procedure to obtain it** — the command, the SQL, or the script. Nothing is estimated, and nothing is filled in from the synopsis.

**Four corrections to my earlier note, made at the team's instruction:**
1. The agents live in **`Backend/app/agents/`**. That is the system.
2. `Backend/agents/` is **stale scaffolding** from the two "Initial agents boiler plate" commits. It is imported by nothing, it is not part of the project, and it should be deleted from the repository. It is mentioned in this document exactly once more (Q1) and then never again.
3. The LLM is a small local model and the numbers it produces will not be strong. Section 0.2 addresses that head-on, including which results are affected and which are not.
4. **There is now one paper, not two.** The question document was written against a two-submission plan — it refers to "Paper 1" and "Paper 2" throughout, and Part C is entirely about managing dual submission. That plan is dropped. **Scope of the single paper: the full system — the multi-agent architecture as the contribution, the retrieval ablations as the core evidence, and the agent/debate ablation reported honestly alongside.** Section 0.4 explains what this changes; every answer below is written for that one paper.

---

## Status legend

| Tag | Meaning |
|---|---|
| **IMPLEMENTED** | On the live path, works as described |
| **PARTIAL** | Exists but materially weaker than the drafted material claims |
| **ABSENT** | Does not exist in the repository |
| **MEASURABLE NOW** | Not yet measured, but obtainable from data/instrumentation that already exists — procedure given |
| **NEEDS BUILD** | Cannot be measured until something is built first — dependency and procedure given |

---

# 0. Read this first

## 0.1 The dependency chain that governs everything

Almost every missing number traces back to one root cause, through a chain that must be walked in order. This is the single most useful thing in this document:

```
Parquet metadata is downloaded but never loaded into Postgres
        │   (populate_db.py writes only case_id, year, title, and 4 text segments)
        ▼
cases.citation, .bench, .decision_date, .disposal_nature are NULL for every row
        │
        ├──► bench signal is a constant  ──────────────► authority weight 0.20 inert
        │
        └──► no citation string to match against
                    │
                    ▼
             citation graph cannot be built
                    │
                    ├──► authority weight 0.35 identically zero
                    │
                    └──► cited-precedents-as-labels ground truth impossible
                                │
                                ▼
                         no qrels ──► no P@k, nDCG, MRR, no baselines,
                                      no ablations, no grid search,
                                      no significance test
```

**Loading the Parquet metadata is a small script and it is the root unblock.** It is Task 1 in the action plan for that reason. Nothing in Part B4 is reachable without it.

## 0.2 The model is small — here is exactly what that costs, and what it does not

The team is right that `deepseek-r1:8b` on localhost is a weak model and the numbers will reflect it. The important question is *which* numbers. The answer is more favourable than it first appears.

**The LLM touches only two of the six agents.** Retrieval, fusion, authority weighting, and evaluation are pure computation — FAISS, Postgres, and arithmetic. The model is used by the Query Planner (1 call) and the Debate agent (7 calls). Nothing else.

| Result | Depends on the LLM? | Consequence |
|---|---|---|
| **Retrieval ablations** (BM25 / dense / hybrid / −authority) | **No — runnable with the LLM switched off entirely** | Model-independent, deterministic, reproducible. **This is the paper's core evidence.** |
| B1 semantic-only, B2 hybrid single-pass | Only via query reformulation | Can also be run LLM-free |
| B3 vs V (the scheduler condition) | Indirectly — the gate reads the Evaluator, which is arithmetic | Weakly dependent |
| Debate quality, consensus rationale, explanations | **Yes, heavily** | This is where the weak model actually hurts |

**Critically: the retriever runs without the planner.** `run()` reads `original_query` and `reformulated_queries` from its input dict and `reformulated[:1]` on an empty list is simply empty ([`retriever.py:195-204`](Backend/app/agents/retriever.py#L195-L204)). So an evaluation harness can call:

```python
RetrieverAgent(db_session=db).execute({
    "query_id": qid,
    "original_query": query_text,
    "reformulated_queries": [],     # ← no LLM anywhere in the pipeline
    "filters": {"year_to": query_year - 1},
})
```

**Every number in the paper's main retrieval table can therefore be produced with no LLM, no GPU, no non-determinism, and no dependence on model quality.** That is a genuinely strong position: the paper's core evidence is insulated from the weak model, and only the agent-level results inherit its limitations.

### What to do about the model

Three options, in increasing order of effort:

**(a) Keep it and report honestly.** Frame local inference as a deployment constraint, not an accident: judgment text never leaves the premises, per-query cost is zero, and the system runs air-gapped. For Indian judicial deployment that is a real argument. State the model, the parameter count, and the hardware, and let the debate numbers be what they are. A modest or null debate effect, honestly reported with the model named, is a publishable finding — *"an 8B locally-hosted model was insufficient to improve ranking through adversarial debate"* is a legitimate negative result and reviewers accept those far more readily than inflated positive ones.

**(b) Swap to a better-suited local model — cheap, and likely the best value.** The specific problem with `deepseek-r1:8b` is not raw capability, it is **JSON adherence**. It is a reasoning-distilled model that emits `<think>…</think>` traces and prose around its JSON, which is precisely why [`debate.py:86-107`](Backend/app/agents/debate.py#L86-L107) needs a four-stage regex recovery ladder. An instruction-tuned model of similar or larger size (`qwen2.5:14b-instruct`, `llama3.1:8b-instruct`) with Ollama's constrained JSON mode would be dramatically more reliable at the same or lower latency, because you stop paying for discarded reasoning tokens.

**Two changes make this concrete, and both are small:**

1. Change `ollama_model` in [`config.py:73`](Backend/app/core/config.py#L73). One line.
2. **Turn on constrained JSON output, which is already implemented and currently unused.** The client sets Ollama's `format: "json"` whenever `response_schema` is passed ([`gemini_client.py:145-146`](Backend/app/core/gemini_client.py#L145-L146)) — but no agent passes it, so every call today is free-form text. Passing a schema to the four LLM calls would eliminate most parse failures outright.

**(c) Use a hosted API for the paper runs only.** The client is one file with a two-method surface (`generate_text`, `generate_embedding`). Swapping the transport is contained. This weakens the local-inference contribution, so if you do it, run *both* and report the comparison — "8B local vs hosted" then becomes an ablation and a contribution rather than a retreat.

**My recommendation: (b), plus report the parse-failure rate as a measured quantity.** See Q33 for how — it turns the model's weakness into a number you can defend rather than a vulnerability you hope nobody probes.

## 0.3 Four things that must be fixed before any measurement run

Running experiments before these are done produces numbers you will have to throw away.

| # | Problem | Fix | Where |
|---|---|---|---|
| 1 | Ranks 1–3 get a hardcoded score floor of 0.75/0.70/0.65 | Delete the two lines | [`scheduler.py:309-310`](Backend/app/agents/scheduler.py#L309-L310) |
| 2 | FAISS channel ignores year filters entirely — a temporal split would leak through the semantic half of the system | Post-filter FAISS hits on year before the RRF merge | [`retriever.py:211`](Backend/app/agents/retriever.py#L211) |
| 3 | LLM calls are unseeded | Add `"seed": 42` to the Ollama options payload | [`gemini_client.py:139-143`](Backend/app/core/gemini_client.py#L139-L143) |
| 4 | `citations` table is empty, so authority weight 0.35 is identically zero | Task 1 + Task 2 of the action plan | — |

## 0.4 One paper, not two — what changes

The original plan was two Elsevier/Procedia submissions with the contribution split between them. **That split could not have been made honestly.** Per Q13, the intended division — one paper asserting three similarity channels, the other giving their formulae — describes a system that does not exist: there is no structural channel, and there are no such equations. Preserving the split would have required one paper to assert something untrue and the other to formalise something absent. Collapsing to a single paper dissolves that problem rather than managing it.

**What the single paper is.** A system-and-evaluation paper. Contributions, in the order they should appear:

1. **A six-agent architecture for precedent retrieval** with per-stage traces persisted and served live — auditability that is genuinely implemented (Q17, Q32).
2. **Hybrid retrieval**: exact dense search fused with PostgreSQL full-text ranking via RRF, followed by an authority re-rank (Q13, Q59).
3. **Evaluation on a citation-derived benchmark** built from the corpus itself, with temporal splitting and explicit leakage controls (Q47, Q48, Q54).
4. **Fully local, zero-egress deployment** — no API calls, no data leaving the premises (Q37).

**What this removes from the workload:**

| Removed | Why |
|---|---|
| All of Part C's dual-submission handling | Only one submission exists (C1–C4 rewritten below) |
| A second related-work and a second discussion section | One of each |
| The artificial contribution boundary | No longer needs defending to an Elsevier duplicate-submission screen |
| Pressure on the scheduler claim | It is now one result among several, not a paper's entire thesis — see Q58 |

**What this does not remove: anything in Tier 0.** Ground truth, the citation extractor, the metadata loader, and the eval harness are required for any paper at all. Dropping to one paper cuts writing and coordination, not measurement.

**One consequence worth naming.** With the scheduler no longer carrying a whole paper, the Q58 fix moves from *mandatory* to *strongly recommended*. You may now report the scheduler descriptively — "iterations are identical by construction, so adaptive and fixed-depth scheduling coincide" — as an honest negative result inside a larger system paper. That is a legitimate option the two-paper plan did not allow. Doing the fix is still better, because it converts a null result into a real one for roughly 20 lines of work.

---

# PART A — Coding team

## A1. What actually exists today

### Q1. Which agents are fully implemented? Which are stubs or mocks?

**Six agents, all in `Backend/app/agents/`, all live and reachable, orchestrated by [`scheduler.py`](Backend/app/agents/scheduler.py).**

| Agent | File | Status | Note |
|---|---|---|---|
| Query Planner | `query_planner.py` | **IMPLEMENTED** | 1 LLM call; degrades gracefully on JSON failure |
| Retriever | `retriever.py` | **IMPLEMENTED** | FAISS ∥ Postgres `tsvector`, RRF-merged |
| Precedent Weighter | `precedent_weighter.py` | **PARTIAL** | Runs correctly; 2 of 5 signals starved of input — Q18, Q21 |
| Debate | `debate.py` | **IMPLEMENTED** | 7 LLM calls; per-call fallbacks; never drops a case |
| Evaluator | `evaluator.py` | **PARTIAL** | Correct formulas over a self-referential relevance proxy — Q26 |
| Scheduler | `scheduler.py` | **IMPLEMENTED** | Deterministic rule loop, ≤ 3 iterations |

**No agent is a stub or a mock.** All six do real work on the live path.

**On the seven-agent claim.** The synopsis counts seven because early scaffolding (commits `824666c`, `49e2ff7`) created a `Backend/agents/` directory containing placeholder Similarity and Mapping agents. That directory is imported by nothing and is not part of the system. **Delete it** (`git rm -r Backend/agents/`) — it serves only to confuse readers of the repository, and if a reviewer clones the code, a directory named `agents/` full of placeholder logic is the worst possible thing to leave lying around.

**For the paper:** state six agents. If Similarity and Mapping are wanted in the architecture, present them as designed-but-not-implemented future components, clearly marked.

### Q2. Can the system process a case start to finish without manual intervention?

**Yes.** `POST /api/v1/query` returns a `query_id` immediately and runs all six agents in a FastAPI `BackgroundTask`, persisting the trace after every stage ([`query.py:24-55`](Backend/app/api/v1/query.py#L24-L55)). Working smoke test: [`test_scores.py`](test_scores.py).

**Branch and commit: `main` @ `96210ee`.**

Preconditions: Postgres on 5433, FAISS index files present, Ollama serving the model, corpus already ingested. Ingestion itself is **not** unattended — six ordered CLI steps, and `explainer.md` warns that `ingest.ps1` omits the database-load step.

### Q3. Is the deployment live?

**ABSENT.** No deployment config, no CI, no URL. Render Pro is an intention (PRD §9). `docker-compose.yml` is local-only and has a case bug — it builds `./backend` while the directory is `Backend`, which fails on case-sensitive Linux.

**No external user has used the system.** Delete NFR-04 (99% uptime) and any availability claim from the paper.

---

## A2. Segmentation (Planner)

### Q4. How are facts and issues extracted?

**Two distinct mechanisms — do not conflate them in the paper.**

**(a) Corpus segmentation — regex only.** No model, no checkpoint, no LLM. [`segment_text.py:20-37`](Backend/scripts/ingest/segment_text.py#L20-L37):

```python
SECTION_PATTERNS = {
  "facts":     [r"(?i)\b(?:FACTS|FACTUAL\s+(?:MATRIX|BACKGROUND)|BACKGROUND|BRIEF\s+FACTS)\b",
                r"(?i)\bFACTS\s+(?:OF|IN)\s+(?:THE|THIS)\s+CASE\b"],
  "issues":    [r"(?i)\b(?:ISSUES?|QUESTIONS?\s+(?:OF|FOR)\s+(?:LAW|CONSIDERATION))\b",
                r"(?i)\bPOINTS?\s+FOR\s+(?:DETERMINATION|CONSIDERATION)\b"],
  "reasoning": [r"(?i)\b(?:REASONING|ANALYSIS|DISCUSSION|CONSIDERATION|HELD|JUDGMENT)\b",
                r"(?i)\bOUR\s+(?:VIEW|ANALYSIS|CONSIDERATION)\b"],
  "outcome":   [r"(?i)\b(?:ORDER|CONCLUSION|RESULT|DISPOSITION|OPERATIVE\s+(?:PART|ORDER))\b",
                r"(?i)\b(?:APPEAL\s+(?:IS|ALLOWED|DISMISSED))\b"],
}
```

Lines of 3–200 characters are scanned for these markers; text between consecutive markers is assigned to the preceding one. The file's own docstring claims a "Gemini-assisted" fallback — **that is false**; the fallback is positional (Q6).

**(b) Query decomposition — one LLM call.** Verbatim prompt for the appendix, from [`query_planner.py:20-40`](Backend/app/agents/query_planner.py#L20-L40):

```
You are an expert Indian Supreme Court legal researcher and query analyst.

Given the following legal query or case description, analyze it and produce a structured JSON response.

Legal Query:
{query}

You must respond with ONLY a JSON object containing:
{
  "legal_domain": "one of: constitutional, civil, criminal, tax, labour, commercial,
                   environmental, family, property, arbitration, administrative, general",
  "extracted_issues": ["list of specific legal issues/questions raised"],
  "extracted_facts": "summary of key factual elements",
  "target_outcome": "what outcome the querier seems to be looking for",
  "temporal_hint": "one of: recent, historical, any",
  "reformulated_queries": ["2-3 alternative search queries that capture different angles
                           of the same legal issue"],
  "confidence": 0.0 to 1.0
}

Be specific to Indian law. Identify relevant Acts, Articles, and Sections where possible.
Respond with ONLY the JSON, no other text.
```

`temperature=0.1`, `num_predict=1024`.

### Q5. Has segmentation accuracy been measured? — **MEASURABLE NOW (partly), no annotation needed**

**Not measured.** But a publishable number is already sitting in your data at zero annotation cost.

**Every segmented JSON carries a `segmentation_method` field** valued `"regex"` or `"heuristic_fallback"` ([`segment_text.py:125`](Backend/scripts/ingest/segment_text.py#L125)). The proportion that received real structural segmentation versus a blind positional cut is one pass over the directory:

```bash
cd data/processed/segmented
python - <<'PY'
import json, collections, pathlib
c = collections.Counter()
for f in pathlib.Path('.').glob('*.json'):
    c[json.loads(f.read_text(encoding='utf-8')).get('segmentation_method','missing')] += 1
tot = sum(c.values())
for k, v in c.most_common():
    print(f"{k:24s} {v:6d}  {100*v/tot:5.1f}%")
print(f"{'TOTAL':24s} {tot:6d}")
PY
```

**That single percentage belongs in the paper.** It is the honest ceiling on structural quality.

**For a true accuracy figure**, hand-check 50 documents. Sample stratified across both methods, and for each of the four sections score: correct / boundary-off / wrong-content / absent. Report per-section accuracy plus the fallback rate. Two people scoring the same 20 gives you an agreement figure at negligible extra cost. Budget: roughly a day.

**Correct the framing.** The question says segmentation quality caps the *structural channel*. There is no structural channel (Q13). What it actually caps is (i) the **embedding input**, since the four segments are concatenated before encoding, (ii) the **lexical index**, since `text_search_vector` is built from `title + facts_text + issues_text` **only** (Q59), and (iii) the **debate prompts**, which are filled from the segments directly. That is a stronger and more defensible claim than the original, because it touches all three retrieval surfaces.

### Q6. What happens when a document yields zero facts or zero issues?

**It never crashes and never skips. It silently substitutes a positional split.** Two fallbacks:

1. **Fewer than 2 markers found** → four equal quarters by character count, assigned in order to facts/issues/reasoning/outcome, tagged `heuristic_fallback` ([`segment_text.py:113-122`](Backend/scripts/ingest/segment_text.py#L113-L122)).
2. **2+ markers but facts and reasoning both empty** → three equal thirds ([`segment_text.py:77-81`](Backend/scripts/ingest/segment_text.py#L77-L81)).

No whole-document fallback, and no downstream flag — by retrieval time a quartered document is indistinguishable from a properly segmented one. A fallback document presents its arbitrary second quarter to the Debate agent as "the legal issues of the case".

Documents *are* dropped earlier, at extraction: PDFs under 100 characters (scanned), encrypted, or corrupt ([`extract_text.py`](Backend/scripts/ingest/extract_text.py)). See Q46.

**This belongs in the limitations section**, quantified with the Q5 percentage.

### Q7. Does the Planner emit multiple retrieval intents?

**PARTIAL — it generates them; the retriever throws most away.** The multi-intent claim is not currently supported.

[`retriever.py:199-204`](Backend/app/agents/retriever.py#L199-L204):
```python
search_queries  = [original_query] + reformulated[:1]   # only the FIRST reformulation
combined_query  = " ".join(search_queries)              # concatenated into ONE string
bm25_query      = original_query                        # lexical ignores reformulations entirely
```

One semantic search over a concatenation; one lexical search over the original. Reformulations 2 and 3 are computed, traced, and discarded.

**Two ways forward.** Either rewrite the claim, or implement it — and implementing it is genuinely small: loop the FAISS call over each reformulation and feed each ranked list into the existing `merge_rankings`, which already accepts arbitrary lists. That makes the claim true, gives you an ablation condition, **and supplies the per-iteration variation that Q58 shows the scheduler needs anyway.** Same 20 lines solve both problems.

---

## A3. Embeddings and retrieval

### Q8. Exact checkpoint and dimension

**`all-MiniLM-L6-v2`**, `sentence-transformers>=3.3.1`, **384 dimensions** ([`config.py:78`](Backend/app/core/config.py#L78), [`embedding_service.py`](Backend/app/services/embedding_service.py)).

Not InLegalBERT, not mpnet, no legal-domain model, no fine-tuning. Corpus and query use the identical model, so the spaces are consistent. State the absence of domain adaptation as a limitation — a reviewer will ask why InLegalBERT was not used, and naming it first is far better than being asked.

`build_embeddings.py`'s docstring still says "Gemini text-embedding-004". It is wrong; the code calls the local model.

### Q9. How is the token limit handled?

**Hard truncation at 1000 characters. No chunking, no pooling, no windowing.**

[`embedding_service.py:27`](Backend/app/services/embedding_service.py#L27):
```python
embedding = await asyncio.to_thread(_LOCAL_MODEL.encode, text[:1000], convert_to_numpy=True)
```

For a corpus document ([`build_embeddings.py:44-55`](Backend/scripts/ingest/build_embeddings.py#L44-L55)): concatenate `facts + issues + reasoning[:2000] + outcome`, then truncate the whole thing to **1000 characters**.

**Consequence, stated plainly for the paper: each judgment is represented by roughly its first paragraph of facts.** Issues, reasoning, and outcome reach the vector only when the facts section is shorter than ~1000 characters. Supreme Court judgments run to tens of thousands of words. 1000 characters ≈ 250 word-pieces, which is about the model's 256-token limit, so the truncation is at the model's true capacity — the limitation is architectural, not a bug.

**Quantify it** (this makes the limitation concrete and costs nothing — see Q44):
```bash
python - <<'PY'
import json, pathlib, statistics as st
r = []
for f in pathlib.Path('data/processed/segmented').glob('*.json'):
    d = json.loads(f.read_text(encoding='utf-8'))
    full = " ".join([d.get(k,"") or "" for k in ("facts","issues","reasoning","outcome")])
    if full.strip(): r.append(min(1000, len(full)) / len(full))
print(f"n={len(r)}  mean fraction embedded={st.mean(r):.4%}  median={st.median(r):.4%}")
PY
```
Report that percentage. My expectation is low single digits, and that is exactly the kind of specific honest number that strengthens a limitations section.

**Fix (Tier 3):** chunk to ~250-token windows, encode each, mean- or max-pool. Likely your largest single retrieval-quality gain.

### Q10. FAISS index type and parameters

**`IndexFlatIP` — exact, exhaustive, brute-force inner product.** [`build_faiss_index.py:58`](Backend/scripts/ingest/build_faiss_index.py#L58).

There is **no `nlist`, no `nprobe`, no `efSearch`** — those belong to IVF and HNSW, neither of which is used. No training, no quantisation, no clustering. Search is O(N·d).

**You must call it exact brute force. Do not write "approximate nearest neighbour" or "sublinear" anywhere in the paper** — it is wrong and trivially checkable.

Frame it as a strength: exact search means retrieval quality is not confounded by index approximation error, so the ablations isolate the ranking pipeline cleanly. Flat search is entirely practical well past 10⁵ vectors at 384-d.

### Q11. Is K varied by the Scheduler?

**No. Every width is a fixed constant.**

```
FAISS top-K       50    config.max_query_k
tsvector top-K    50    config.bm25_top_k
after RRF         50    config.final_candidates
after authority   20    precedent_weighter.py:82  (hardcoded)
debated            3    debate.py:202             (hardcoded)
returned          10    options.top_k default
```

The PRD's `expand_k = True` on low confidence (§6.5) was **never implemented**. A refinement iteration re-runs the identical retriever call with the identical K — the root of the Q58 problem.

### Q12. Are vectors L2-normalised?

**Yes, both sides. Inner product is true cosine.** `faiss.normalize_L2(matrix)` before `index.add` ([`build_faiss_index.py:55`](Backend/scripts/ingest/build_faiss_index.py#L55)); `faiss.normalize_L2(query_vec)` before every search ([`faiss_index.py:107`](Backend/app/core/faiss_index.py#L107)). State without qualification.

---

## A4. Similarity computation

> **Read before writing the similarity section.** This is the largest divergence between the drafted material and the code, and it is the reason the two-paper split had to be abandoned (§0.4).

### Q13. Is the structural score a symmetric best-match alignment over span embeddings, per Eq. (2)–(4)?

**No. There is no structural score, no span alignment, no span embeddings.**

One similarity computation exists: cosine between a 384-d query vector and a 384-d document vector (the truncated lead-paragraph encoding of Q9). That is `faiss_score`. It is then converted to a **rank**, and the rank — not the score — enters RRF.

The complete scoring pipeline:

```
Stage 1 — Rank fusion (retriever.py:24-58)
  rrf(rank)      = 1 / (60 + rank)
  rrf_score(c)   = rrf(faiss_rank) + rrf(tsrank_rank)     # missing from a list ⇒ 0

Stage 2 — Authority re-rank (precedent_weighter.py:80)
  authority = 0.35·norm(citation_count)   ← identically 0 (Q18)
            + 0.20·bench_size_score       ← constant 0.3 ⇒ 0.06 (Q21)
            + 0.15·recency_score
            + 0.20·norm(rrf_score)        ← RRF re-enters, labelled "factual_alignment"
            + 0.10·domain_score

Stage 3 — Final score (scheduler.py:296-311)
  norm_rrf = 0.5 + 0.5·(rrf − rrf_min)/(rrf_max − rrf_min)   # min-max WITHIN the returned set
  final    = 0.5·norm_rrf + 0.3·authority + 0.2·norm_rrf     # = 0.7·norm_rrf + 0.3·authority
  if rank ≤ 3: final = max(final, 0.65 + (3 − rank)·0.05)    # hardcoded floor
```

**Three defects in Stage 3.** The third term was meant to be a structural channel; `norm_rrf` was passed where a structural score belonged, so "three-channel fusion" is **two-channel fusion with one channel double-counted**. `norm_rrf` is min-max normalised *within the returned set*, so it encodes relative position among the top-k, not absolute relevance — rank 1 always gets 1.0 and the last always 0.5. And the rank-1–3 floor makes the top three scores partly independent of the computation.

There is an unused three-argument function [`ranking_service.py:compute_final_score(semantic, authority, structural)`](Backend/app/services/ranking_service.py) — **dead code, nothing calls it.** If the drafted equations were written from that signature, that is the source of the discrepancy.

**Recommendation.** Write the similarity section as: RRF fusion over a dense and a lexical channel, followed by an authority re-rank. That is real, describable, and defensible. Do not present Eq. (2)–(4). Building a genuine structural channel is substantial work (segment-level embeddings, alignment, pooling) — Tier 3, realistically future work.

### Q14. Values of α, β, γ. Fitted or hand-set?

**ABSENT — these parameters do not exist.** The analogues, all **hand-set, never fitted**:

| Location | Constants |
|---|---|
| Final score | 0.5 / 0.3 / 0.2 (the 0.2 double-counts semantic) |
| Authority | 0.35 citation, 0.20 bench, 0.15 recency, 0.20 factual, 0.10 domain |
| RRF | k = 60 (Cormack et al. default) |

**Delete the grid-search claim.** No search has been run and none could be — a search needs a labelled set (Q47). Say "set a priori in consultation with the industry partner" if true, otherwise "set heuristically". Do not imply optimisation.

**How to get fitted values later:** see Q61.

### Q15. Value of ω (fact vs issue balance)

**ABSENT.** Facts and issues are not scored separately — they are concatenated before encoding, and because of the 1000-character truncation the issues section usually does not survive into the vector at all. There is no ω, and no sweep is possible without segment-level scoring (Tier 3).

### Q16. Is isotonic calibration implemented?

**ABSENT.** No calibration of any kind; `scikit-learn` is not in [`requirements.txt`](Backend/requirements.txt). **Delete the subsection.**

Worth one limitations sentence: the scores are not merely uncalibrated but *anti*-calibrated — within-set min-max normalisation plus a rank-1–3 floor means displayed confidence tracks list position more than relevance.

### Q17. Are channel scores stored per candidate?

**Yes — and this is the best-supported claim in the project.**

Per candidate ([`precedent_weighter.py:71`](Backend/app/agents/precedent_weighter.py#L71)): `faiss_score`, `bm25_score`, `rrf_score`, `cite_count`, `raw_bench`, `raw_recency`, `domain_score`, `factual_alignment`, `authority_score`.

Returned by the API ([`scheduler.py:345-369`](Backend/app/agents/scheduler.py#L345-L369)): `relevance_score`, `authority_score`, `final_score`, `matched_issues`, `ratio_decidendi`, `relief`, `relevance_argument`, `weakness`, `precedent_issues`.

Plus the full per-stage `agent_trace` — latency, I/O sizes, stage details for all six agents — persisted to Postgres after **every** stage and served live. Lean on this. Caveat: these are semantic/lexical/authority sub-signals, not the three channels the drafted material names.

---

## A5. Precedential weight

### Q18. Is the citation graph built? Nodes and edges? — **NEEDS BUILD**

**ABSENT. Zero nodes, zero edges.**

The `citations` table exists in the migration and the ORM with full relationships. **[`populate_db.py`](Backend/scripts/ingest/populate_db.py) never inserts a single row.**

**The consequence is exact, not approximate:**
```python
mx_c = max(s["cite_count"] for s in scored) or 1.0   # max(0,0,…)=0 → falls through to 1.0
nc   = _norm(0.0, 0.0, 1.0)                          # = 0.0 for every case
```
**The highest-weighted authority signal, at 0.35, contributes identically zero to every score in the system.**

**How to build it — the two-step procedure.** The order matters and is not obvious:

**Step 1 — load the Parquet metadata (the root unblock of §0.1).** Citation extraction is useless without something to match against: `case_id` values are filenames like `2024_1_1_10_EN`, not citations. You must first populate `cases.citation`, `.title`, `.bench`, `.decision_date`, `.disposal_nature`, `.acts_sections` from the Parquet files already downloaded to `data/raw/metadata/parquet/year=*/`:

```python
# Backend/scripts/ingest/load_metadata.py  (new — ~60 lines)
import pandas as pd, pathlib
from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://verdicto:verdicto_secret@localhost:5433/verdicto")
frames = [pd.read_parquet(p) for p in pathlib.Path("data/raw/metadata").rglob("*.parquet")]
df = pd.concat(frames, ignore_index=True)
print(df.columns.tolist())   # ← RUN THIS FIRST and map the real column names below

with engine.begin() as conn:
    for row in df.itertuples():
        conn.execute(text("""
            UPDATE cases SET citation=:cit, bench=:bench, decision_date=:dt,
                             disposal_nature=:disp, title=COALESCE(NULLIF(:title,''), title)
            WHERE case_id = :cid
        """), {...})   # map from the printed column names
```
**Print the columns before writing the mapping** — the schema is whatever the bucket publishes, and guessing it is how this script fails silently.

**Step 2 — extract citations and build the edge list:**
```python
# Backend/scripts/ingest/extract_citations.py  (new — ~80 lines)
import re
CITATION_PATTERNS = [
    r"AIR\s+(\d{4})\s+SC\s+(\d+)",              # AIR 1973 SC 1461
    r"\((\d{4})\)\s*(\d+)\s*SCC\s*(\d+)",       # (1973) 4 SCC 225
    r"(\d{4})\s*\((\d+)\)\s*SCC\s*(\d+)",       # 2017 (10) SCC 1
    r"(\d{4})\s+INSC\s+(\d+)",                  # 2023 INSC 456
    r"\((\d{4})\)\s*(\d+)\s*SCR\s*(\d+)",       # SCR reporter
]
CASE_NAME = r"([A-Z][\w.&' -]{2,60})\s+(?:v\.?|vs\.?|versus)\s+([A-Z][\w.&' -]{2,60})"
```
For each case's full text: find all matches, normalise each to a canonical string, look it up against `cases.citation` (populated in Step 1), and insert `(citing_case_id, cited_case_id)` for every in-corpus hit. Use case-name matching as a fallback, matched against `petitioner`/`respondent`.

**Then report:** node count = `SELECT count(*) FROM cases`; edge count = `SELECT count(*) FROM citations`; plus mean out-degree, mean in-degree, and the proportion of extracted citations that resolved to an in-corpus case. **That last number is your extraction recall proxy and it belongs in the paper** (Q19).

### Q19. How are citations extracted? Recall estimate?

**ABSENT — no extractor exists** in any form (no regex, no spaCy, no LLM). `spacy` is not in requirements. No recall estimate exists because there is nothing to estimate.

**How to estimate recall once built:** hand-annotate every citation in 20 judgments (roughly 2 hours), run the extractor over the same 20, and report precision and recall against that. Report *two* recall figures and keep them distinct: (i) recall of citation *strings* in the text, and (ii) the proportion that *resolve to an in-corpus case*. The second will be much lower on a narrow corpus and is the one that actually limits your ground truth (Q51).

**This is the highest-leverage task in the project.** One extractor unlocks the citation graph (Q18), the 0.35 authority signal (Q20), and cited-precedents-as-labels ground truth (Q47) — three blockers, one piece of work.

### Q20. Is PageRank run via NetworkX?

**ABSENT.** `networkx` is not in requirements. No graph algorithm of any kind.

Precedential weight is a five-term weighted sum in which the citation term is 0 and the bench term is constant. **What varies per case is only recency (0.15), RRF-derived factual alignment (0.20), and domain match (0.10) — 0.45 of the nominal 1.0 is live; 0.55 is constant.** Because the constants are identical across cases, they shift all scores by a fixed offset and **have no effect on ranking whatsoever.**

State precisely: *precedential re-ranking currently reorders candidates using recency, RRF score, and domain match only.*

**How to add PageRank** once Q18 is done: `pip install networkx`, build a `DiGraph` from the `citations` table, run `nx.pagerank(G, alpha=0.85)`, store per case, substitute the normalised PageRank for `norm(citation_count)`. Then **report both** — raw citation count and PageRank as separate conditions. That is a clean, self-contained ablation and a real contribution.

### Q21. Exact court tier weights t(·)

**ABSENT and structurally inapplicable — the corpus is Supreme Court only** (PRD §3 excludes High Court and District Court). One tier. **Delete every court-hierarchy claim from the paper.**

The nearest analogue is bench-size scoring ([`precedent_weighter.py:18-27`](Backend/app/agents/precedent_weighter.py#L18-L27)):
```
bench ≥ 5 judges → 1.0     (Constitution Bench)
bench ≥ 3 judges → 0.6
otherwise        → 0.3
```
parsed by regex from the `bench` text field. **But `bench` is NULL for every case**, so `_extract_bench_size` returns its default of 2, every case scores 0.3, and the term is a constant 0.06. The Constitution-Bench distinction — legally the most meaningful authority signal available in an SC-only corpus — is implemented and then starved of input.

**Fixed by Step 1 of Q18.** After loading metadata, report the bench-size distribution:
```sql
SELECT CASE WHEN bench ~ '(\d+)' THEN substring(bench from '(\d+)') ELSE 'unparsed' END AS n_judges,
       count(*) FROM cases GROUP BY 1 ORDER BY 2 DESC;
```
That distribution is itself a corpus-description table, and it converts the "− precedential" ablation from meaningless into meaningful (Q57).

### Q22. Is the overruled/doubted flag o(d) implemented?

**ABSENT.** No overruling detection, no column, no data source.

One honest exception: the opposing-counsel prompt asks *"Was this case overruled?"* and the schema carries `overruled_by` ([`debate.py:53-70`](Backend/app/agents/debate.py#L53-L70)). So the system surfaces an **8B model's unverified assertion** about overruling, for the top 3 cases, in free text, with no ground truth. `overruled_by` is **never read by any scoring code** — it is display-only.

**Follow the instruction: set ψ = 0 and state the limitation.** The citable reason is solid: India has no comprehensive machine-readable subsequent-treatment database comparable to Shepard's or KeyCite. Add to the limitations that an unverified LLM assertion of overruling is a hallucination risk that would matter in real practice — naming it is much better than having a reviewer find it.

---

## A6. The Scheduler

### Q23. Rule set, or does the LLM decide?

**A deterministic rule set. The LLM has no role in control flow.** The priority-ordered rule-set framing (the question's Table 1) is correct.

Complete policy ([`scheduler.py:86`](Backend/app/agents/scheduler.py#L86), [`:247-259`](Backend/app/agents/scheduler.py#L247-L259), predicate at [`evaluator.py:77`](Backend/app/agents/evaluator.py#L77)):
```python
while iteration < max_iter:                 # max_iter = 3
    iteration += 1
    retriever → precedent_weighter
    if enable_debate and ranked_cases and iteration == 1:
        debate                              # first iteration only, ever
    evaluator
    needs_refinement = (confidence < 0.55) or (disagreement_rate > 0.3)
    if not needs_refinement: break
```

Plain `if`/`while`, fully deterministic. No LLM call decides anything, and there is exactly one action available ("run the loop body again").

**Two properties that must be disclosed, because together they gut the adaptivity claim:**

1. **Refinement is identical to the first pass** — same plan, same K, same filters (Q11). The retriever is deterministic, so **iterations 2 and 3 recompute exactly the same candidates and therefore exactly the same confidence.** The loop cannot converge by improving; it can only run to the cap.
2. **Only the last iteration survives.** `best_result` / `best_eval` / `best_debate` ([`scheduler.py:242-244`](Backend/app/agents/scheduler.py#L242-L244)) are unconditionally overwritten each pass — no comparison, no argmax. "Best" means "latest".

The current scheduler is behaviourally an early-exit loop. **That is close to being your own B3 baseline** — see Q58.

### Q24. Values of τ_c, τ_S, τ_σ, k_max, and where configured

| Symbol | Code name | Value | Location |
|---|---|---|---|
| τ_c | `confidence_threshold` | **0.55** | [`config.py:65`](Backend/app/core/config.py#L65) |
| τ_σ | hardcoded | **0.3** | [`evaluator.py:77`](Backend/app/agents/evaluator.py#L77) |
| k_max | `scheduler_max_iterations`, clamped `min(…, 3)` | **3** | [`config.py:64`](Backend/app/core/config.py#L64), [`scheduler.py:50`](Backend/app/agents/scheduler.py#L50) |
| — | `debate_max_rounds` | **3 — declared, never read by any code** | [`config.py:63`](Backend/app/core/config.py#L63) |
| — | relevance threshold | **0.4** | [`evaluator.py:46`](Backend/app/agents/evaluator.py#L46) |
| — | RRF k | **60** | [`retriever.py:26`](Backend/app/agents/retriever.py#L26) |

**τ_S has no counterpart** — no stability or score threshold exists. Remove it or define it. The PRD says τ_c = 0.75; **the code uses 0.55 — cite the code.**

### Q25. How is the disagreement flag d computed?

**Not from channel comparison, rank correlation, or score spread. It is a count of items in a list the LLM emitted.**

[`evaluator.py:75-77`](Backend/app/agents/evaluator.py#L75-L77):
```python
disagreements     = debate_result.get("disagreement_flags", [])
disagreement_rate = len(disagreements) / max(len(ranked_cases[:5]), 1)
```
`disagreement_flags` is the `disputes` array from the synthesis call — whatever the model chose to put there.

**Four consequences to disclose:**
- Denominator is `len(ranked_cases[:5])` = 5, but debate only examines **3** cases — a mismatched population.
- On iterations 2–3 debate does not run, so `debate_result = {}` and **d = 0 always. The disagreement branch is unreachable after the first iteration.**
- If synthesis fails or times out, the fallback sets `disputes: []` → d = 0. **Failure is indistinguishable from consensus.**
- No quartile analysis, no rank correlation, no inter-channel comparison exists anywhere.

Describe it as *LLM-reported dispute count normalised by candidate-set size*, unvalidated.

### Q26. Is Evaluator confidence self-reported by the LLM, or computed?

**Computed from formulas — not self-reported.** But the formulas consume the system's own scores, so the number is arithmetically sound and epistemically circular. **Both halves of that sentence belong in the paper.**

[`evaluator.py`](Backend/app/agents/evaluator.py), complete:
```python
scores    = [c["final_score"] for c in ranked_cases]     # ← the system's OWN output
threshold = 0.4
p_at_5    = |{s ∈ scores[:5]  : s ≥ 0.4}| / min(5,  len(scores))
ndcg_10   = DCG(scores, 10) / DCG(sorted(scores, desc), 10)
mrr       = 1 / (1 + index of first s ≥ 0.4)
coverage  = |{issue : issue.lower()[:20] ∈ concat(top-10 issues+facts)}| / |issues|
confidence = 0.3·p_at_5 + 0.3·ndcg_10 + 0.2·mrr + 0.2·coverage
```

**Why every term is degenerate:**
- **nDCG@10 ≈ 1.0 by construction** — the "ideal" ranking is the actual scores re-sorted, and the list is already sorted by a monotone function of the same inputs. **It measures whether the list is sorted, not whether it is relevant.**
- **P@5 and MRR are near-1 by construction** — they count scores above 0.4, and the rank-1–3 floor *guarantees* the top three exceed 0.65. MRR is almost always exactly 1.0.
- **Coverage is a crude substring test** — first 20 characters, lowercased. A paraphrase scores 0; a shared prefix scores 1.

**Do not put these in a results table.** You *may* describe the mechanism in methods as a self-consistency heuristic that gates re-querying — that is a fair description of what it is.

**The good news relative to the question's worry:** this is *not* weakly-calibrated self-reported LLM confidence, so you dodge that specific objection. (The Planner does self-report a `confidence`, but it is trace-only and never gates anything.) The flaw is circularity, which is more explicable.

### Q27. Mean and maximum iterations per query — **MEASURABLE NOW**

**Never measured — but the data may already be in your database.** `agent_trace["scheduler"]["details"]["iterations"]` is written for every query alongside `final_confidence` and `total_pipeline_ms`.

Because `agent_trace` is a JSON string in a TEXT column, use Postgres JSON casting:
```sql
SELECT (agent_trace::json -> 'scheduler' -> 'details' ->> 'iterations')::int AS iters,
       count(*) AS n,
       round(avg((agent_trace::json->'scheduler'->'details'->>'final_confidence')::numeric), 4) AS mean_conf
FROM query_records
WHERE status = 'complete' AND agent_trace IS NOT NULL
GROUP BY 1 ORDER BY 1;
```
That gives the full distribution, the mean, and the max in one query.

**Prediction to check against:** because refinement iterations are identical (Q23), confidence should not change between passes, so queries should stop at 1 or run to 3 with **nothing at 2**. A bimodal distribution with an empty middle confirms the loop is not adapting — **and that finding, honestly reported, is itself a legitimate contribution** about the limits of naive iteration.

### Q28. Has the loop failed to terminate? What fraction hit k_max? — **MEASURABLE NOW**

**Termination is structurally guaranteed** — `while iteration < max_iter`, `max_iter = min(setting, 3)`, no decrement path. Debate has per-call 120 s timeouts and the client a 3-failure circuit breaker, so no stage hangs indefinitely.

**Cap fraction:** the Q27 query answers it — `n` at `iters = 3` divided by the total.

---

## A7. Debate

### Q29. Maximum rounds R and confidence step η

**R = 2 recorded rounds, structurally fixed. η is ABSENT.**

| Round | Type | Calls |
|---|---|---|
| 1 | `advocate_opposing`, sequential per case | 3 × 2 = **6** |
| 2 | `synthesis` | **1** |
| | | **7** |

`debate_max_rounds = 3` in config is **read by nothing**. Prompts at [`debate.py:34-81`](Backend/app/agents/debate.py#L34-L81) are appendix-ready as written. `temperature=0.3` for advocate/opposing, `0.1` for synthesis; 120 s per call; every failure caught individually with a safe default so no case is dropped.

**No η, no confidence step, no iterative update.** Advocate and opposing each emit a `confidence` float that is stored, displayed, and never used.

### Q30. Is δ (claim survival) computed?

**ABSENT.** No δ, no survival measure, no claim/counterclaim overlap. Post-debate confidence is neither computed nor re-asked; the two self-reported confidences sit side by side and are never combined.

**What debate actually changes is rank order only.** Synthesis returns `final_ranking`; the Scheduler reorders `ranked_cases`, appending un-mentioned cases at the end so nothing is lost ([`scheduler.py:192-200`](Backend/app/agents/scheduler.py#L192-L200)). **Scores are never modified by debate** — a debated case keeps its `authority_score`, and its `final_score` is recomputed from its *new* rank, which means the rank-1–3 floor is applied post-debate. Debate is a 3-item re-ranker, not a confidence-revision mechanism.

**If you want δ**, it is definable from data you already store: token or embedding overlap between `advocate.relevance_argument` and `opposing.counterargument`, both persisted in `debate_rounds`. Computable retrospectively over existing traces without re-running anything.

### Q31. In how many runs did debate change the top precedent? — **MEASURABLE NOW, and the most persuasive paragraph available to the paper**

**Never measured, fully recoverable.** `agent_trace["debate"]["details"]` holds `final_ranking`, the complete `debate_rounds` with every argument and counterargument, `consensus_rationale`, and `disagreement_flags`. `agent_trace["precedent_weighting"]` records the pre-debate stage.

```python
# Backend/scripts/eval/debate_impact.py
import json, asyncio
from sqlalchemy import text
from app.core.database import async_session_factory

async def main():
    changed, total, examples = 0, 0, []
    async with async_session_factory() as db:
        rows = (await db.execute(text(
            "SELECT id, query_text, agent_trace, result FROM query_records "
            "WHERE status='complete' AND agent_trace IS NOT NULL"))).fetchall()
    for qid, qtext, trace_s, result_s in rows:
        tr = json.loads(trace_s)
        det = tr.get("debate", {}).get("details", {})
        ranking = det.get("final_ranking") or []
        rounds  = det.get("debate_rounds") or []
        if not ranking or not rounds: continue
        debated = [e["case_id"] for e in rounds[0].get("entries", [])]  # pre-debate order
        if not debated: continue
        total += 1
        if ranking[0] != debated[0]:
            changed += 1
            entries = {e["case_id"]: e for e in rounds[0]["entries"]}
            examples.append({
                "query": qtext, "was": debated[0], "now": ranking[0],
                "promoted_advocate": entries.get(ranking[0], {}).get("advocate", {}).get("relevance_argument", ""),
                "demoted_opposing":  entries.get(debated[0], {}).get("opposing", {}).get("counterargument", ""),
                "rationale": det.get("consensus_rationale", ""),
            })
    print(f"debate changed the top precedent in {changed}/{total} queries "
          f"({100*changed/max(total,1):.1f}%)")
    print(json.dumps(examples[:3], indent=2, ensure_ascii=False))

asyncio.run(main())
```

**Two caveats to state with the number.** Debate runs only on iteration 1, and it sees only the top 3 — so it can never promote a case ranked 4th or lower. **Quote the frequency against the 3! = 6 reachable permutations, not against the full result list.**

This is also where the weak model shows up most directly. If the frequency is near zero, that is a real and reportable finding about 8B-scale adversarial debate — see §0.2(a).

---

## A8. Engineering claims

### Q32. Are agents stateless and re-runnable? Is there a replay facility?

**Stateless: yes, genuinely.** Every agent extends `BaseAgent` ([`base_agent.py`](Backend/app/agents/base_agent.py)) with the contract `async def run(input_data: dict) -> dict`, documented as "must be idempotent for the same input". No cross-query state; all state flows through the returned dict. `execute()` wraps `run()` with timing, structured logging, and error handling. Well supported.

Qualifications: Retriever and Precedent Weighter hold an `AsyncSession` (a resource, not state), and the LLM client singleton carries a circuit-breaker counter that the Scheduler explicitly resets at pipeline start.

**Replay: ABSENT — mark aspirational.** Note the *inputs* to each stage are largely reconstructible from the persisted trace, so replay is a plausible addition rather than a fiction. **But "we log enough to replay" ≠ "we have replay". Claim only the former.**

### Q33. Is JSON schema validation enforced? What happens on violation?

**PARTIAL — Pydantic at the API boundary, bypassed for agent messages and LLM output.**

- **API boundary: enforced.** `QueryRequest`/`QueryResponse` in `app/models/query.py`; violations return 422.
- **Agent-to-agent: not enforced.** Plain `dict[str, Any]`. Schemas exist in `app/models/agent.py` and are unused.
- **LLM output: hand-rolled recovery.** `generate_structured()` exists on the client and validates against a Pydantic model — **no agent calls it.** Every agent calls `generate_text()` and parses manually.

The recovery ladder ([`debate.py:86-107`](Backend/app/agents/debate.py#L86-L107)): strip `<think>…</think>` → strip markdown fences → `json.loads` → regex the first `{.*}` → **safe default, warn, continue.** Nothing retries; nothing fails the pipeline. The Planner degrades to `{legal_domain:"general", extracted_issues:[query], confidence:0.3}`; Debate degrades to empty arguments at confidence 0.5 while keeping the case.

Describe this as graceful degradation — accurate and defensible. **Do not describe it as schema-validated structured output.** Note that degradation is silent: a query whose planner failed looks identical to one that succeeded except for `confidence: 0.3` in the trace.

**How to measure the parse-failure rate — do this, it directly addresses the weak-model concern (§0.2):**

The failures are already logged as structured events: `debate.advocate_failed`, `debate.opposing_failed`, `debate.synthesis_failed`, `query_planner.json_parse_failed`. Capture stdout to a file and count:
```bash
uvicorn app.main:app --port 8000 2>&1 | tee run.log
grep -c "advocate_failed"   run.log
grep -c "opposing_failed"   run.log
grep -c "synthesis_failed"  run.log
grep -c "json_parse_failed" run.log
```
Or, better and query-attributable, detect it from the database — a planner failure is uniquely identifiable by its sentinel confidence:
```sql
SELECT count(*) FILTER (WHERE (agent_trace::json->'query_planner'->'details'->>'confidence')::float = 0.3)
       AS planner_parse_failures,
       count(*) AS total
FROM query_records WHERE status='complete';
```
**"X% of LLM calls required regex recovery; Y% fell back to defaults" is a real, defensible number that characterises the model honestly** — and it is the strongest justification you can give for switching models (§0.2(b)) or for a modest debate effect.

### Q34. Model variant, temperature, structured output

**Not Gemini.** `deepseek-r1:8b` via **Ollama** at `http://host.docker.internal:11434`, endpoint `/api/generate` ([`config.py:73-74`](Backend/app/core/config.py#L73-L74)).

| Call | Temperature |
|---|---|
| Query Planner | 0.1 |
| Debate — advocate | 0.3 |
| Debate — opposing | 0.3 |
| Debate — synthesis | 0.1 |

`num_predict = 1024` on every call. **Structured output: supported but unused** — `format: "json"` is set only when `response_schema` is passed, and no agent passes it, so every call is free-form text with regex recovery.

`google-generativeai` is **removed** from requirements ("using Ollama"). `gemini_api_key` defaults to the literal `"not_used_ollama_is_active"`. The `GeminiClient` class name and `gemini_*` config fields are vestigial.

**Replace every Gemini mention in the paper**, then reframe: fully local inference, zero API cost, no data egress, runs air-gapped. For judicial deployment that is a substantive argument.

### Q35. Is PostgreSQL actually wired up?

**Yes, fully. Postgres 15 throughout** — SQLAlchemy 2.0 async + `asyncpg`, Alembic migration `001_initial`, `postgres:15-alpine` on host port 5433. Load-bearing, not decorative: the lexical channel *is* a Postgres query, and the live trace is persisted there.

One detail with real consequences, from the migration:
```sql
ALTER TABLE cases ADD COLUMN text_search_vector tsvector GENERATED ALWAYS AS (
  to_tsvector('english', coalesce(title,'') || ' ' || coalesce(facts_text,'') || ' ' || coalesce(issues_text,''))
) STORED;
CREATE INDEX idx_cases_fts ON cases USING GIN(text_search_vector);
```
**The lexical index covers `title + facts + issues` only — `reasoning_text` and `outcome_text` are not searchable.** So the lexical channel sees roughly half the document, and citations appearing in the reasoning section are invisible to it. Two implications: it caps lexical recall (report it as a limitation), and it *reduces* — but does not eliminate — the Q48 leakage surface.

Caveats: `citations` is created but never populated (Q18); `celery`/`redis` are configured ([`worker.py`](Backend/app/worker.py), a `worker` service in compose) but **the pipeline does not use them** — it runs in `BackgroundTasks`, and Redis is only health-checked. **Do not claim a distributed task queue.**

### Q36. Latency — median, P95, per-agent, hardware — **MEASURABLE NOW**

**Never measured.** But `latency_ms` is already recorded for all six agents in the trace, plus `processing_time_ms` for the pipeline.

```sql
WITH t AS (
  SELECT processing_time_ms AS total,
         (agent_trace::json->'query_planner'      ->>'latency_ms')::int AS planner,
         (agent_trace::json->'retriever'          ->>'latency_ms')::int AS retriever,
         (agent_trace::json->'precedent_weighting'->>'latency_ms')::int AS weighter,
         (agent_trace::json->'debate'             ->>'latency_ms')::int AS debate,
         (agent_trace::json->'evaluator'          ->>'latency_ms')::int AS evaluator
  FROM query_records WHERE status='complete' AND agent_trace IS NOT NULL)
SELECT count(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY total)     AS median_total_ms,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY total)    AS p95_total_ms,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY planner)   AS median_planner,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY retriever) AS median_retriever,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY weighter)  AS median_weighter,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY debate)    AS median_debate,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY evaluator) AS median_evaluator
FROM t;
```
**That one query produces your entire latency table.** Run ≥ 30 queries first so the percentiles mean something.

Expect debate to dominate: 7 sequential LLM calls at 120 s timeout each; the module's docstring estimates 15–30 s per call, ~2 min typical, ~6 min worst case. Retriever, weighter, and evaluator should be milliseconds to low seconds.

**The PRD's P95 < 8 s is unreachable and NFR-02's ≤ 60 s is likely violated. Revise the NFR rather than reporting against a target you miss.** A 2–5 minute deep-analysis pipeline is entirely defensible when the alternative is hours of manual research — frame it as a considered latency/quality trade-off and report the real distribution.

**Hardware (Q67):** record CPU model and cores, RAM, **GPU model and VRAM** (decisive — GPU vs CPU inference for an 8B model is roughly a 10× difference), OS, Ollama version, and whether Ollama/Postgres/API shared one machine.

### Q37. API calls and token cost per query

**API calls: zero. Monetary cost: zero.** All inference local. State this — it is a genuine result.

**LLM invocations per query**, deterministic from the code:

| Path | Calls |
|---|---|
| Planner | 1 |
| Debate (iteration 1 only) | 7 |
| Iterations 2–3 | 0 additional — neither retrieval nor weighting calls the LLM |
| **Total** | **8** with debate, **1** without |

Well inside the PRD's ≤ 12 budget.

**Token counts — MEASURABLE with a small change.** `_UsageStats` already accumulates `prompt_eval_count` and `eval_count` from every Ollama response ([`gemini_client.py:48-66`](Backend/app/core/gemini_client.py#L48-L66)), exposed via `get_usage_stats()` — **currently never surfaced.** In `scheduler.py`, before the final return:

```python
from app.core.gemini_client import get_gemini_client
trace["scheduler"]["details"]["token_usage"] = get_gemini_client().get_usage_stats()
```
Then read it back from the trace with the same JSON pattern as above. (Note the client is a process-wide singleton, so counts accumulate across queries — either reset at pipeline start alongside `reset_circuit()`, or record deltas.)

**Say this in the paper:** deepseek-r1 generates `<think>` reasoning traces that are counted, paid for in latency, and then **stripped and discarded**. Token counts will look high relative to visible output. This is also a concrete argument for §0.2(b).

### Q38. Random seeds, code release, licence

**Seeds: not fixed.** No `torch.manual_seed`, no `numpy.random.seed`, no Ollama seed.

| Component | Deterministic? |
|---|---|
| FAISS flat search | Yes |
| SentenceTransformer inference | Yes |
| Postgres `ts_rank` | Yes |
| RRF and authority arithmetic | Yes |
| **LLM calls (temp 0.1–0.3)** | **No** |

**Fix — one line**, in the payload at [`gemini_client.py:139-143`](Backend/app/core/gemini_client.py#L139-L143):
```python
"options": {"temperature": temperature, "num_predict": 1024, "seed": 42},
```
Do this **before** the measurement runs. Combined with §0.2's LLM-free retrieval path, that makes the retrieval results fully deterministic and the agent-level results reproducible.

**Licence: ABSENT.** No `LICENSE` file. **Decide before submission** — an unlicensed public repository is legally "all rights reserved", which undercuts any reproducibility claim. MIT or Apache-2.0 are conventional.

### Q39. Does the frontend stream live agent status?

**Polling. Not WebSocket, not SSE.**
- [`ProgressDashboard.jsx:76`](Frontend/webapp/src/pages/ProgressDashboard.jsx#L76) — `setInterval` at **1500 ms** → `GET /api/v1/query/{id}/status`, merges the trace into state
- [`DebateVisualization.jsx:142`](Frontend/webapp/src/pages/DebateVisualization.jsx#L142) — `setInterval` at **2000 ms**, extracts the debate sub-trace

**The underlying claim is nevertheless true.** The backend genuinely writes the trace after every stage via `trace_callback`, including explicit `"status": "in_progress"` markers before the debate and evaluator stages, so the UI shows which agent is running now. It is real-time in substance.

**Write "polls the status endpoint at 1.5-second intervals", not "streams via WebSocket".** All eight pages route through a single `apiClient.js`, which supports the clean-architecture claim.

---

# PART B — Data analysis team

> Every item here is answered, and every missing number has a procedure. The `data/` directory is gitignored, so counts must come from your machine — but the *methods* below are exact.

## B1. The corpus

### Q40. Exact source

**AWS Open Data Registry — the `indian-supreme-court-judgments` public S3 bucket.** Not IndianKanoon, not eCourts, not Kaggle, not e-SCR.

Verbatim, from [`download_dataset.py:22-23`](Backend/scripts/ingest/download_dataset.py#L22-L23):
```python
S3_BUCKET = "indian-supreme-court-judgments"
S3_CONFIG = Config(signature_version=UNSIGNED)   # no AWS credentials required
```
```
s3://indian-supreme-court-judgments/
├── data/pdf/year={YEAR}/
├── data/tar/year={YEAR}/english/       # english.tar + english.index.json
└── metadata/{json,parquet}/year={YEAR}/
```
Unsigned access is excellent for the reproducibility statement. **Replace "DataSet — AWS Ai" with the bucket URI.**

### Q41. Licence and terms of use — **verify directly, do not assume**

Not in the repository. **Procedure:** open the AWS Open Data Registry entry for `indian-supreme-court-judgments` and quote its licence field verbatim. Confirm two things: redistribution/derivative terms, and that others can obtain it by the same unsigned access. PRD §14 asserts public availability, which is a reasonable prior for Indian court judgments, but **assert nothing you have not read on the registry page.**

### Q42. N judgments, date range, courts — **MEASURABLE NOW**

**Authoritative source is your running instance:**
```bash
curl -s http://localhost:8000/api/v1/stats | python -m json.tool
# → total_cases, years_covered, total_queries, faiss_index_size, embedding_dimension
```
Cross-check directly:
```sql
SELECT count(*) AS n_cases, min(year), max(year), count(DISTINCT year) FROM cases;
SELECT year, count(*) FROM cases GROUP BY year ORDER BY year;
```
**`total_cases` and `faiss_index_size` must agree.** They are populated by independent scripts, so a mismatch is possible and is itself worth reporting (Q46).

**Date range:** whatever `--year-from`/`--year-to` you actually ran. The docs disagree — README 2020–2024, `explainer.md` 2024 only, PRD 2015–2024. **Report what was run.**

**Courts: Supreme Court of India only** (PRD §3). English only (`english.tar`); regional-language judgments are out of scope.

Note `year` is parsed from the filename prefix (`2024_1_1_10_EN` → 2024), not the judgment metadata — so it is the bucket's partition year, which may differ from the decision date. Worth a sentence, since recency scoring depends on it. Loading `decision_date` (Q18 Step 1) fixes it.

### Q43. Subject-matter distribution — **NEEDS BUILD**

**Not currently derivable** — `acts_sections` and `disposal_nature` are never populated, and no subject field exists. The `legal_domain` taxonomy exists only in the Planner prompt, for *queries*.

**Two routes, cheapest first:**
1. **Check the Parquet metadata for a subject field** — run the `print(df.columns.tolist())` line from Q18 Step 1. If a category column exists, this is free.
2. **Otherwise classify** — either keyword rules over `acts_sections` once loaded (Constitution → constitutional, IPC/CrPC → criminal, Income Tax Act → tax, and so on), or one LLM pass over the corpus using the same twelve-domain taxonomy as the Planner prompt.

**The question's warning stands: if one area dominates, the paper must say so**, and on a single-year slice that is a live risk.

### Q44. Mean and median document length — **MEASURABLE NOW**

```bash
python - <<'PY'
import pathlib, statistics as st
w = [len(p.read_text(encoding='utf-8', errors='ignore').split())
     for p in pathlib.Path('data/processed').glob('*.txt')]
print(f"n={len(w)}  mean={st.mean(w):.0f}  median={st.median(w):.0f}  "
      f"p10={st.quantiles(w, n=10)[0]:.0f}  p90={st.quantiles(w, n=10)[-1]:.0f}")
PY
```
For encoder tokens, use the actual tokeniser rather than a word-count proxy:
```python
from sentence_transformers import SentenceTransformer
m = SentenceTransformer("all-MiniLM-L6-v2")
tok = m.tokenizer(text, truncation=False)["input_ids"]; print(len(tok))
```
**Report word length, token length, and the fraction embedded** (the Q9 snippet) side by side. Together they make the truncation limitation concrete and quantified.

### Q45. Has near-duplicate detection been run? — **ABSENT, but cheap to run now**

**No deduplication of any kind exists.** The only control is exact `case_id` (filename) matching — `ON CONFLICT (case_id) DO NOTHING`. That catches re-ingesting the same file and **nothing else**: not the same judgment under two IDs, not connected appeals, not corrected re-issues, not cross-year duplicates.

**The concern is real and unmitigated.** Near-duplicates inflate every retrieval metric, and they are especially damaging under option-(a) ground truth, where a duplicate of the query case in the pool is an outright leak.

**Procedure — the index is already built, so this is one matrix operation:**
```python
# Backend/scripts/eval/dedup.py
import faiss, json, numpy as np
idx = faiss.read_index("data/index/cases.index")
mapping = {int(k): v for k, v in json.load(open("data/index/cases_mapping.json")).items()}
X = idx.reconstruct_n(0, idx.ntotal)          # already L2-normalised
D, I = idx.search(X, 6)                        # self + 5 neighbours
pairs = [(mapping[i], mapping[int(j)], float(s))
         for i, (row_d, row_i) in enumerate(zip(D, I))
         for s, j in zip(row_d, row_i) if int(j) != i and s >= 0.95]
seen, uniq = set(), []
for a, b, s in pairs:
    k = tuple(sorted((a, b)))
    if k not in seen: seen.add(k); uniq.append((a, b, s))
print(f"{len(uniq)} near-duplicate pairs at cos ≥ 0.95 out of {idx.ntotal} documents "
      f"({100*len(uniq)/idx.ntotal:.2f}%)")
for a, b, s in uniq[:20]: print(f"  {s:.4f}  {a}  ~  {b}")
```
**Caveat that must accompany the number:** because embeddings are 1000-char truncations (Q9), this detects *lead-paragraph* duplicates. It will over-flag judgments with boilerplate openings and under-flag documents that diverge only late. Sweep the threshold (0.90/0.95/0.98), inspect ~20 pairs by hand, and report both the rate and the threshold. For a stricter check, add character-level MinHash over the full text.

Then either drop duplicates or collapse them into equivalence classes for scoring, and say which you did.

### Q46. How many documents failed segmentation or metadata extraction? — **MEASURABLE NOW**

Three loss points:

| Stage | Failure mode | Recorded? |
|---|---|---|
| `extract_text.py` | pdfplumber → pypdf → skip if < 100 chars (scanned), encrypted, or corrupt | Console only |
| `segment_text.py` | Never fails — silently falls back to positional split | **`segmentation_method` field — recoverable** |
| `build_embeddings.py` | Skips combined text < 50 chars | Console; `.progress` lists successes |

**The full attrition chain — five commands, publication-quality table:**
```bash
ls data/raw/pdfs/*.pdf                | wc -l   # 1. downloaded
ls data/processed/*.txt               | wc -l   # 2. text extracted
ls data/processed/segmented/*.json    | wc -l   # 3. segmented
ls data/embeddings/*.npy              | wc -l   # 4. embedded
psql -p 5433 -U verdicto -d verdicto -c "SELECT count(*) FROM cases;"   # 5. in DB
curl -s localhost:8000/api/v1/stats | python -c "import sys,json; print(json.load(sys.stdin)['faiss_index_size'])"
```
Present as a corpus-construction table with the loss at each step. **Steps 4/5/6 must agree**; a mismatch means `populate_db` and `build_faiss_index` saw different file sets, which would silently break the `case_id` ↔ FAISS mapping and is worth checking before any experiment.

Add the `segmentation_method` split from Q5.

---

## B2. Ground truth — the single most important item

### Q47. How is "relevant" defined? — **ABSENT. This is the blocking item.**

**It is not defined. There is no ground truth in this project.** Not (a), not (b), not (c), not a mixture. No labelled set, no annotation, no benchmark import, no citation-derived labels. `scripts/eval/` and `golden_set.json` were specified in PRD §5 and §12 and never built — PRD §6.6 admits it: "a golden set … *to be built during development*."

What the system currently calls its metrics is Q26: formulas over its own `final_score`, where the "ideal" ranking is those same scores re-sorted. **No external referent. They cannot appear in a results table.**

**Recommended path: option (a), cited-precedents-as-labels.** It needs no annotators, scales to hundreds of queries immediately, is well precedented in legal IR, and — decisively — **shares its only dependency with Q18 and Q19.** One citation extractor gives you the graph, the authority signal, and the labels.

**Full procedure:**

```python
# Backend/scripts/eval/build_golden_set.py
# PREREQUISITES: Q18 Step 1 (metadata loaded) and Step 2 (citations table populated)
import json, re, asyncio
from sqlalchemy import text
from app.core.database import async_session_factory

CITE_RE = re.compile(
    r"(AIR\s+\d{4}\s+SC\s+\d+"
    r"|\(\d{4}\)\s*\d+\s*SC[CR]\s*\d+"
    r"|\d{4}\s*\(\d+\)\s*SCC\s*\d+"
    r"|\d{4}\s+INSC\s+\d+)", re.I)
CASE_NAME_RE = re.compile(
    r"[A-Z][\w.&' -]{2,60}\s+(?:v\.?|vs\.?|versus)\s+[A-Z][\w.&' -]{2,60}")

def strip_leakage(t: str) -> str:
    """Remove citation strings and case names so the query cannot contain its own answer."""
    return CASE_NAME_RE.sub(" ", CITE_RE.sub(" ", t))

async def main():
    async with async_session_factory() as db:
        rows = (await db.execute(text("""
            SELECT c.case_id, c.year, c.facts_text, c.issues_text,
                   array_agg(ci.cited_case_id) AS cited
            FROM cases c JOIN citations ci ON ci.citing_case_id = c.case_id
            GROUP BY c.case_id, c.year, c.facts_text, c.issues_text
            HAVING count(ci.cited_case_id) >= 2          -- need ≥2 labels to be useful
        """))).fetchall()

    queries, qrels = [], []
    for case_id, year, facts, issues, cited in rows:
        q = strip_leakage(((facts or "")[:1500] + " " + (issues or "")[:1000]).strip())
        if len(q) < 200:                                  # too short to be a real query
            continue
        queries.append({"qid": case_id, "text": q, "year": year})
        for tgt in set(cited):
            qrels.append(f"{case_id} 0 {tgt} 1")           # TREC qrels format

    json.dump(queries, open("data/eval/queries.json", "w"), indent=2, ensure_ascii=False)
    open("data/eval/qrels.txt", "w").write("\n".join(qrels) + "\n")
    rel_per_q = len(qrels) / max(len(queries), 1)
    print(f"Q={len(queries)} queries, {len(qrels)} judgements, "
          f"mean relevant/query = {rel_per_q:.2f}")     # ← this is Q51

asyncio.run(main())
```

**Before committing to (a), check option (c).** If an ILDC-derived or COLIEE-style Indian set can be obtained, it skips the Q48 leakage minefield entirely and lets you compare against published numbers. Worth thirty minutes of searching.

Option (b), human annotation, is scientifically strongest but needs law students, written guidelines, and κ — unlikely to fit the timeline.

### Q48. If (a): are the query judgment's own citations removed before embedding?

**Not yet applicable — but read before implementing (a), because the trap is already laid.**

Under (a) the leakage risk is severe and nothing in the pipeline prevents it:

1. **Citation text sits inside the embedded region.** The embedded text is `facts + issues + reasoning + outcome` truncated to 1000 characters (Q9), and Indian judgments cite in the facts. Nothing strips citations at any stage.
2. **The lexical channel is the bigger hole.** `text_search_vector` covers `title + facts_text + issues_text` (Q35), so case names and citation strings there are directly matchable tokens. A query judgment citing *Puttaswamy* lexically matches *Puttaswamy* — the model does not reason, it copies. (Mitigating detail: `reasoning_text` is *not* indexed, so citations appearing only in reasoning are already invisible to this channel. Do not rely on that.)
3. **No leakage guard exists anywhere** — no masking, no self-exclusion, no temporal filter on the semantic side.

**Mandatory if you implement (a):**
- Strip citation strings **and** case names from query text before embedding *and* before the tsvector query — the `strip_leakage()` function above does both.
- Exclude the query case from its own pool (Q55).
- Exclude cases decided after the query (Q56).
- **Verify by inspection:** print 20 stripped queries and confirm no residual case names. Put a stripped example in the appendix — it pre-empts the reviewer's first question.

**The question is right that this is the first thing a reviewer checks. Skip it and every number is invalid in a trivially detectable way.**

### Q49. If (b): annotators, guidelines, agreement

**Not applicable — no annotation performed.** If you go this route the paper needs: annotator count and legal background; guidelines verbatim in an appendix; the double-annotated sample size; and Cohen's κ (two raters) or Fleiss' κ (three or more). Budget realistically — 100 queries × 10 candidates is a large undertaking, and legal relevance judgement is slow.

**A cheap hybrid worth considering:** build labels via (a), then have one law student validate a 50-query sample. Report agreement between citation-derived labels and human judgement. **That single number substantially strengthens the (a) methodology at a fraction of the cost of full annotation**, and it directly answers the reviewer who doubts that citation implies relevance.

### Q50. How many query cases Q? — **determined by Q47's script**

**Zero today.** PRD §12 targets 100. The `build_golden_set.py` script prints Q directly. Target ≥ 50 for the paired bootstrap (Q63) to have power; 100+ is better. If the script yields too few, widen the corpus year range (Q51) — that is the lever.

### Q51. Average relevant precedents per query — **printed by the same script**

The script's `mean relevant/query` line answers this.

**Compute it before choosing your headline metric.** The question's guidance is exactly right: **if the mean is under 5, P@10 has a ceiling below 0.5 and is close to meaningless — lead with MRR and nDCG.**

**Expect a low number, and understand why:** it is the mean out-degree of the citation graph *restricted to in-corpus targets*. Most cases cited by a 2024 judgment are older, so on a 2024-only corpus almost every citation points outside the corpus and is dropped.

**This is the strongest argument for widening the corpus, and it has a long lead time — start ingestion early.** A 2015–2024 corpus is close to a prerequisite for option (a) to work at all. Report the in-corpus resolution rate alongside the mean; it explains the number and doubles as your extraction-recall proxy (Q19).

### Q52. Binary or graded relevance?

**Undecided — nothing exists.** Under (a), the natural graded scheme:

| Grade | Criterion |
|---|---|
| 2 | Cited **and** discussed — the citation appears in `reasoning_text`, or within N sentences of "held"/"relied"/"followed" |
| 1 | Cited in passing — appears only in a citation list |
| 0 | Not cited |

This requires the extractor to record citation *context* — capture the surrounding window and which segment it fell in, which is a small addition to `extract_citations.py`. **If you can grade, grade** — binary nDCG is much less interesting, and with a low relevant-per-query count nDCG is likely to be your headline metric. Emit graded qrels (`qid 0 docid 2`) and `ir_measures` handles the rest.

---

## B3. Splits and leakage

### Q53. Train / dev / test sizes

**ABSENT.** Note that nothing is *trained* — the encoder is frozen and all weights are hand-set — so "train" is a misnomer. What you need is a **dev set** for any threshold or weight tuning (Q61, Q62) and a **held-out test set** reported once.

**Procedure:** split the queries from Q47 **temporally** (Q54) — earliest 60% dev, latest 40% test, or a fixed year boundary. Keep them disjoint and say so explicitly. With hand-set parameters the temptation to tune on test is high and reviewers know it.

### Q54. Random or temporal split? — **temporal, and argue for it**

**Neither exists yet. Temporal is both more defensible and more realistic**: it mirrors how precedent search works, since no judge can cite the future, and it eliminates an entire leakage class automatically (Q56).

**Feasibility is good** — `year` is indexed, and the retriever already supports year filtering ([`retriever.py:169-179`](Backend/app/agents/retriever.py#L169-L179)):
```sql
AND year >= :year_from    AND year <= :year_to
```

**One gap you must close first: that filter applies only to the lexical channel. The FAISS channel ignores filters entirely** ([`retriever.py:211`](Backend/app/agents/retriever.py#L211) passes none). **A temporal split enforced through the existing mechanism would leak through the semantic half of the system.** Fix by post-filtering FAISS hits before the RRF merge:

```python
# retriever.py — inside _faiss_search, after results are returned
if filters and filters.get("year_to"):
    keep = {r["case_id"] for r in results
            if int(str(r["case_id"])[:4]) <= int(filters["year_to"])}
    results = [r for r in results if r["case_id"] in keep]
    for i, r in enumerate(results, 1):     # re-rank after filtering — RRF uses ranks
        r["faiss_rank"] = i
```
Note the re-ranking step: RRF consumes *ranks*, so filtering without renumbering would corrupt the fusion. **Over-fetch (say `top_k * 3`) before filtering** so you still have 50 candidates afterwards.

Also: `year` comes from the filename, not the decision date (Q42), so a temporal split is year-granular. Loading `decision_date` (Q18 Step 1) upgrades it to day granularity.

### Q55. Is the query case excluded from its own pool?

**Not currently — and there is a working pattern in the codebase to copy.**

Under (a) the query *is* a judgment, its vector is in the index, and self-cosine is 1.0. **It will rank first every time.**

`/cases/{id}/similar` already handles it ([`cases.py:57-58`](Backend/app/api/v1/cases.py#L57-L58)):
```python
results = faiss_idx.search(embedding, top_k=top_k + 1)      # over-fetch by one
results = [r for r in results if r["case_id"] != case_id][:top_k]
```
Replicate this in the harness, on **both** channels — the lexical side needs `AND case_id <> :qid` too. **Confirm the exclusion in writing in the paper**, as the question asks.

### Q56. Are later cases that cite the query excluded?

**No — nothing prevents it, and this is the subtlest leak.** A 2024 case citing your 2020 query judgment is topically near-identical and sitting in the pool; retrieving it is retrieving the future.

**A temporal split (Q54) eliminates this class entirely and automatically** — the strongest practical argument for adopting one. Pass `filters={"year_to": query_year - 1}` on every eval call, with the FAISS fix in place.

If you use a random split instead, exclude all cases decided after the query date explicitly in the harness — and remember that delegating it to the existing filter mechanism does not work until the FAISS gap is closed.

---

## B4. Runs completed

### Q57. Which conditions have real numbers today?

**None. Zero conditions have been run.** No harness, no results files, no logs, no notebooks, no CSVs.

With one paper, these become **two tables in the same results section** — Table 1 the retrieval evidence, Table 2 the agent-level evidence.

**Table 1 — retrieval ablations (LLM-free, deterministic; the paper's core evidence):**

| Condition | Status | How to run it |
|---|---|---|
| BM25 (`ts_rank`) | **ABSENT** | `_bm25_search` alone |
| Dense | **ABSENT** | `_faiss_search` alone |
| Hybrid (RRF) | **ABSENT** | Retriever, no weighter |
| Hybrid + authority | **ABSENT** | Retriever + weighter — **caveat below** |
| Hybrid − semantic | **ABSENT** | Lexical + weighter |
| ~~Hybrid − structural~~ | — | **Drop this row — no structural channel exists (Q13)** |
| *Optional:* `plainto_tsquery` vs OR-builder | **ABSENT** | One-line switch — ablates a real design decision (Q59) |

**Table 2 — agent-level ablations (LLM-dependent; inherits the §0.2 model caveat):**

| Condition | Status | How to run it |
|---|---|---|
| B1 semantic-only | **ABSENT** | Call `_faiss_search` alone; skip RRF |
| B2 hybrid single-pass | **ABSENT** | Retriever + weighter, 1 iteration, `enable_debate=False` |
| B3 hybrid fixed-3-pass | **ABSENT** | Force 3 iterations, bypass the early exit — **see Q58 first** |
| V full system | **ABSENT** | Current default |

**Caveat on "− precedential" that must not be missed.** Because two authority signals are dead constants (Q18, Q21), removing the weighter today removes a component containing only recency, RRF, and domain match. **The ablation would show a small effect, and a reader would misattribute that to precedential weighting being unimportant when in fact it was never active.** Either populate the metadata first (Q18 Step 1 — cheap, high value) or state exactly what the component contained when ablated.

**The frontend Experimentation Suite is not a harness.** [`ExperimentMode.jsx`](Frontend/webapp/src/pages/ExperimentMode.jsx) is a static mockup — the toggles are hardcoded booleans wired to nothing, "Run Ablation Test" has no handler, and the comparison tab shows fabricated results (*"Outcome Confidence: 92.4%"*, precedents *"Smith (98%)"* and *"Torres (94%)"* — placeholder American names from the original UI mock). **No number from that page may appear in the paper.**

**The harness itself** (this is the "how" for the whole of B4):

```python
# Backend/scripts/eval/run_eval.py
"""Runs all conditions over the golden set, writes TREC run files.
Table 1 conditions need NO LLM — reformulated_queries=[] bypasses the planner."""
import asyncio, json
from app.core.database import async_session_factory
from app.agents.retriever import RetrieverAgent, merge_rankings
from app.agents.precedent_weighter import PrecedentWeighterAgent

QUERIES = json.load(open("data/eval/queries.json"))

async def run_condition(name, db, use_dense=True, use_lexical=True, use_authority=True):
    lines = []
    for q in QUERIES:
        filters = {"year_to": q["year"] - 1}          # temporal split (Q54/Q56)
        r = RetrieverAgent(db_session=db)
        dense   = await r._faiss_search(q["text"], 50) if use_dense else []
        lexical = await r._bm25_search(q["text"], 50, filters) if use_lexical else []
        dense   = [d for d in dense if d["case_id"] != q["qid"]]      # self-exclusion (Q55)
        lexical = [d for d in lexical if d["case_id"] != q["qid"]]
        cands   = merge_rankings(dense, lexical)[:50]
        if use_authority:
            w = await PrecedentWeighterAgent(db_session=db).execute(
                {"query_id": q["qid"], "candidates": cands, "legal_domain": "general"})
            ranked = w["ranked_cases"]
            key = lambda c: c.get("authority_score", 0)
        else:
            ranked, key = cands, (lambda c: c.get("rrf_score", 0))
        for rank, c in enumerate(ranked[:20], 1):
            lines.append(f'{q["qid"]} Q0 {c["case_id"]} {rank} {key(c):.6f} {name}')
    open(f"data/eval/run_{name}.txt", "w").write("\n".join(lines) + "\n")
    print(f"{name}: {len(lines)} lines")

async def main():
    async with async_session_factory() as db:
        await run_condition("bm25",       db, use_dense=False, use_authority=False)
        await run_condition("dense",      db, use_lexical=False, use_authority=False)
        await run_condition("hybrid",     db, use_authority=False)
        await run_condition("hybrid_auth",db)

asyncio.run(main())
```
Then score with a standard library (Q60). The Table 2 conditions need the scheduler in the loop and therefore the LLM; run them separately with a fixed seed (Q38).

### Q58. B3 — fixed-depth iteration without the scheduler

**Not run — and there is a structural problem beyond simply not having been run. Read this before scheduling the experiment.**

*(The question called this "the condition Paper 1 lives or dies on". With one paper it is no longer load-bearing — see §0.4 — but it remains the difference between a real result and a null one.)*

Per Q23, a refinement iteration is **identical** to the first: same plan, same K, same filters, deterministic retriever. So B3 (fixed 3 passes) and V (adaptive) compute the **same candidate set** on every pass. The only difference is how many times the same computation repeats.

**As the code stands, B3 and V produce identical rankings, and the scheduling contribution measures exactly zero.** Running it now yields a null result — not because scheduling is worthless, but because nothing varies between iterations for scheduling to exploit.

**Three ways forward** (the third is newly available now that this is one section of a system paper rather than a paper's thesis):

**(i) Make iterations actually differ — recommended.** In the scheduler loop, vary the input per iteration:
```python
# scheduler.py — inside the while loop, before calling the retriever
reforms = plan_result.get("reformulated_queries", [])
retriever_input = {
    **plan_result,
    "filters": filters,
    # iteration 1: original; iteration 2: first reformulation; iteration 3: second
    "reformulated_queries": reforms[iteration - 1: iteration],
}
settings_k = settings.max_query_k * iteration          # widen the pool each pass (PRD's expand_k)
```
**This reuses the reformulations you already generate and discard (Q7), so it fixes two questions with one change.** Then B3 vs V measures something real: does *deciding when to stop* beat *always running three*?

**(ii) Reduce the claim to early stopping.** V terminates after one iteration when confidence suffices; B3 always runs three. The contribution becomes efficiency — latency and compute saved at equal quality — not quality. Smaller, entirely honest, and writable against the current code.

**(iii) Report it as a negative result.** State that refinement iterations are identical by construction, so adaptive and fixed-depth scheduling coincide, and that naive re-querying without input variation cannot improve retrieval. **Inside a system paper this is a perfectly respectable half-page** — it tells readers something true about a design many would otherwise assume works. The two-paper plan could not have accommodated it; one paper can.

**Recommendation: (i), with (iii) as the fallback if time runs out.** It is the smallest engineering change on this document that turns a null result into a real one.

### Q59. BM25 implementation and parameters

**Not `rank_bm25`, not Elasticsearch, not Pyserini — and strictly, not BM25.**

It is PostgreSQL full-text search: `ts_rank(text_search_vector, to_tsquery('english', :tsquery))` over a GIN index ([`retriever.py:134-144`](Backend/app/agents/retriever.py#L134-L144)).

**`ts_rank` is not BM25.** It is Postgres's own term-frequency/position ranking. **There is no k₁ and no b** — those parameters do not exist in Postgres FTS. The optional weights array and normalisation flag are unused, so it runs at defaults.

**Call it "PostgreSQL full-text ranking (`ts_rank`)" throughout the paper, never BM25.** The codebase calls it `bm25_score` internally, which is exactly how this error would reach print.

**One genuinely interesting design decision worth writing up** ([`retriever.py:86-112`](Backend/app/agents/retriever.py#L86-L112)): the query is not passed to `plainto_tsquery` (which ANDs terms and yields very low recall on long legal queries). Instead a custom builder extracts words ≥ 4 characters, removes a 24-word stoplist that deliberately includes legal-domain terms (`case`, `court`, `supreme`, `india`, `indian` — they match everything in an SC corpus), deduplicates preserving order, takes the **top 8**, and joins with `|`. That is a real, describable recall-oriented choice and a legitimate small contribution. **Ablate it** — `plainto_tsquery` vs the OR builder is a clean one-line condition and makes the point empirically.

**Add a true BM25 baseline.** `ts_rank` is a weak and unusual comparator. `pip install rank_bm25`, tokenise the corpus once, and report k₁ = 1.2, b = 0.75 (the standard defaults). Pure Python, no infrastructure, and it makes the comparison one reviewers recognise.

### Q60. Metric computation — own code or standard library?

**Hand-rolled, and it contains exactly the quiet error the question anticipates.** `_dcg`/`_ndcg` in [`evaluator.py:16-30`](Backend/app/agents/evaluator.py#L16-L30) are hand-written. **The formula is textbook-correct** (`rel / log2(i+2)`); the defect is the input — the "relevance scores" are the system's own `final_score` and the ideal is those values re-sorted (Q26). No library is present: no `pytrec_eval`, no `ir_measures`, no `scikit-learn`.

**Use a standard library for every reported number:**
```bash
pip install ir_measures        # wraps pytrec_eval; simpler API
```
```python
import ir_measures
from ir_measures import nDCG, P, RR, R
qrels = list(ir_measures.read_trec_qrels("data/eval/qrels.txt"))
for cond in ["bm25", "dense", "hybrid", "hybrid_auth"]:
    run = list(ir_measures.read_trec_run(f"data/eval/run_{cond}.txt"))
    print(cond, ir_measures.calc_aggregate([nDCG@10, P@5, P@10, RR, R@20], qrels, run))
```
Three reasons: it eliminates this error class; the qrels/run format *forces* the discipline that surfaces leakage and self-referential labels; and reviewers trust standard tooling. Keep the in-pipeline evaluator for the scheduler's gating decision — just never report its output as retrieval quality.

Use `ir_measures.iter_calc(...)` to get **per-query** scores — you need those for the bootstrap (Q63).

### Q61. Has the weight grid search been run?

**No. ABSENT** — no search code, no dev split, no labelled data to optimise against. **Delete the grid-search claim** (Q14).

**How to run it once ground truth exists.** The space is small: 5 authority weights, the fusion weights, and RRF k. Disable debate so each configuration is seconds, not minutes.
```python
import itertools, ir_measures
from ir_measures import nDCG
best = None
grid = [w/20 for w in range(0, 21)]                     # 0.00 … 1.00 in steps of 0.05
for cit, bench, rec, fact in itertools.product(grid, repeat=4):
    if cit + bench + rec + fact > 1.0: continue
    dom = round(1.0 - cit - bench - rec - fact, 4)
    score = evaluate_on_dev(cit, bench, rec, fact, dom)  # returns nDCG@10 on the DEV split
    if best is None or score > best[0]:
        best = (score, cit, bench, rec, fact, dom)
print("best on dev:", best)
```
**Report the resolution (0.05), the searched ranges, the split it was searched on, and final numbers on the held-out test set only.** Also report the *unfitted* hand-set weights as a condition — "hand-set vs fitted" is itself an informative row.

### Q62. Have the sensitivity sweeps been run?

**No.** β and ω **do not exist as parameters** (Q14, Q15) — these specific sweeps have no object.

**Parameters that do exist and make meaningful sweeps:**

| Parameter | Current | Sweep range | Why it matters |
|---|---|---|---|
| **RRF k** | 60 | 10, 20, 40, 60, 80, 100 | **The most publishable** — a real fusion parameter, standard to report |
| Authority blend | 0.3 | 0.0 … 1.0 by 0.1 | The genuine semantic-vs-authority trade-off, and the closest real analogue to β |
| τ_c | 0.55 | 0.3 … 0.9 | Iteration count vs quality (Table 2) |
| Candidate pool | 50 | 20, 50, 100, 200 | Recall vs latency |
| Top-8 keyword cap | 8 | 4, 8, 12, 16 | Lexical recall |

Each is a loop over `run_eval.py` with one constant changed. **ω becomes meaningful only with segment-level scoring** (Tier 3).

### Q63. Paired bootstrap or significance test?

**No. ABSENT** — no statistical testing; `scipy` is not in requirements (though the snippet below needs only `numpy`).

```python
import numpy as np, ir_measures
from ir_measures import nDCG

def per_query(run_file, qrels):
    run = list(ir_measures.read_trec_run(run_file))
    return {m.query_id: m.value for m in ir_measures.iter_calc([nDCG@10], qrels, run)}

def paired_bootstrap(a, b, n=10000, seed=42):
    """a, b: dicts qid -> metric. Returns (mean diff, 95% CI, P(a>b))."""
    rng  = np.random.default_rng(seed)
    qids = sorted(set(a) & set(b))
    d    = np.array([a[q] - b[q] for q in qids])
    idx  = rng.integers(0, len(d), size=(n, len(d)))
    means = d[idx].mean(axis=1)
    return d.mean(), (np.percentile(means, 2.5), np.percentile(means, 97.5)), (means > 0).mean()
```
**10,000 resamples** is conventional and cheap at Q ≤ 100. **Paired is essential** — the conditions run on identical queries, so pairing removes query-difficulty variance and gives far more power on a small Q.

**Be prepared for wide intervals** given a likely Q of ~100 with a low relevant-per-query count, and report them honestly. A modest improvement with an interval crossing zero, reported as such, is respectable. An unqualified point estimate is not.

---

## B5. Beyond the tables

### Q64. Categorised failure analysis

**ABSENT — not started.** Nothing prevents it once results exist, and the persisted trace makes attribution unusually tractable.

**Procedure:** take the 30 queries with the worst nDCG@10 from the test run, and for each inspect the top-5 retrieved against the qrels, tagging with:

| Category | Diagnostic signal already available |
|---|---|
| Segmentation error | `segmentation_method == "heuristic_fallback"` on the retrieved case |
| Truncation miss | Relevant content beyond the 1000-char cut (Q9) |
| Lexical miss | Query terms absent from the top-8 keyword list (Q59) |
| Lexical blind spot | Relevant content only in `reasoning_text`, which is not indexed (Q35) |
| Authority mis-weighting | Currently attributable only to recency/domain (Q20) |
| Debate error | Synthesis promoted a weaker case — inspect `debate_rounds` |
| Planner error | `confidence == 0.3` marks the JSON-degradation path (Q33) |
| Missing from corpus | Gold case not in `cases` at all — a corpus-coverage problem, not a retrieval one |

**That last row matters more than it looks:** on a narrow corpus a large share of "failures" will be cases that were never ingested, and separating those from genuine retrieval misses changes the story considerably. **30 categorised failures is achievable and it is one of the most persuasive sections you can write**, not least because several categories map onto limitations you must disclose anyway — turning a defensive passage into an analytical one.

### Q65. Two or three concrete hybrid-beats-dense examples

**None identified — recoverable from a single evaluation run**, and the question is right that they are worth more than a decimal point of nDCG.

**Procedure — mechanical, not hand-picked:**
```python
dense_s  = per_query("data/eval/run_dense.txt",  qrels)
hybrid_s = per_query("data/eval/run_hybrid.txt", qrels)
wins = sorted(((hybrid_s[q] - dense_s[q], q) for q in dense_s if q in hybrid_s), reverse=True)
for delta, qid in wins[:5]:
    print(f"Δ nDCG@10 = {delta:+.3f}   qid={qid}")
```
Then for each winner, print the per-channel ranks of the gold cases — **both are already available**, `faiss_rank` from the index wrapper and the lexical rank feeding RRF. Log them during the eval run.

**The mechanism to look for is well defined here and easy to narrate.** A hybrid win will typically be a query containing a **specific statutory or numeric token** — a section number, an Act name, an Article — which the lexical channel matches exactly but the dense channel misses, because `all-MiniLM-L6-v2` has no legal pretraining and treats "Section 138" as unremarkable tokens, **and** because the document vector covers only ~1000 characters so a statute cited mid-judgment is invisible to it (Q9). The smoke-test query in [`test_scores.py`](test_scores.py) — *"Can an unstamped arbitration agreement be enforced under the Arbitration and Conciliation Act 1996?"* — is exactly this shape.

Present each example as: query text → gold case → dense rank → lexical rank → fused rank → one sentence of mechanism. **Mechanistically true, not hand-waved.**

### Q66. Is human evaluation of explanations planned?

**Not implemented, not designed, no protocol.** Mark as future work unless you commit to running it.

Evaluable outputs that exist: `consensus_rationale` from synthesis, per-case `relevance_argument` and `weakness`, and the component score breakdown (Q17).

**If you run it**, the paper needs: rater count and legal background; outputs per rater; overlap for agreement; the construct — **faithfulness** ("does this explain why the system actually ranked it?") and **usefulness** are different questions and must be separate items; the scale (5-point Likert); and the statistic (Krippendorff's α for ordinal, κ for categorical). A minimum viable version — 3 raters × 30 explanations × 2 items, with 10 overlapping for agreement — is about a day's work and is enough to report.

**One integrity point that must not be glossed.** The advocate prompt receives the case text and the query — **never the scores or the signals that produced the rank** ([`debate.py:34-51`](Backend/app/agents/debate.py#L34-L51)). **So the explanation is a plausible post-hoc justification, not a faithful account of the ranking mechanism.** If you measure faithfulness that is precisely what you will find; stating it up front is far better than having a reviewer derive it. **The genuinely faithful explainability in this system is the numeric component breakdown (Q17), not the generated prose** — draw that distinction explicitly in the paper.

### Q67. Hardware for latency measurements

**No measurements exist (Q36), so no hardware has been recorded.** When you measure, record in the paper: CPU model and cores; RAM; **GPU model and VRAM** (decisive — GPU vs CPU for an 8B model is roughly 10× and is the single most important number for interpreting your timings); OS and version; Ollama version; whether Ollama, Postgres, and the API shared one machine; and corpus size at measurement time.

Also state that debate calls are **deliberately sequential** because Ollama on a single GPU queues concurrent requests anyway ([`debate.py:8-13`](Backend/app/agents/debate.py#L8-L13)) — so the figures are single-GPU-serialised **by design**, and the paper should say so rather than leave a reader assuming a parallelism that was consciously avoided.

---

# PART C — Similarity integrity

**Most of this part was written for a two-submission plan and no longer applies.** With one paper: the Paper-1-vs-Paper-2 overlap measurement (C1) is moot, the duplicate-acknowledgement fix (C2) is unnecessary, and the Elsevier duplicate-contribution screen (C4) is not a concern. What survives is the general similarity guidance, which still holds and is recorded below.

## C1–C2. Still applicable
- Turnitin: **Exclude bibliography** and **Exclude quotes** on; **Exclude small matches** at 8–10 words.
- The `ecrc.sty` instructions-to-authors block is already deleted — confirmed by the supervisor.
- Expect 3–6% from references alone without exclusions; this is normal and every examiner knows it.
- ~~Reword one acknowledgement so the two submissions do not match~~ — **no longer needed.**
- **Zero overlap with the team's own reports is a real asset, and the risk it guards against is unchanged by the single-paper decision.** Turnitin indexes student submissions, so if the synopsis was ever uploaded through an institutional account it is sitting in the repository waiting to match. See C3.1.

## C3. Rules, unchanged
1. **Never paste from the synopsis, IEI report, or PPT.** Currently zero; keep it there. **This document is subject to the same rule** — it tells you what is true, it does not supply prose. Do not paste from it.
2. **Do not paraphrase cited work sentence-by-sentence.** Describe DELTA and ReaKase-8B from understanding, in your own structure.
3. **Write the discussion yourselves.** Doubly important now: it must be built from measurements that do not yet exist. **Do not pre-write it with placeholder numbers** — placeholders have a way of surviving into submissions.
4. **Run the check before submission**, exclusions on, inspecting the *student papers* category specifically.

## C4. The risk that replaces dual-submission screening

Dropping to one paper removes the duplicate-contribution concern entirely. **It does not remove — and slightly concentrates — the larger exposure, which is claim accuracy.**

This document identifies roughly two dozen places where the drafted material asserts something the code does not do: Gemini, approximate nearest-neighbour indexing, BM25, seven agents, PageRank, court tiers, isotonic calibration, grid-searched weights, structural span alignment, WebSocket streaming. Each is checkable in seconds against a repository that will be public.

**A paper flagged for an unsupported claim is worse than one flagged at 12% similarity**, and unlike a similarity score there is no exclusion setting that makes it go away. Before submission, every claim should be traceable to a file and line. The delete-list at the end of this document is the working checklist for that pass.

---

# Consolidated action plan

Ordered by dependency. Tier 0 must complete before *any* results table can exist.

### Tier 0 — Nothing can be reported until these are done

| # | Task | Effort | Unblocks |
|---|---|---|---|
| 1 | **Load Parquet metadata into `cases`** (`citation`, `bench`, `decision_date`, `disposal_nature`, `acts_sections`) — Q18 Step 1 | ~60 lines | **The root unblock (§0.1).** Tasks 2, 6; Q21, Q43 |
| 2 | **Build the citation extractor and populate `citations`** — Q18 Step 2 | ~80 lines | Ground truth (Q47), citation graph (Q18), the 0.35 signal (Q20) — **three blockers, one task** |
| 3 | **Remove the rank-1–3 score floor** | 2 lines | Every metric — leaving it in invalidates all of them |
| 4 | **Build the golden set** — `build_golden_set.py` (Q47), with leakage stripping (Q48) | ~50 lines | All of B4; prints Q50, Q51 |
| 5 | **Fix the FAISS filter gap**, with rank renumbering — Q54 | ~10 lines | Temporal splits (Q54, Q56) — otherwise the split is illusory |
| 6 | **Build the eval harness** — `run_eval.py` + `ir_measures` (Q57, Q60) | ~120 lines | Every results table in the paper |

### Tier 1 — Required for the paper's central claims

| # | Task | Effort | Why |
|---|---|---|---|
| 7 | **Make refinement iterations differ** — vary K and cycle the reformulations | ~20 lines | Without it B3 ≡ V and the scheduler result is null (Q58). Also fixes Q7. **Now optional — Q58(iii) is an honest fallback** |
| 8 | **Switch to an instruction-tuned model + enable constrained JSON** | 1 line + 4 call sites | §0.2(b) — the highest-value response to the weak-model problem |
| 9 | **Fix the LLM seed** (`"seed": 42`) | 1 line | Reproducibility (Q38) — far easier now than explaining later |
| 10 | **Paired bootstrap** (Q63) | ~15 lines | Significance for every reported difference |

### Tier 2 — Cheap measurements, high paper value

| # | Task | Effort | Yields |
|---|---|---|---|
| 11 | `segmentation_method` counts | 1 command | Segmentation quality (Q5) — no annotation needed |
| 12 | Five-stage file counts | 5 commands | Corpus attrition table (Q46) |
| 13 | Trace SQL — iterations, latency, debate impact | 3 queries + 1 script | Q27, Q28, Q31, Q36 |
| 14 | Document-length + fraction-embedded stats | 2 snippets | Q44, and quantifies the Q9 limitation |
| 15 | Near-duplicate detection over existing vectors | ~15 lines | Q45 |
| 16 | Surface `get_usage_stats()` into the trace | 2 lines | Real token counts (Q37) |
| 17 | Parse-failure rate from logs and DB | 2 commands | Q33 — characterises the model honestly |
| 18 | Record measurement hardware | 5 minutes | Q67 — without it timings are uninterpretable |
| 19 | Hand-check 50 documents for segmentation accuracy | ~1 day | Q5 — a real accuracy number |
| 20 | Hand-annotate 20 documents for citation recall | ~2 hours | Q19 — validates Tier 0 Task 2 |

### Tier 3 — Larger; likely future work

| # | Task | Note |
|---|---|---|
| 21 | Chunk-and-pool embeddings instead of 1000-char truncation | **Likely the largest retrieval-quality win available** (Q9) |
| 22 | Add `rank_bm25` as a true BM25 baseline | Q59 — `ts_rank` alone is a weak comparator |
| 23 | Index `reasoning_text` + `outcome_text` in the tsvector | Q35 — the lexical channel currently sees half the document |
| 24 | Segment-level scoring → a real structural channel | Prerequisite for ω, Eq. (2)–(4), everything the drafted similarity section claims |
| 25 | **Widen the corpus to 2015–2024** | **Long lead time — start now.** Option (a) is weak on one year (Q51) |
| 26 | PageRank over the citation graph | Q20 — only sensible after Task 2 |
| 27 | Human evaluation of explanations | Q66 |

### Delete from the paper before submission

Gemini (all mentions) · "approximate nearest-neighbour" / sublinear retrieval · BM25 (say `ts_rank`) · seven agents (say six) · PageRank · court-tier weights · overruled flag ψ (set to 0, state the limitation) · isotonic calibration · grid-searched weights · structural span alignment and Eq. (2)–(4) · α, β, γ, ω · WebSocket/SSE streaming (say polling) · Celery / distributed task queue · 99% uptime, NFR-04 · P95 < 8 s · multiple retrieval intents (unless Task 7 is done) · any number from `ExperimentMode.jsx`

### Also delete from the repository

`Backend/agents/` — stale scaffolding, imported by nothing, and the last thing you want a reviewer to find in a cloned repo.

### Keep and lead with — these are real

Fully local inference, zero API cost, no data egress — a substantive argument for judicial deployment · exact (non-approximate) search, so ablations are not confounded by index error · per-stage agent trace persisted and served live — genuine auditability · component scores retained per candidate — genuine numeric explainability · the recall-oriented OR-`tsquery` construction — a real design decision, and ablatable · graceful degradation throughout (circuit breaker, per-call timeouts, never-drop-cases fallbacks) · stateless, idempotent agent contract · 8 LLM calls per query, well inside budget

---

*Prepared from static analysis of commit `96210ee`. Every claim is traceable to a cited file and line. Every missing number is marked as such and carries a procedure. Please fill them from measurement, not from the synopsis.*
