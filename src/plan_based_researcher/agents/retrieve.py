"""Retrieve runner: ranking walk, ingest, per-paper hybrid chunks (RETR-02, RETR-03, RETR-04)."""

from __future__ import annotations

import asyncio
import logging

from langchain_openai import ChatOpenAI
from langsmith import trace

from plan_based_researcher.adapters.hybrid import HybridResult, HybridRetrievePort
from plan_based_researcher.agents.query_schema import (
    FormulatedRetrieveQuery,
    formulate_human,
    formulate_retry_human,
    step_eval_feedback,
)
from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.graph.state import merge_hole_tasks, merge_papers
from plan_based_researcher.ingest.chunk_build import build_chunk_drafts
from plan_based_researcher.ingest.expand import expand_hits
from plan_based_researcher.ingest.html_parse import ParsedPaper, parse_arxiv_html
from plan_based_researcher.ingest.pack import pack_hits
from plan_based_researcher.ingest.rerank import (
    RERANK_MODEL_ID,
    build_rerank_query,
    chunks_for_trace,
    cut_reranked,
    score_chunks,
)
from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import (
    ChunkDraft,
    ChunkRecord,
    ChunkRepository,
    PaperRecord,
)
from plan_based_researcher.ports.embeddings import EmbeddingPort
from plan_based_researcher.ports.papers import PaperPort

__all__ = ["RetrieveRunner", "fuse_hop_cuts", "normalize_retrieve_hops"]

logger = logging.getLogger(__name__)

_FORMULATE_SYSTEM = """\
You write a English retrieval query for hybrid search (vector + BM25) over \
chunks from papers already admitted for this thread. The runtime uses your query \
field as the retriever input when hops are empty or length 1. This is not an \
arXiv API search.

Rules:
- Put the query in the structured `query` field. Do not narrate.
- Always English keywords and phrases, even when the task is in another language.
- Write terms that should appear in paper chunks. Do not use arXiv syntax \
(ti:, abs:, AND, OR, ANDNOT, cat:).
- Do not copy the task prose as the query.
- hops are English chunk terms, not sentences. Do not copy the full retrieve \
task prose as a hop.
- Emit hops with length at least 2 only when the task asks for distinct \
coverages (separate facts or section-like requests that one chunk cannot cover).
- Emit empty hops when one chunk can cover the task.
- When Previous query or Evaluator feedback is present, honor the feedback and \
emit a different query from Previous query.

Example:
- Task: Retrieve passages that explain how LoRA updates weights
  query: LoRA low-rank adaptation weight update adapter matrices
  hops: []
"""


def _paper_record_from_ref(ref: dict) -> PaperRecord:
    return PaperRecord(
        arxiv_id=ref["arxiv_id"],
        version=ref["version"],
        title=ref.get("title") or "",
        year=int(ref.get("year") or 0),
        url=ref.get("url") or "",
        categories=list(ref.get("categories") or []),
    )


def _paper_ref_from_record(record: PaperRecord) -> dict:
    return {
        "arxiv_id": record.arxiv_id,
        "version": record.version,
        "title": record.title,
        "year": record.year,
        "url": record.url,
        "categories": list(record.categories),
    }


def _paper_ref_from_hit(key: dict, hits: list) -> dict:
    aid = key["arxiv_id"]
    ver = str(key.get("version") or "")
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        if hit.get("arxiv_id") == aid and str(hit.get("version") or "") == ver:
            return {
                "arxiv_id": aid,
                "version": ver,
                "title": hit.get("title") or "",
                "year": int(hit.get("year") or 0),
                "url": hit.get("url") or "",
                "categories": list(hit.get("categories") or []),
            }
    return {
        "arxiv_id": aid,
        "version": ver,
        "title": "",
        "year": 0,
        "url": "",
        "categories": [],
    }


def _unique_refs(papers: list, *, limit: int) -> list[dict]:
    selected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        key = (paper["arxiv_id"], paper["version"])
        if key in seen:
            continue
        seen.add(key)
        selected.append(paper)
        if len(selected) >= limit:
            break
    return selected


