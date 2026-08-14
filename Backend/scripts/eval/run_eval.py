"""
Run every retrieval condition over the golden set and write TREC run files.

NO LLM IS INVOLVED. The retriever reads `original_query` and `reformulated_queries`
from its input dict, and `reformulated[:1]` on an empty list is simply empty — so the
Query Planner can be bypassed entirely. Consequence: the paper's core evidence is
deterministic, reproducible, and completely unaffected by the quality of the local
8B model.

Conditions:
    dense           FAISS only
    tsrank          PostgreSQL ts_rank only          (what the deployed system uses)
    bm25            rank_bm25 only                   (true BM25 baseline, k1/b reportable)
    hybrid          RRF(dense, tsrank)               (the system's retrieval)
    hybrid_bm25     RRF(dense, bm25)
    hybrid_auth     RRF(dense, tsrank) + authority re-rank   (the full pipeline)

LEAKAGE CONTROLS APPLIED ON EVERY CONDITION:
    * temporal filter  — candidates restricted to year < query year   (Q54, Q56)
      applied to BOTH channels, including FAISS, which the app itself does not do (Q54)
    * self-exclusion   — the query case removed from its own pool     (Q55)
    * rank renumbering — after filtering, because RRF consumes RANKS  (Q54)

Usage (from Backend/):
    python -m scripts.eval.run_eval --data-dir ../data
    python -m scripts.eval.run_eval --data-dir ../data --conditions dense,bm25,hybrid
    python -m scripts.eval.run_eval --data-dir ../data --split test
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from scripts.lib.report import Report

# Condition names map onto the paper's Table 1 labels:
#   bm25         -> "BM25 Okapi, k1=1.2, b=0.75"
#   tsrank_conj  -> "L-conj  conjunctive tsquery"    (plainto_tsquery, the default)
#   tsrank       -> "L       disjunctive tsquery"    (the recall-oriented OR builder)
#   dense        -> "D       dense only"
#   hybrid       -> "F       rank fusion"
#   hybrid_auth  -> "F+A     fusion and authority"
ALL_CONDITIONS = ["bm25", "tsrank_conj", "tsrank", "dense", "hybrid", "hybrid_bm25", "hybrid_auth"]

# Improved system (v2). Each replaces one weak component identified by the first run:
#   bm25s          proper BM25, persistent + sparse, replaces ts_rank
#   dense_chunk    chunked BGE-small embeddings, replaces the 4.7 %-coverage single vector
#   hybrid_v2      weighted RRF over the two above
#   hybrid_v2_auth + the authority re-rank
V2_CONDITIONS = ["bm25s", "dense_chunk", "hybrid_v2", "hybrid_v2_auth", "hybrid_v2_authc",
                 "bm25s_ce", "hybrid_v3", "hybrid_v3_auth", "hybrid_v4"]

# v5. The v2 lexical index covers title+facts+issues = 20 % of the judgment; the
# reasoning section, where precedents are actually discussed, was never indexed.
#   bm25_full        whole judgment, document level  — the STRONGER BASELINE to beat
#   bm25_chunk       whole judgment, passage level, max-pooled
#   *_rm3            + RM3 pseudo-relevance feedback
#   hybrid_v5        weighted RRF over passage-lexical + doc-lexical + dense-chunk
V5_CONDITIONS = ["bm25_full", "bm25_chunk", "bm25_full_rm3", "bm25_chunk_rm3",
                 "hybrid_v5", "hybrid_v5_rm3", "hybrid_lex", "hybrid_lex_rm3",
                 "hybrid_lex3", "hybrid_v6", "hybrid_v6_rm3",
                 "cite_prop", "hybrid_cite", "hybrid_v7", "bm25_grid"]

# rank_bm25 BM25Okapi defaults are k1=1.5, b=0.75. We set k1=1.2 explicitly so the
# reported parameters match the conventional Robertson/Okapi values quoted in the paper.
BM25_K1 = 1.2
BM25_B = 0.75


def _year_of(case_id: str) -> int:
    m = re.match(r"^(\d{4})_", case_id)
    return int(m.group(1)) if m else 0


def _renumber(results: list[dict], key: str) -> list[dict]:
    """RRF consumes ranks, so any filtering must be followed by renumbering."""
    for i, r in enumerate(results, 1):
        r[key] = i
    return results


RRF_K = [60]
GRID_INDEX = ["bm25_full"]
# Document-level lexical index used by every condition that reads full text, including
# the neighbour retrieval inside cite_prop. Made configurable so the SYSTEM and the
# BASELINE can be held at the same tuned (k1, b) — comparing a tuned baseline against
# an untuned system channel would understate us, and the reverse would be dishonest.
LEX_INDEX = ["bm25_full"]


def merge_weighted(lists: list[list[dict]], weights: list[float], k: int | None = None) -> list[dict]:
    """
    Weighted Reciprocal Rank Fusion.

    Plain RRF weights every channel equally. The first evaluation showed why that is a
    problem: fusing the weak dense channel with BM25 produced a WORSE result than BM25
    alone (P@1 8.13 vs 11.18) — a mostly-wrong channel drags down a mostly-right one,
    because RRF is symmetric. Weighting lets a strong channel dominate while a weaker
    one still contributes its independent evidence.

    weight 1.0 for every list reduces exactly to standard RRF.
    """
    if k is None:
        k = RRF_K[0]
    scores: dict[str, dict[str, float]] = {}
    for lst, w in zip(lists, weights):
        for rank, r in enumerate(lst, 1):
            cid = r["case_id"]
            e = scores.setdefault(cid, {"rrf_score": 0.0, "faiss_score": 0.0, "bm25_score": 0.0})
            e["rrf_score"] += w / (k + rank)
            if "faiss_score" in r:
                e["faiss_score"] = r["faiss_score"]
            if "bm25_score" in r:
                e["bm25_score"] = r["bm25_score"]
    merged = [{"case_id": cid, **d} for cid, d in scores.items()]
    merged.sort(key=lambda x: x["rrf_score"], reverse=True)
    return merged


class Harness:
    """
    Thin evaluation harness. Shares the RANKING MATHS with the application
    (merge_rankings, the authority formula) but owns its own storage access, so a
    condition can be isolated without going through the agent pipeline.
    """

    def __init__(self, db, data_dir: Path, top_k: int, depth: int,
                 w_lex: float = 1.0, w_dense: float = 1.0, w_auth: float = 0.0,
                 w_full: float = 1.0, w_sum: float = 0.5, w_cite: float = 0.5) -> None:
        self.w_lex = w_lex
        self.w_dense = w_dense
        self.w_auth = w_auth
        self.w_full = w_full
        self.w_sum = w_sum
        self.w_cite = w_cite
        self.db = db
        self.data_dir = data_dir
        self.top_k = top_k
        self.depth = depth
        self._bm25 = None
        self._bm25_ids: list[str] = []
        self._bm25s = None
        self._bm25s_ids: list[str] = []
        self._stemmer = None
        self._chunk_index = None
        self._chunk_owner: dict = {}
        self._chunk_model = None
        self._warned_fallback = False
        self._ce = None
        self._doc_text: dict[str, str] = {}
        # index_name -> (bm25 object, owner list, is_passage_level)
        self._bm25_idx: dict[str, tuple] = {}
        self._tok_cache: dict[str, list[str]] = {}
        self.cite_neighbours = 50
        self.cite_rr_k = 10.0
        self.rm3_fb_docs = 10
        self.rm3_fb_terms = 20
        self.rm3_alpha = 0.6
        self.ce_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        self.chunk_model_name = "BAAI/bge-small-en-v1.5"

    # ── dense ─────────────────────────────────────────────────────────────
    async def dense(self, text: str, qid: str, max_year: int) -> list[dict]:
        from app.core.faiss_index import get_faiss_index
        from app.services.embedding_service import get_embedding

        idx = get_faiss_index()
        if not idx.is_loaded:
            idx.load()
        emb = await get_embedding(text)
        # Over-fetch, because the temporal filter and self-exclusion will remove some.
        raw = idx.search(emb, top_k=self.top_k * self.depth)
        keep = [r for r in raw
                if r["case_id"] != qid and (max_year <= 0 or _year_of(r["case_id"]) <= max_year)]
        return _renumber(keep[: self.top_k], "faiss_rank")

    # ── ts_rank, disjunctive (what the deployed system uses) ──────────────
    async def tsrank(self, text: str, qid: str, max_year: int) -> list[dict]:
        """
        The system's lexical channel: a hand-built OR-tsquery over content words.
        NOTE: ts_rank is NOT BM25 — it is Postgres's own term-frequency ranking and
        has no k1 or b. The `bm25` condition below is the real BM25 baseline.
        """
        from app.agents.retriever import RetrieverAgent
        tsquery = RetrieverAgent._build_or_tsquery(text)
        if not tsquery:
            return []
        return await self._tsrank_exec(
            "to_tsquery('english', :q)", tsquery, qid, max_year)

    # ── ts_rank, conjunctive (the default that was rejected) ──────────────
    async def tsrank_conj(self, text: str, qid: str, max_year: int) -> list[dict]:
        """
        Conjunctive counterpart of the system's disjunctive builder.

        Uses the SAME top-8 keyword selection and joins with & instead of |, so the
        ablation isolates the conjunction/disjunction decision rather than conflating
        it with term selection.

        (Measured separately: passing the raw ~2,000-character query to
        plainto_tsquery — the truly naive default — ANDs roughly 300 terms and returns
        ZERO results for every query in the test set. That is reported as a finding in
        its own right; it is not a usable baseline.)
        """
        from app.agents.retriever import RetrieverAgent
        or_query = RetrieverAgent._build_or_tsquery(text)
        if not or_query:
            return []
        and_query = or_query.replace(" | ", " & ")
        return await self._tsrank_exec(
            "to_tsquery('english', :q)", and_query, qid, max_year)

    async def _tsrank_exec(self, tsq_expr: str, q: str, qid: str, max_year: int) -> list[dict]:
        from sqlalchemy import text as sa_text
        sql = sa_text(f"""
            SELECT case_id, ts_rank(text_search_vector, {tsq_expr}) AS score
            FROM cases
            WHERE text_search_vector @@ {tsq_expr}
              AND case_id <> :qid
              AND (:maxyear <= 0 OR year <= :maxyear)
            ORDER BY score DESC
            LIMIT :k
        """)
        try:
            rows = (await self.db.execute(
                sql, {"q": q, "qid": qid, "maxyear": max_year, "k": self.top_k}
            )).fetchall()
        except Exception as e:
            print(f"[warn] ts_rank failed for {qid}: {e}")
            return []
        out = [{"case_id": r[0], "bm25_score": float(r[1])} for r in rows]
        return _renumber(out, "bm25_rank")

    # ── chunked dense (BGE, max-pooled to case level) ─────────────────────
    async def dense_chunk(self, text: str, qid: str, max_year: int) -> list[dict]:
        """
        Search the chunk index and max-pool to case level: a case scores as well as
        its single best-matching passage. This is what lets a precedent discussed only
        in the reasoning section be found — the original single-vector index covered
        4.7 % of a document, effectively the opening paragraph of facts.
        """
        import faiss, numpy as np
        chunk_path = self.data_dir / "index" / "cases_chunk.index"
        if self._chunk_index is None and not chunk_path.exists():
            # Fall back to the original single-vector index so the fusion conditions
            # remain runnable before the chunk index has been built. Reported as
            # `dense_chunk (fallback)` — do not confuse the two in the results.
            if not self._warned_fallback:
                print("[warn] no chunk index; dense_chunk falling back to the "
                      "single-vector index")
                self._warned_fallback = True
            return await self.dense(text, qid, max_year)
        if self._chunk_index is None:
            self._chunk_index = faiss.read_index(str(chunk_path))
            self._chunk_owner = json.loads(
                (self.data_dir / "index" / "cases_chunk_mapping.json").read_text(encoding="utf-8"))
            from sentence_transformers import SentenceTransformer
            self._chunk_model = SentenceTransformer(self.chunk_model_name)

        # BGE expects an instruction prefix on QUERIES only; documents are embedded bare.
        q = "Represent this sentence for searching relevant passages: " + text
        vec = self._chunk_model.encode([q], convert_to_numpy=True,
                                       normalize_embeddings=True).astype("float32")
        faiss.normalize_L2(vec)
        # Over-fetch heavily: many chunks map to the same case, and filtering removes more.
        n = min(self.top_k * self.depth * 20, self._chunk_index.ntotal)
        D, I = self._chunk_index.search(vec, n)

        best: dict[str, float] = {}
        for score, ci in zip(D[0], I[0]):
            if ci < 0:
                continue
            cid = self._chunk_owner.get(str(int(ci)))
            if cid is None or cid == qid:
                continue
            if max_year > 0 and _year_of(cid) > max_year:
                continue
            s = float(score)
            if s > best.get(cid, -1e9):          # max-pool over the case's chunks
                best[cid] = s
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[: self.top_k]
        return _renumber([{"case_id": c, "faiss_score": s} for c, s in ranked], "faiss_rank")

    # ── BM25 via bm25s (persistent, sparse, fast) ─────────────────────────
    async def bm25s_search(self, text: str, qid: str, max_year: int) -> list[dict]:
        import bm25s, Stemmer
        if self._bm25s is None:
            d = self.data_dir / "index" / "bm25"
            self._bm25s = bm25s.BM25.load(str(d), load_corpus=False)
            self._bm25s_ids = json.loads((d / "case_ids.json").read_text(encoding="utf-8"))
            self._stemmer = Stemmer.Stemmer("english")
        toks = bm25s.tokenize([text], stopwords="en", stemmer=self._stemmer,
                              show_progress=False)
        n = min(self.top_k * self.depth, len(self._bm25s_ids))
        res, scores = self._bm25s.retrieve(toks, k=n, show_progress=False)
        out = []
        for j, s in zip(res[0], scores[0]):
            cid = self._bm25s_ids[int(j)]
            if cid == qid or (max_year > 0 and _year_of(cid) > max_year):
                continue
            out.append({"case_id": cid, "bm25_score": float(s)})
            if len(out) >= self.top_k:
                break
        return _renumber(out, "bm25_rank")

    # ── generic BM25 over any index dir, max-pooled to case level ─────────
    def _load_bm25_index(self, index_name: str):
        """
        Load one of the persistent bm25s indexes and its unit -> case_id map.

            bm25        title + facts + issues        (v2; 20 % of the document)
            bm25_full   + reasoning + outcome         (whole judgment, doc level)
            bm25_chunk  the same text, passage level  (1800/200/16, as the dense channel)

        `owner.json` maps unit index -> case_id. For a doc-level index that is one
        entry per case; for a passage-level index many units share a case, which is
        what the max-pool below collapses.
        """
        if index_name in self._bm25_idx:
            return self._bm25_idx[index_name]
        import bm25s, Stemmer
        d = self.data_dir / "index" / index_name
        if not (d / "owner.json").exists() and index_name == "bm25":
            # the v2 index predates owner.json; its case_ids.json serves the same role
            owner = json.loads((d / "case_ids.json").read_text(encoding="utf-8"))
        else:
            owner = json.loads((d / "owner.json").read_text(encoding="utf-8"))
        obj = bm25s.BM25.load(str(d), load_corpus=False)
        if self._stemmer is None:
            self._stemmer = Stemmer.Stemmer("english")
        is_passage = len(set(owner)) < len(owner)
        self._bm25_idx[index_name] = (obj, owner, is_passage)
        return self._bm25_idx[index_name]

    async def bm25_pooled(self, index_name: str, text: str, qid: str,
                          max_year: int, limit: int | None = None) -> list[dict]:
        """
        Score with BM25 and max-pool to case level: a case scores as well as its single
        best-matching passage.

        WHY MAX-POOLING MATTERS FOR THE LEXICAL CHANNEL. BM25's `b` parameter penalises
        long documents, and these judgments average ~44,000 characters. A decisive
        paragraph is diluted across thousands of unrelated terms, and the length prior
        pushes the whole document down regardless. Scoring passages independently and
        keeping each case's best removes both effects. On a doc-level index the pool is
        a no-op (one unit per case), so the same code path serves both.
        """
        import bm25s
        # `limit` lets a caller ask for a deeper list than the run's reporting depth.
        # cite_prop needs this: its neighbour vote was silently capped at top_k, so
        # asking for 50 or 200 neighbours had no effect whatsoever.
        cap = limit or self.top_k
        obj, owner, is_passage = self._load_bm25_index(index_name)
        toks = bm25s.tokenize([text], stopwords="en", stemmer=self._stemmer,
                              show_progress=False)
        # Over-fetch far more on a passage index: many units collapse onto one case,
        # and the temporal filter removes more still.
        mult = self.depth * (12 if is_passage else 1)
        n = min(cap * mult, len(owner))
        res, scores = obj.retrieve(toks, k=n, show_progress=False)

        best: dict[str, float] = {}
        for j, s in zip(res[0], scores[0]):
            cid = owner[int(j)]
            if cid == qid or (max_year > 0 and _year_of(cid) > max_year):
                continue
            s = float(s)
            if s > best.get(cid, -1e9):
                best[cid] = s
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:cap]
        return _renumber([{"case_id": c, "bm25_score": s} for c, s in ranked], "bm25_rank")

    # ── RM3 pseudo-relevance feedback ─────────────────────────────────────
    def _seg_tokens(self, cid: str) -> list[str]:
        """Stemmed content tokens of a judgment, read from the segmented JSON."""
        if cid in self._tok_cache:
            return self._tok_cache[cid]
        import bm25s
        p = self.data_dir / "processed" / "segmented" / f"{cid}.json"
        toks: list[str] = []
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                from scripts.eval.build_query_sets import clean_ocr
                raw = " ".join((d.get(k) or "")
                               for k in ("facts", "issues", "reasoning", "outcome"))
                # Cap per document: feedback needs the term distribution, not every token.
                t = bm25s.tokenize([clean_ocr(raw)[:60000]], stopwords="en",
                                   stemmer=self._stemmer, show_progress=False)
                vocab = {v: k for k, v in t.vocab.items()}
                toks = [vocab[i] for i in t.ids[0] if i in vocab]
            except Exception:
                toks = []
        # Bound the cache — 984 queries x 10 feedback docs would otherwise hold the
        # whole corpus as token lists, which is what pushed the v1 run into swap.
        if len(self._tok_cache) < 3000:
            self._tok_cache[cid] = toks
        return toks

    async def rm3_query(self, index_name: str, text: str, qid: str, max_year: int) -> str:
        """
        Expand the query with RM3 relevance-model terms drawn from the top feedback
        documents of a first-pass retrieval.

        RM3 estimates P(t | R) = sum_d P(t | d) P(d | q) over the pseudo-relevant set,
        then interpolates that distribution with the original query. It is the standard
        strong-BM25 configuration and the usual reason a lexical run beats plain BM25.

        NO LEAKAGE: the feedback set comes from the first-pass ranking alone. The qrels,
        the citation graph and the query's own case are never consulted, and the
        temporal filter applies to the feedback documents exactly as it does to the
        final ranking.

        Weights are realised by REPEATING a term in the query string rather than by a
        weighted query vector, because bm25s scores a token list. Repetition is
        equivalent up to BM25's within-query saturation, which is flat here.
        """
        import bm25s
        first = await self.bm25_pooled(index_name, text, qid, max_year)
        fb = first[: self.rm3_fb_docs]
        if not fb:
            return text

        # P(d | q): retrieval scores normalised over the feedback set.
        tot = sum(max(c["bm25_score"], 0.0) for c in fb) or 1.0
        weights: dict[str, float] = {}
        for c in fb:
            toks = self._seg_tokens(c["case_id"])
            if not toks:
                continue
            pdq = max(c["bm25_score"], 0.0) / tot
            n = len(toks)
            tf: dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            for t, f in tf.items():
                if len(t) < 3:
                    continue
                weights[t] = weights.get(t, 0.0) + pdq * (f / n)      # P(t|d) P(d|q)

        if not weights:
            return text
        top = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[: self.rm3_fb_terms]
        mx = top[0][1] or 1.0

        # Original query terms carry weight alpha; expansion terms share (1 - alpha),
        # scaled by their relevance-model weight. Repetition counts are small integers.
        q_toks = bm25s.tokenize([text], stopwords="en", stemmer=self._stemmer,
                                show_progress=False)
        vocab = {v: k for k, v in q_toks.vocab.items()}
        orig = [vocab[i] for i in q_toks.ids[0] if i in vocab]
        base = max(1, int(round(self.rm3_alpha * 10)))
        parts = orig * base
        for t, w in top:
            reps = max(1, int(round((1.0 - self.rm3_alpha) * 10 * (w / mx))))
            parts.extend([t] * reps)
        return " ".join(parts)

    async def bm25_rm3(self, index_name: str, text: str, qid: str,
                       max_year: int) -> list[dict]:
        q = await self.rm3_query(index_name, text, qid, max_year)
        return await self.bm25_pooled(index_name, q, qid, max_year)

    # ── citation propagation through text-similar neighbours ──────────────
    async def cite_prop(self, text: str, qid: str, max_year: int,
                        n_neighbours: int | None = None) -> list[dict]:
        """
        Recommend a precedent because CASES LIKE THIS ONE cited it.

        The authority experiments failed because they scored a candidate by its GLOBAL
        in-degree — how famous it is — which is nearly independent of the query. This
        channel uses the citation graph in the targeted way instead:

            1. retrieve the text-nearest earlier judgments N (the "neighbours")
            2. score candidate C by  sum over N of  w(N) * 1[N cites C]

        If past cases about the same question relied on C, this case probably should
        too. That is precisely the structure citation-derived ground truth encodes, and
        it is a different kind of evidence from term overlap between the query and C —
        C is reachable even when its own text shares little vocabulary with the query.

        LEAKAGE CONTROLS (this channel touches the citation graph, so these matter and
        are the same failure mode documented in RESULTS_V2 §4):
          * the query case is never in the neighbour set (self-exclusion upstream), so
            the label edge Q -> C is never read;
          * neighbours are restricted to year <= max_year, so only citations a reader
            could have seen at query time contribute;
          * candidates are filtered by year as well, and C == qid is dropped.

        The neighbour weight is reciprocal-rank rather than the raw BM25 score, so one
        very high-scoring neighbour cannot dominate the vote.
        """
        from sqlalchemy import text as sa_text
        if n_neighbours is None:
            n_neighbours = self.cite_neighbours
        neigh = await self.bm25_pooled(LEX_INDEX[0], text, qid, max_year,
                                       limit=n_neighbours)
        if not neigh:
            return []
        nids = [n["case_id"] for n in neigh]
        wt = {n["case_id"]: 1.0 / (self.cite_rr_k + i) for i, n in enumerate(neigh, 1)}

        rows = (await self.db.execute(sa_text("""
            SELECT ci.citing_case_id, ci.cited_case_id
            FROM citations ci
            JOIN cases c ON c.case_id = ci.citing_case_id
            WHERE ci.citing_case_id = ANY(:nids)
              AND ci.cited_case_id <> :qid
              AND (:maxyear <= 0 OR c.year <= :maxyear)
        """), {"nids": nids, "qid": qid, "maxyear": max_year})).fetchall()

        votes: dict[str, float] = {}
        for citing, cited in rows:
            if max_year > 0 and _year_of(cited) > max_year:
                continue
            votes[cited] = votes.get(cited, 0.0) + wt.get(citing, 0.0)
        if not votes:
            return []
        ranked = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)[: self.top_k]
        return _renumber([{"case_id": c, "cite_prop_score": s} for c, s in ranked],
                         "cite_rank")

    # ── authority as a fused PRIOR rather than a re-sort ──────────────────
    async def authority_prior(self, cands: list[dict], qid: str, max_year: int) -> list[dict]:
        """
        Rank candidates by leakage-clean citation count alone, to be fused with the
        retrieval channels rather than replacing them.

        Why this and not the deployed re-rank: `authority_score` gives only 0.20 weight
        to retrieval evidence, so sorting by it throws away 80 % of what retrieval knew.
        Measured, that costs P@1 (5.59 -> 4.57). Fusing an authority *ranking* into RRF
        with a small weight keeps retrieval dominant while still expressing the prior
        that prominent precedents are more likely to be cited again — preferential
        attachment, a real property of citation networks.

        Leakage controls identical to authority_clean: no self-edge, no future citations.
        """
        from sqlalchemy import text as sa_text
        if not cands:
            return []
        ids = [c["case_id"] for c in cands]
        rows = (await self.db.execute(sa_text("""
            SELECT ci.cited_case_id, count(*)
            FROM citations ci
            JOIN cases c ON c.case_id = ci.citing_case_id
            WHERE ci.cited_case_id = ANY(:ids)
              AND ci.citing_case_id <> :qid
              AND (:maxyear <= 0 OR c.year <= :maxyear)
            GROUP BY ci.cited_case_id
        """), {"ids": ids, "qid": qid, "maxyear": max_year})).fetchall()
        cites = {r[0]: float(r[1]) for r in rows}
        # Candidates with no in-corpus citations carry no prior and are dropped from
        # this list; RRF simply gives them no contribution from this channel.
        ranked = [c for c in cands if cites.get(c["case_id"], 0.0) > 0]
        ranked.sort(key=lambda c: cites[c["case_id"]], reverse=True)
        return _renumber([{**c, "cite_count": cites[c["case_id"]]} for c in ranked], "auth_rank")

    # ── cross-encoder reranking ───────────────────────────────────────────
    async def rerank_ce(self, cands: list[dict], query: str, top_n: int = 50) -> list[dict]:
        """
        Re-score the top-N fused candidates with a cross-encoder.

        Bi-encoders (the dense channel) embed query and document independently, so they
        can only measure coarse topical similarity. A cross-encoder reads the pair
        jointly and is far more accurate — it is the standard second stage in modern IR
        and the usual way a neural system overtakes BM25.

        Applied to the top-50 only, so cost is bounded: ~500 pairs/s on CPU means about
        0.1 s per query. No leakage: it sees only the query text and the candidate's own
        text, never the citation graph or the labels.
        """
        from sqlalchemy import text as sa_text
        if not cands:
            return []
        head = cands[:top_n]
        tail = cands[top_n:]
        ids = [c["case_id"] for c in head]

        missing = [i for i in ids if i not in self._doc_text]
        if missing:
            rows = (await self.db.execute(sa_text(
                "SELECT case_id, coalesce(title,'') || '. ' || coalesce(issues_text,'') "
                "|| ' ' || coalesce(facts_text,'') FROM cases WHERE case_id = ANY(:ids)"
            ), {"ids": missing})).fetchall()
            for cid, txt in rows:
                self._doc_text[cid] = (txt or "")[:1200]

        if self._ce is None:
            from sentence_transformers import CrossEncoder
            self._ce = CrossEncoder(self.ce_model_name, device="cpu", max_length=512)

        pairs = [(query[:800], self._doc_text.get(c["case_id"], "")) for c in head]
        scores = self._ce.predict(pairs, batch_size=64, show_progress_bar=False)
        for c, s in zip(head, scores):
            c["ce_score"] = float(s)
        head.sort(key=lambda x: x["ce_score"], reverse=True)
        return head + tail

    # ── authority re-rank with LEAKAGE-CLEAN citation counts ──────────────
    async def authority_clean(self, cands: list[dict], qid: str, max_year: int) -> list[dict]:
        """
        Re-implements the precedent-weighting score with two corrections that the
        deployed agent does not make, both of which matter for evaluation validity:

        1. SELF-EDGE EXCLUSION. The qrels say "C is relevant to Q because Q cites C".
           The citation graph contains that very edge, so C's in-degree is inflated by
           the label itself. Every relevant candidate gets a +1 that no irrelevant
           candidate gets. Excluding citing_case_id = qid removes it.

        2. TEMPORAL FILTER ON THE GRAPH. An unfiltered in-degree counts citations from
           judgments decided AFTER the query — a case looks authoritative because of
           what happened in its future. Restricting citing cases to year <= max_year
           makes the signal causally available at query time.

        Without these the authority gain is partly an artefact. `hybrid_v2_auth` uses
        the deployed agent; `hybrid_v2_authc` uses this. Comparing them measures the
        size of the artefact.
        """
        from sqlalchemy import text as sa_text
        if not cands:
            return []
        ids = [c["case_id"] for c in cands]

        rows = (await self.db.execute(sa_text("""
            SELECT ci.cited_case_id, count(*)
            FROM citations ci
            JOIN cases c ON c.case_id = ci.citing_case_id
            WHERE ci.cited_case_id = ANY(:ids)
              AND ci.citing_case_id <> :qid
              AND (:maxyear <= 0 OR c.year <= :maxyear)
            GROUP BY ci.cited_case_id
        """), {"ids": ids, "qid": qid, "maxyear": max_year})).fetchall()
        cites = {r[0]: float(r[1]) for r in rows}

        meta_rows = (await self.db.execute(sa_text(
            "SELECT case_id, year, bench FROM cases WHERE case_id = ANY(:ids)"
        ), {"ids": ids})).fetchall()
        meta = {r[0]: (r[1], r[2]) for r in meta_rows}

        from app.agents.precedent_weighter import (
            WEIGHTS, _bench_size_score, _extract_bench_size, _norm, _recency_score)

        scored = []
        for c in cands:
            cid = c["case_id"]
            yr, bench = meta.get(cid, (None, None))
            scored.append({
                **c,
                "cite_count": cites.get(cid, 0.0),
                "raw_bench": _bench_size_score(_extract_bench_size(bench)),
                "raw_recency": _recency_score(yr),
                "domain_score": 0.3,
                "factual_alignment": c.get("rrf_score", 0.0),
            })
        mx_c = max((s["cite_count"] for s in scored), default=0.0) or 1.0
        mn_c = min((s["cite_count"] for s in scored), default=0.0)
        mx_f = max((s["factual_alignment"] for s in scored), default=0.0) or 1.0
        mn_f = min((s["factual_alignment"] for s in scored), default=0.0)
        for s in scored:
            s["authority_score"] = round(min(1.0,
                WEIGHTS["citation_count"] * _norm(s["cite_count"], mn_c, mx_c)
                + WEIGHTS["bench_size"] * s["raw_bench"]
                + WEIGHTS["recency"] * s["raw_recency"]
                + WEIGHTS["factual_alignment"] * _norm(s["factual_alignment"], mn_f, mx_f)
                + WEIGHTS["domain_match"] * s["domain_score"]), 4)
        scored.sort(key=lambda x: x["authority_score"], reverse=True)
        return scored

    # ── true BM25 (rank_bm25 — kept for the original comparison) ──────────
    async def _ensure_bm25(self) -> None:
        if self._bm25 is not None:
            return
        from rank_bm25 import BM25Okapi
        from sqlalchemy import text as sa_text

        cache = self.data_dir / "eval" / "bm25_corpus.json"
        if cache.exists():
            payload = json.loads(cache.read_text(encoding="utf-8"))
            ids, toks = payload["ids"], payload["tokens"]
        else:
            print("[info] building BM25 index (one-off; cached afterwards) ...")
            rows = (await self.db.execute(sa_text(
                "SELECT case_id, coalesce(title,'') || ' ' || coalesce(facts_text,'') "
                "|| ' ' || coalesce(issues_text,'') FROM cases"
            ))).fetchall()
            ids = [r[0] for r in rows]
            # Cap tokens per document. Without this, 7k judgments x ~2.5k tokens are held
            # as Python strings (several GB), which pushes the process into swap and slows
            # every LATER condition in the same run to a crawl. 2,000 tokens covers the
            # title + facts + issues that the lexical index actually contains.
            toks = [re.findall(r"[a-z]{3,}", (r[1] or "").lower())[:2000] for r in rows]
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"ids": ids, "tokens": toks}), encoding="utf-8")
            print(f"[info] BM25 index built over {len(ids)} documents")
        self._bm25_ids = ids
        self._bm25 = BM25Okapi(toks, k1=BM25_K1, b=BM25_B)

    async def bm25(self, text: str, qid: str, max_year: int) -> list[dict]:
        await self._ensure_bm25()
        import numpy as np
        toks = re.findall(r"[a-z]{3,}", text.lower())
        if not toks:
            return []
        scores = self._bm25.get_scores(toks)
        order = np.argsort(scores)[::-1][: self.top_k * self.depth]
        out = []
        for i in order:
            cid = self._bm25_ids[int(i)]
            if cid == qid or (max_year > 0 and _year_of(cid) > max_year):
                continue
            out.append({"case_id": cid, "bm25_score": float(scores[int(i)])})
            if len(out) >= self.top_k:
                break
        return _renumber(out, "bm25_rank")


# Suffix appended to run filenames so different query regimes (short / keyword /
# long) can coexist in data/eval/ instead of overwriting one another.
TAG = [""]


async def run_condition(name: str, h: Harness, queries: list[dict], out_dir: Path,
                        use_authority: bool = False) -> dict[str, Any]:
    from app.agents.retriever import merge_rankings

    lines: list[str] = []
    latencies: list[float] = []
    empty = 0

    for n, q in enumerate(queries, 1):
        qid, text = q["qid"], q["text"]
        max_year = (q.get("year") or 0) - 1          # strict temporal split (Q54/Q56)
        t0 = time.monotonic()

        if name == "dense":
            cands = await h.dense(text, qid, max_year)
        elif name == "tsrank":
            cands = await h.tsrank(text, qid, max_year)
        elif name == "tsrank_conj":
            cands = await h.tsrank_conj(text, qid, max_year)
        elif name == "bm25":
            cands = await h.bm25(text, qid, max_year)
        elif name == "hybrid":
            cands = merge_rankings(await h.dense(text, qid, max_year),
                                   await h.tsrank(text, qid, max_year))
        elif name == "hybrid_bm25":
            cands = merge_rankings(await h.dense(text, qid, max_year),
                                   await h.bm25(text, qid, max_year))
        elif name == "bm25s":
            cands = await h.bm25s_search(text, qid, max_year)
        elif name == "dense_chunk":
            cands = await h.dense_chunk(text, qid, max_year)
        elif name in ("hybrid_v2", "hybrid_v2_auth", "hybrid_v2_authc"):
            dn = await h.dense_chunk(text, qid, max_year)
            lx = await h.bm25s_search(text, qid, max_year)
            cands = merge_weighted([lx, dn], [h.w_lex, h.w_dense])
            if name == "hybrid_v2_auth":
                use_authority = True
            elif name == "hybrid_v2_authc":
                ranked = await h.authority_clean(cands[: h.top_k], qid, max_year)
                latencies.append((time.monotonic() - t0) * 1000)
                if not ranked:
                    empty += 1
                for rank, c in enumerate(ranked[: h.top_k], 1):
                    lines.append(f"{qid} Q0 {c['case_id']} {rank} {c.get('authority_score',0.0):.6f} {name}")
                continue
        elif name == "hybrid_v4":
            # lexical + dense + authority PRIOR, all fused (authority never re-sorts)
            dn = await h.dense_chunk(text, qid, max_year)
            lx = await h.bm25s_search(text, qid, max_year)
            base = merge_weighted([lx, dn], [h.w_lex, h.w_dense])
            ap = await h.authority_prior(base[: h.top_k * 2], qid, max_year)
            cands = merge_weighted([lx, dn, ap], [h.w_lex, h.w_dense, h.w_auth])
        elif name == "bm25_full":
            cands = await h.bm25_pooled(LEX_INDEX[0], text, qid, max_year)
        elif name == "bm25_chunk":
            cands = await h.bm25_pooled("bm25_chunk", text, qid, max_year)
        elif name == "bm25_full_rm3":
            cands = await h.bm25_rm3(LEX_INDEX[0], text, qid, max_year)
        elif name == "bm25_chunk_rm3":
            cands = await h.bm25_rm3("bm25_chunk", text, qid, max_year)
        elif name == "bm25_grid":
            # doc-level full-text BM25 over an arbitrary index dir (k1/b tuning)
            cands = await h.bm25_pooled(GRID_INDEX[0], text, qid, max_year)
        elif name == "cite_prop":
            cands = await h.cite_prop(text, qid, max_year)
        elif name == "hybrid_cite":
            # lexical (doc + passage) + citation propagation
            fl = await h.bm25_pooled(LEX_INDEX[0], text, qid, max_year)
            lx = await h.bm25_pooled("bm25_chunk", text, qid, max_year)
            cp = await h.cite_prop(text, qid, max_year)
            cands = merge_weighted([lx, fl, cp], [h.w_lex, h.w_full, h.w_cite])
        elif name == "hybrid_v7":
            # the full system: two lexical views + dense chunks + citation propagation
            fl = await h.bm25_pooled(LEX_INDEX[0], text, qid, max_year)
            lx = await h.bm25_pooled("bm25_chunk", text, qid, max_year)
            dn = await h.dense_chunk(text, qid, max_year)
            cp = await h.cite_prop(text, qid, max_year)
            cands = merge_weighted([lx, fl, dn, cp],
                                   [h.w_lex, h.w_full, h.w_dense, h.w_cite])
        elif name == "hybrid_lex3":
            # Three lexical views of the same corpus, fused. The v2 index (title +
            # facts + issues) is not redundant with the full-text one: it is a SUMMARY
            # FIELD view, where a term match is not diluted by 40k characters of
            # reasoning. Fusing field views is the rank-level analogue of BM25F.
            fl = await h.bm25_pooled(LEX_INDEX[0], text, qid, max_year)
            lx = await h.bm25_pooled("bm25_chunk", text, qid, max_year)
            sm = await h.bm25_pooled("bm25", text, qid, max_year)
            cands = merge_weighted([lx, fl, sm], [h.w_lex, h.w_full, h.w_sum])
        elif name in ("hybrid_v6", "hybrid_v6_rm3"):
            # The full system: three lexical views + the chunked dense channel.
            if name == "hybrid_v6_rm3":
                fl = await h.bm25_rm3(LEX_INDEX[0], text, qid, max_year)
            else:
                fl = await h.bm25_pooled(LEX_INDEX[0], text, qid, max_year)
            lx = await h.bm25_pooled("bm25_chunk", text, qid, max_year)
            sm = await h.bm25_pooled("bm25", text, qid, max_year)
            dn = await h.dense_chunk(text, qid, max_year)
            cands = merge_weighted([lx, fl, sm, dn],
                                   [h.w_lex, h.w_full, h.w_sum, h.w_dense])
        elif name in ("hybrid_lex", "hybrid_lex_rm3"):
            # Lexical only: document-level and passage-level views of the same text.
            # Isolates what the two lexical views contribute before dense is added.
            if name == "hybrid_lex_rm3":
                fl = await h.bm25_rm3(LEX_INDEX[0], text, qid, max_year)
            else:
                fl = await h.bm25_pooled(LEX_INDEX[0], text, qid, max_year)
            lx = await h.bm25_pooled("bm25_chunk", text, qid, max_year)
            cands = merge_weighted([lx, fl], [h.w_lex, h.w_full])
        elif name in ("hybrid_v5", "hybrid_v5_rm3"):
            # Three channels reading the SAME full text three different ways:
            # passage-level lexical, document-level lexical, passage-level dense.
            if name == "hybrid_v5_rm3":
                lx = await h.bm25_rm3("bm25_chunk", text, qid, max_year)
            else:
                lx = await h.bm25_pooled("bm25_chunk", text, qid, max_year)
            fl = await h.bm25_pooled(LEX_INDEX[0], text, qid, max_year)
            dn = await h.dense_chunk(text, qid, max_year)
            cands = merge_weighted([lx, fl, dn], [h.w_lex, h.w_full, h.w_dense])
        elif name == "bm25s_ce":
            # BM25 + cross-encoder: isolates the reranker's contribution from fusion
            cands = await h.rerank_ce(await h.bm25s_search(text, qid, max_year), text)
        elif name in ("hybrid_v3", "hybrid_v3_auth"):
            dn = await h.dense_chunk(text, qid, max_year)
            lx = await h.bm25s_search(text, qid, max_year)
            fused = merge_weighted([lx, dn], [h.w_lex, h.w_dense])
            cands = await h.rerank_ce(fused[: h.top_k * 2], text)
            if name == "hybrid_v3_auth":
                ranked = await h.authority_clean(cands[: h.top_k], qid, max_year)
                latencies.append((time.monotonic() - t0) * 1000)
                for rank, c in enumerate(ranked[: h.top_k], 1):
                    lines.append(f"{qid} Q0 {c['case_id']} {rank} {c.get('authority_score',0.0):.6f} {name}")
                continue
        elif name == "hybrid_auth":
            cands = merge_rankings(await h.dense(text, qid, max_year),
                                   await h.tsrank(text, qid, max_year))
            use_authority = True
        else:
            raise ValueError(f"unknown condition {name}")

        cands = cands[: h.top_k]

        if use_authority and cands:
            from app.agents.precedent_weighter import PrecedentWeighterAgent
            w = await PrecedentWeighterAgent(db_session=h.db).execute(
                {"query_id": qid, "candidates": cands, "legal_domain": "general"})
            ranked = w.get("ranked_cases", [])
            score_of = lambda c: c.get("authority_score", 0.0)
        else:
            ranked = cands
            score_of = (lambda c: c.get("ce_score", c.get("rrf_score", c.get("faiss_score", c.get("bm25_score", 0.0)))))

        latencies.append((time.monotonic() - t0) * 1000)
        if not ranked:
            empty += 1
        for rank, c in enumerate(ranked[: h.top_k], 1):
            lines.append(f"{qid} Q0 {c['case_id']} {rank} {score_of(c):.6f} {name}")

        if n % 25 == 0:
            print(f"  [{name}] {n}/{len(queries)} queries ...", end="\r")

    path = out_dir / f"run_{name}{TAG[0]}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lat_sorted = sorted(latencies)
    stats = {
        "condition": name,
        "queries": len(queries),
        "lines": len(lines),
        "empty_result_queries": empty,
        "median_latency_ms": round(lat_sorted[len(lat_sorted)//2], 1) if lat_sorted else 0,
        "run_file": str(path),
    }
    print(f"  [{name}] done: {len(lines)} lines, {empty} empty, "
          f"median {stats['median_latency_ms']} ms")
    return stats


async def run(args: argparse.Namespace) -> None:
    from app.core.database import async_session_factory

    data = Path(args.data_dir)
    out_dir = data / "eval"
    qfile = out_dir / (args.queries or "queries.json")
    if not qfile.exists():
        raise SystemExit(f"No {qfile}. Run build_golden_set.py / build_query_sets.py first.")

    queries = json.loads(qfile.read_text(encoding="utf-8"))
    if args.split != "all":
        queries = [q for q in queries if q.get("split") == args.split]
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        raise SystemExit(f"No queries for split={args.split}")

    RRF_K[0] = args.rrf_k
    GRID_INDEX[0] = args.grid_index
    LEX_INDEX[0] = args.lex_index
    conditions = [c.strip() for c in args.conditions.split(",")] if args.conditions else ALL_CONDITIONS
    TAG[0] = args.tag

    rep = Report("run_eval", data, args)
    rep.section("Configuration")
    rep.stat("split", args.split)
    rep.stat("queries", len(queries))
    rep.stat("conditions", ", ".join(conditions))
    rep.stat("top_k", args.top_k)
    rep.stat("temporal_split", "year < query_year, applied to BOTH channels")
    rep.stat("self_exclusion", True)
    rep.stat("llm_used", False, "the planner is bypassed — results are deterministic")
    rep.note("BM25 parameters (rank_bm25 BM25Okapi defaults): k1=1.5, b=0.75. Report these.")

    print(f"[info] {len(queries)} queries, conditions: {', '.join(conditions)}")
    all_stats = []
    async with async_session_factory() as db:
        h = Harness(db, data, args.top_k, args.depth, args.w_lex, args.w_dense,
                    args.w_auth, args.w_full, args.w_sum, args.w_cite)
        h.cite_neighbours, h.cite_rr_k = args.cite_neighbours, args.cite_rr_k
        h.rm3_fb_docs, h.rm3_fb_terms, h.rm3_alpha = (
            args.rm3_fb_docs, args.rm3_fb_terms, args.rm3_alpha)
        for cond in conditions:
            if cond not in ALL_CONDITIONS + V2_CONDITIONS + V5_CONDITIONS:
                print(f"[warn] skipping unknown condition '{cond}'")
                continue
            print(f"\n[run] {cond}")
            try:
                all_stats.append(await run_condition(cond, h, queries, out_dir))
            except Exception as e:
                print(f"[error] condition {cond} failed: {e}")
                rep.note(f"Condition '{cond}' FAILED: {e}")

    if all_stats:
        rep.section("Runs produced")
        rep.table("Run files",
                  ["condition", "queries", "lines", "empty", "median_ms"],
                  [[s["condition"], s["queries"], s["lines"], s["empty_result_queries"],
                    s["median_latency_ms"]] for s in all_stats])
    rep.note("Next: python -m scripts.eval.score --data-dir ../data")
    rep.save()


def main() -> None:
    ap = argparse.ArgumentParser(description="Run retrieval conditions, write TREC run files")
    ap.add_argument("--data-dir", type=str, default="../data")
    ap.add_argument("--conditions", type=str, default=None,
                    help=f"comma-separated; default all: {','.join(ALL_CONDITIONS)}")
    ap.add_argument("--split", type=str, default="all", choices=["all", "dev", "test"])
    ap.add_argument("--top-k", type=int, default=20, help="results kept per query")
    ap.add_argument("--depth", type=int, default=5,
                    help="over-fetch multiplier before temporal filtering")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--queries", type=str, default=None,
                    help="query file under <data>/eval/ (e.g. queries_short.json). "
                         "Defaults to queries.json.")
    ap.add_argument("--w-lex", type=float, default=1.0,
                    help="weighted-RRF weight for the lexical channel (hybrid_v2)")
    ap.add_argument("--w-dense", type=float, default=1.0,
                    help="weighted-RRF weight for the dense channel (hybrid_v2)")
    ap.add_argument("--w-auth", type=float, default=0.3,
                    help="weighted-RRF weight for the authority prior (hybrid_v4)")
    ap.add_argument("--w-full", type=float, default=1.0,
                    help="weighted-RRF weight for the doc-level full-text channel (hybrid_v5)")
    ap.add_argument("--w-cite", type=float, default=0.5,
                    help="weighted-RRF weight for the citation-propagation channel")
    ap.add_argument("--cite-neighbours", type=int, default=50,
                    help="how many text-nearest earlier judgments vote in cite_prop")
    ap.add_argument("--cite-rr-k", type=float, default=10.0,
                    help="reciprocal-rank constant for the neighbour vote weight")
    ap.add_argument("--lex-index", type=str, default="bm25_full",
                    help="doc-level lexical index used by the system channels and by "
                         "cite_prop neighbour retrieval")
    ap.add_argument("--grid-index", type=str, default="bm25_full",
                    help="index dir under <data>/index for the bm25_grid condition")
    ap.add_argument("--rrf-k", type=float, default=60,
                    help="RRF constant. The default 60 is a TREC convention, not a law; "
                         "smaller values weight top ranks more sharply.")
    ap.add_argument("--w-sum", type=float, default=0.5,
                    help="weighted-RRF weight for the summary-field lexical view")
    ap.add_argument("--rm3-fb-docs", type=int, default=10,
                    help="RM3 pseudo-relevant feedback documents")
    ap.add_argument("--rm3-fb-terms", type=int, default=20,
                    help="RM3 expansion terms")
    ap.add_argument("--rm3-alpha", type=float, default=0.6,
                    help="RM3 interpolation: weight on the original query")
    ap.add_argument("--tag", type=str, default="",
                    help="suffix appended to run filenames, e.g. --tag _short")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