def _step_index(state: dict) -> int:
    try:
        return int(state.get("step_index") or 0)
    except (TypeError, ValueError):
        return 0


def _current_step(state: dict) -> dict:
    plan = state.get("plan") or []
    index = _step_index(state)
    if not isinstance(plan, list) or index < 0 or index >= len(plan):
        return {}
    step = plan[index]
    return step if isinstance(step, dict) else {}


def _retry_count(state: dict, retrieve_index: int) -> int:
    raw = state.get("retry_counts") or {}
    if not isinstance(raw, dict):
        return 0
    try:
        return int(raw.get(str(retrieve_index), 0) or 0)
    except (TypeError, ValueError):
        return 0


def _passed_search_indices(state: dict) -> list[int]:
    plan = state.get("plan") or []
    passed: set[int] = set()
    for item in state.get("passed_steps") or []:
        try:
            passed.add(int(item))
        except (TypeError, ValueError):
            continue
    if not isinstance(plan, list):
        return []
    indices: list[int] = []
    for i, step in enumerate(plan):
        if i not in passed or not isinstance(step, dict):
            continue
        if step.get("agent") == "search":
            indices.append(i)
    return indices


def _artifact_for_step(artifacts: dict, index: int) -> dict:
    art = artifacts.get(str(index))
    if art is None:
        art = artifacts.get(index)
    return art if isinstance(art, dict) else {}


def _parse_and_build(html_bytes: bytes) -> tuple[ParsedPaper, list[ChunkDraft]]:
    parsed = parse_arxiv_html(html_bytes)
    return parsed, build_chunk_drafts(parsed)


def _append_numbered(
    dest: list[dict],
    packed: list[ChunkRecord],
    excerpts: list[str],
    n: int,
) -> int:
    for chunk, excerpt in zip(packed, excerpts):
        dest.append(
            {
                "chunk_id": chunk.chunk_id,
                "n": n,
                "arxiv_id": chunk.arxiv_id,
                "version": chunk.version,
                "title": chunk.title,
                "year": chunk.year,
                "url": chunk.url,
                "excerpt": excerpt,
            }
        )
        n += 1
    return n


def normalize_retrieve_hops(raw: list[str], *, cap: int | None = None) -> list[str]:
    limit = Policy.retrieve_hop_cap if cap is None else cap
    hops: list[str] = []
    seen: set[str] = set()
    for item in raw:
        hop = item.strip()
        if not hop or hop in seen:
            continue
        seen.add(hop)
        hops.append(hop)
        if len(hops) >= limit:
            break
    return hops


def fuse_hop_cuts(
    hop_cuts: list[list[ChunkRecord]],
    *,
    pack_cap: int = 10,
    rrf_k: int = 60,
) -> list[ChunkRecord]:
    packed: list[ChunkRecord] = []
    seen: set[str] = set()
    hop_taken: list[int] = [0] * len(hop_cuts)

    def take(chunk: ChunkRecord, hop_i: int | None) -> None:
        if chunk.chunk_id in seen or len(packed) >= pack_cap:
            return
        seen.add(chunk.chunk_id)
        packed.append(chunk)
        if hop_i is not None:
            hop_taken[hop_i] += 1

    for hop_i, cut in enumerate(hop_cuts):
        for chunk in cut:
            if chunk.chunk_id not in seen:
                take(chunk, hop_i)
                break

    if len(packed) < pack_cap:
        candidates: dict[str, tuple[ChunkRecord, float, int]] = {}
        for hop_i, cut in enumerate(hop_cuts):
            if hop_taken[hop_i] >= 2:
                continue
            for rank, chunk in enumerate(cut, start=1):
                if chunk.chunk_id in seen:
                    continue
                score = 1.0 / (rrf_k + rank)
                prior = candidates.get(chunk.chunk_id)
                if prior is None:
                    candidates[chunk.chunk_id] = (chunk, score, hop_i)
                else:
                    candidates[chunk.chunk_id] = (
                        chunk,
                        prior[1] + score,
                        prior[2],
                    )
                break
        ordered = sorted(
            candidates.values(),
            key=lambda item: (-item[1], item[0].chunk_id),
        )
        for chunk, _score, hop_i in ordered:
            if len(packed) >= pack_cap:
                break
            if hop_taken[hop_i] >= 2:
                continue
            take(chunk, hop_i)

    if len(packed) < pack_cap:
        leftover: dict[str, float] = {}
        leftover_chunks: dict[str, ChunkRecord] = {}
        for cut in hop_cuts:
            for rank, chunk in enumerate(cut, start=1):
                if chunk.chunk_id in seen:
                    continue
                leftover[chunk.chunk_id] = leftover.get(chunk.chunk_id, 0.0) + (
                    1.0 / (rrf_k + rank)
                )
                leftover_chunks[chunk.chunk_id] = chunk
        for cid in sorted(leftover, key=lambda key: (-leftover[key], key)):
            if len(packed) >= pack_cap:
                break
            take(leftover_chunks[cid], None)

    return packed


def union_retry_evidence(
    first_pack: list[dict],
    retry_numbered: list[dict],
    *,
    add_cap: int,
    pack_cap: int,
) -> list[dict]:
    pinned = [dict(row) for row in first_pack]
    seen = {str(row.get("chunk_id") or "") for row in pinned}
    seen.discard("")
    added = 0
    n = len(pinned) + 1
    for row in retry_numbered:
        if added >= add_cap or len(pinned) >= pack_cap:
            break
        cid = str(row.get("chunk_id") or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        extra = dict(row)
        extra["n"] = n
        pinned.append(extra)
        n += 1
        added += 1
    return pinned


class RetrieveRunner:
    def __init__(
        self,
        papers: PaperPort,
        chunks: ChunkRepository,
        embeddings: EmbeddingPort,
        hybrid: HybridRetrievePort,
        api_key: str | None = None,
        *,
        voyage_api_key: str,
    ) -> None:
        self._papers = papers
        self._chunks = chunks
        self._embeddings = embeddings
        self._hybrid = hybrid
        self._voyage_api_key = voyage_api_key
        kwargs: dict = {"model": REGISTRY["retrieve"].model}
        if api_key is not None:
            kwargs["api_key"] = api_key
        self._formulate = ChatOpenAI(**kwargs).with_structured_output(
            FormulatedRetrieveQuery, method="json_schema"
        )

    async def run(self, state: dict) -> dict:
        retrieve_index = _step_index(state)
        step = _current_step(state)
        task = str(step.get("task") or "")
        feedback = step_eval_feedback(state, retrieve_index)
        previous_query = str(state.get("retrieve_query_used") or "").strip()

        retry = _retry_count(state, retrieve_index)
        is_retry = retry > 0
        passed_search_indices = _passed_search_indices(state)

        newly_admitted: list[dict] = []
        gap_step_indices: list[int] = []
        gap_tasks: list[str] = []
        walked = False
        any_miss = False
        skip_walk = True
        plan = state.get("plan") or []
        if not isinstance(plan, list):
            plan = []

        if retry > 0:
            skip_walk = True
            merged = _unique_refs(state.get("papers") or [], limit=Policy.max_papers)
            walked = False
        elif not passed_search_indices:
            skip_walk = True
            merged = _unique_refs(state.get("papers") or [], limit=Policy.max_papers)
            walked = False
        else:
            skip_walk = False
            walked = True
            usable = _unique_refs(state.get("papers") or [], limit=Policy.max_papers)
            usable_keys = {(p["arxiv_id"], p["version"]) for p in usable}
            artifacts = state.get("search_artifacts") or {}
            if not isinstance(artifacts, dict):
                artifacts = {}
            for i in passed_search_indices:
                art = _artifact_for_step(artifacts, i)
                ranked = art.get("ranked_keys") or []
                if not isinstance(ranked, list):
                    ranked = []
                hits = art.get("hits") or []
                if not isinstance(hits, list):
                    hits = []
                admitted_one = False
                for key in ranked:
                    if not isinstance(key, dict):
                        continue
                    aid = key.get("arxiv_id")
                    if not aid:
                        continue
                    ver = str(key.get("version") or "")
                    if (aid, ver) in usable_keys:
                        continue
                    if await self._chunks.paper_has_chunks(aid, ver):
                        record = await self._chunks.get_paper(aid, ver)
                        ref = (
                            _paper_ref_from_record(record)
                            if record is not None
                            else _paper_ref_from_hit(key, hits)
                        )
                    else:
                        any_miss = True
                        html = await self._papers.load_html(aid, ver)
                        if html.status != "ok" or not html.body:
                            continue
                        parsed, drafts = await asyncio.to_thread(
                            _parse_and_build, html.body
                        )
                        if not parsed.usable or not drafts:
                            continue
                        vectors = await self._embeddings.embed_documents(
                            [draft.embedding_text for draft in drafts]
                        )
                        ref = _paper_ref_from_hit(key, hits)
                        await self._chunks.upsert_paper_with_chunks(
                            _paper_record_from_ref(ref), drafts, vectors
                        )
                    usable.append(ref)
                    usable_keys.add((aid, ver))
                    newly_admitted.append(ref)
                    admitted_one = True
                    break
                if not admitted_one:
                    gap_step_indices.append(i)
                    if 0 <= i < len(plan) and isinstance(plan[i], dict):
                        gap_task = str(plan[i].get("task") or "").strip()
                        if gap_task:
                            gap_tasks.append(gap_task)
            merged = merge_papers(state.get("papers") or [], newly_admitted)

        ingest = {
            "gap_step_indices": gap_step_indices,
            "gap_tasks": gap_tasks,
            "walked": walked,
        }
        holes = merge_hole_tasks(
            state.get("hole_tasks"),
            [{"task": task, "reason": "gap"} for task in gap_tasks],
        )
        if not merged:
            result = {
                "evidence_chunks": [],
                "retrieve_query_used": "",
                "last_agent": "retrieve",
                "retrieve_ingest": {**ingest, "case": "t1"},
                "hole_tasks": holes,
                "pgvector": "miss" if any_miss else "hit",
            }
            if not skip_walk and newly_admitted:
                result["papers"] = newly_admitted
            return result

        formulated = await self._formulate_retrieve(
            task,
            feedback=feedback,
            previous_query=previous_query,
            is_retry=is_retry,
            student_query=str(state.get("query") or ""),
        )
        hops = normalize_retrieve_hops(list(formulated.hops))
        query = formulated.query
        use_multi = (not is_retry) and len(hops) >= 2
        hybrid_query = feedback.strip() if is_retry else query
        rerank_query = (
            build_rerank_query("", feedback)
            if is_retry
            else build_rerank_query(task, feedback)
        )
        first_stage_k = (
            Policy.retrieve_retry_first_stage_k
            if is_retry
            else Policy.retrieve_first_stage_k
        )
        top_n = (
            Policy.retrieve_retry_add_cap
            if is_retry
            else Policy.retrieve_rerank_top_n
        )
        if use_multi:
            numbered = await self._multi_first_pass(merged, hops)
            hybrid_query = " ".join(hops)
        else:
            numbered = await self._one_facet_pass(
                merged,
                hybrid_query=hybrid_query,
                rerank_query=rerank_query,
                first_stage_k=first_stage_k,
                top_n=top_n,
            )

        if is_retry:
            numbered = union_retry_evidence(
                list(state.get("evidence_chunks") or []),
                numbered,
                add_cap=Policy.retrieve_retry_add_cap,
                pack_cap=Policy.retrieve_pack_cap_after_retry,
            )

        if walked and gap_step_indices:
            case = "t2a"
        else:
            case = "t3"

        result = {
            "evidence_chunks": numbered,
            "retrieve_query_used": hybrid_query,
            "last_agent": "retrieve",
            "pgvector": "miss" if any_miss else "hit",
            "retrieve_ingest": {**ingest, "case": case},
            "hole_tasks": holes,
        }
        if not skip_walk and newly_admitted:
            result["papers"] = newly_admitted
        return result

    async def _one_facet_pass(
        self,
        merged: list[dict],
        *,
        hybrid_query: str,
        rerank_query: str,
        first_stage_k: int,
        top_n: int,
    ) -> list[dict]:
        per_paper: list[HybridResult] = []
        for paper in merged:
            if not isinstance(paper, dict):
                continue
            per_paper.append(
                await self._hybrid.retrieve(
                    hybrid_query,
                    [(paper["arxiv_id"], paper["version"])],
                    k=first_stage_k,
                )
            )

        unique: list[ChunkRecord] = []
        seen_ids: set[str] = set()
        for result_i in per_paper:
            for chunk in result_i.ranked:
                if chunk.chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk.chunk_id)
                unique.append(chunk)

        numbered: list[dict] = []
        if not unique:
            return numbered
        async with trace(
            "rerank",
            run_type="chain",
            inputs={
                "query": rerank_query,
                "n_docs": len(unique),
                "model": RERANK_MODEL_ID,
                "chunks": chunks_for_trace(unique),
            },
            tags=["rerank"],
            metadata={"model": RERANK_MODEL_ID},
        ) as rerank_run:
            strategy = "voyage"
            error_type: str | None = None
            error_msg: str | None = None
            by_id: dict[str, float] = {}
            packed_chunks: list[ChunkRecord] = []
            n = 1
            try:
                scores = await asyncio.to_thread(
                    score_chunks,
                    unique,
                    rerank_query,
                    api_key=self._voyage_api_key,
                )
                chunk_ids = [chunk.chunk_id for chunk in unique]
                by_id = dict(zip(chunk_ids, scores))
            except Exception as exc:
                logger.exception("voyage rerank failed; packing ensemble order")
                strategy = "ensemble_order"
                error_type = type(exc).__name__
                error_msg = str(exc)
                for result_i in per_paper:
                    packed = pack_hits(result_i.ranked, k=top_n)
                    if not packed:
                        continue
                    packed_chunks.extend(packed)
                    excerpts = expand_hits(packed, result_i.corpus)
                    n = _append_numbered(numbered, packed, excerpts, n)
            else:
                for result_i in per_paper:
                    pairs = [
                        (chunk, by_id[chunk.chunk_id])
                        for chunk in result_i.ranked
                    ]
                    pairs.sort(key=lambda item: item[1], reverse=True)
                    cut = cut_reranked(
                        pairs,
                        top_n=top_n,
                        margin=Policy.retrieve_rerank_margin,
                        floor=Policy.retrieve_rerank_floor,
                    )
                    packed = pack_hits(cut, k=len(cut))
                    if not packed:
                        continue
                    packed_chunks.extend(packed)
                    excerpts = expand_hits(packed, result_i.corpus)
                    n = _append_numbered(numbered, packed, excerpts, n)
            score_map = by_id or None
            outputs: dict = {
                "strategy": strategy,
                "n_packed": n - 1,
                "chunks": chunks_for_trace(packed_chunks, scores=score_map),
            }
            if by_id:
                scored = sorted(
                    unique,
                    key=lambda chunk: by_id[chunk.chunk_id],
                    reverse=True,
                )
                outputs["chunks_scored"] = chunks_for_trace(scored, scores=by_id)
            if error_type is not None:
                outputs["error_type"] = error_type
                outputs["error"] = error_msg
            rerank_run.end(outputs=outputs)
        return numbered

    async def _hop_leg(
        self, paper: dict, hop: str
    ) -> tuple[HybridResult | None, list[ChunkRecord]]:
        try:
            result = await self._hybrid.retrieve(
                hop,
                [(paper["arxiv_id"], paper["version"])],
                k=Policy.retrieve_first_stage_k,
            )
        except Exception as exc:
            logger.warning("hop hybrid failed; 0 slots (%s)", exc)
            return None, []
        if not result.ranked:
            return result, []
        prefix = result.ranked[: Policy.retrieve_hop_voyage_docs]
        try:
            scores = await asyncio.to_thread(
                score_chunks,
                prefix,
                hop,
                api_key=self._voyage_api_key,
            )
        except Exception as exc:
            logger.warning("hop voyage failed; 0 slots (%s)", exc)
            return result, []
        pairs = list(zip(prefix, scores))
        pairs.sort(key=lambda item: item[1], reverse=True)
        cut = cut_reranked(
            pairs,
            top_n=Policy.retrieve_hop_voyage_docs,
            margin=Policy.retrieve_rerank_margin,
            floor=Policy.retrieve_rerank_floor,
        )
        return result, cut

    async def _multi_first_pass(
        self, merged: list[dict], hops: list[str]
    ) -> list[dict]:
        numbered: list[dict] = []
        n = 1
        packed_chunks: list[ChunkRecord] = []
        async with trace(
            "rerank",
            run_type="chain",
            inputs={
                "query": " ".join(hops),
                "hop_count": len(hops),
                "used_hops": True,
                "hops": hops,
                "model": RERANK_MODEL_ID,
            },
            tags=["rerank"],
            metadata={
                "model": RERANK_MODEL_ID,
                "hop_count": len(hops),
                "used_hops": True,
            },
        ) as rerank_run:
            for paper in merged:
                if not isinstance(paper, dict):
                    continue
                legs = await asyncio.gather(
                    *[self._hop_leg(paper, hop) for hop in hops]
                )
                cuts: list[list[ChunkRecord]] = []
                corpus: list[ChunkRecord] = []
                seen_corpus: set[str] = set()
                for result_i, cut in legs:
                    cuts.append(cut)
                    if result_i is None:
                        continue
                    for chunk in result_i.corpus:
                        if chunk.chunk_id in seen_corpus:
                            continue
                        seen_corpus.add(chunk.chunk_id)
                        corpus.append(chunk)
                fused = fuse_hop_cuts(
                    cuts,
                    pack_cap=Policy.retrieve_rerank_top_n,
                    rrf_k=Policy.retrieve_hop_rrf_k,
                )
                packed = pack_hits(fused, k=len(fused))
                if not packed:
                    continue
                packed_chunks.extend(packed)
                excerpts = expand_hits(packed, corpus)
                n = _append_numbered(numbered, packed, excerpts, n)
            rerank_run.end(
                outputs={
                    "strategy": "voyage_hops",
                    "n_packed": n - 1,
                    "hop_count": len(hops),
                    "chunks": chunks_for_trace(packed_chunks),
                }
            )
        return numbered

    async def _formulate_retrieve(
        self,
        task: str,
        *,
        feedback: str,
        previous_query: str,
        is_retry: bool = False,
        student_query: str = "",
    ) -> FormulatedRetrieveQuery:
        human = (
            formulate_retry_human(
                feedback=feedback, previous_query=previous_query
            )
            if is_retry
            else formulate_human(
                task=task,
                feedback=feedback,
                previous_query=previous_query,
                student_query=student_query,
            )
        )
        formulated = await self._formulate.ainvoke(
            [
                ("system", _FORMULATE_SYSTEM),
                (
                    "human",
                    human,
                ),
            ]
        )
        if not isinstance(formulated, FormulatedRetrieveQuery):
            payload = (
                formulated.model_dump()
                if hasattr(formulated, "model_dump")
                else formulated
            )
            formulated = FormulatedRetrieveQuery.model_validate(payload)
        query = formulated.query.strip() or task
        return FormulatedRetrieveQuery(query=query, hops=list(formulated.hops))
