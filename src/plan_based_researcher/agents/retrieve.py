"""Retrieve runner: ranking walk, ingest, per-paper hybrid chunks (RETR-02, RETR-03, RETR-04)."""

from __future__ import annotations

import asyncio
import logging

from langchain_openai import ChatOpenAI

from plan_based_researcher.adapters.hybrid import HybridResult, HybridRetrievePort
from plan_based_researcher.agents.query_schema import (
    FormulatedQuery,
    formulate_human,
    step_eval_feedback,
)
from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.graph.state import merge_hole_tasks, merge_papers
from plan_based_researcher.ingest.chunk_build import build_chunk_drafts
from plan_based_researcher.ingest.expand import expand_hits
from plan_based_researcher.ingest.html_parse import ParsedPaper, parse_arxiv_html
from plan_based_researcher.ingest.pack import pack_hits
from plan_based_researcher.ingest.rerank import (
    build_rerank_query,
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

__all__ = ["RetrieveRunner"]

logger = logging.getLogger(__name__)

_FORMULATE_SYSTEM = """\
You write a English retrieval query for hybrid search (vector + BM25) over \
chunks from papers already admitted for this thread. The runtime uses your query \
field as the retriever input. This is not an arXiv API search.

Rules:
- Put the query in the structured `query` field. Do not narrate.
- Always English keywords and phrases, even when the task is in another language.
- Write terms that should appear in paper chunks. Do not use arXiv syntax \
(ti:, abs:, AND, OR, ANDNOT, cat:).
- Do not copy the task prose as the query.
- When Previous query or Evaluator feedback is present, honor the feedback and \
emit a different query from Previous query.

Example:
- Task: Retrieve passages that explain how LoRA updates weights
  query: LoRA low-rank adaptation weight update adapter matrices
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
            FormulatedQuery, method="json_schema"
        )

    async def run(self, state: dict) -> dict:
        retrieve_index = _step_index(state)
        step = _current_step(state)
        task = str(step.get("task") or "")
        feedback = step_eval_feedback(state, retrieve_index)
        previous_query = str(state.get("retrieve_query_used") or "").strip()

        retry = _retry_count(state, retrieve_index)
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

        query = await self._formulate_query(
            task, feedback=feedback, previous_query=previous_query
        )
        rerank_query = build_rerank_query(task, feedback)
        per_paper: list[HybridResult] = []
        for paper in merged:
            if not isinstance(paper, dict):
                continue
            per_paper.append(
                await self._hybrid.retrieve(
                    query,
                    [(paper["arxiv_id"], paper["version"])],
                    k=Policy.retrieve_first_stage_k,
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
        if unique:
            try:
                scores = await asyncio.to_thread(
                    score_chunks, unique, rerank_query, api_key=self._voyage_api_key
                )
                chunk_ids = [chunk.chunk_id for chunk in unique]
                by_id = dict(zip(chunk_ids, scores))
            except Exception:
                logger.exception(
                    "voyage rerank failed; packing ensemble order"
                )
                n = 1
                for result_i in per_paper:
                    packed = pack_hits(
                        result_i.ranked, k=Policy.retrieve_rerank_top_n
                    )
                    if not packed:
                        continue
                    excerpts = expand_hits(packed, result_i.corpus)
                    n = _append_numbered(numbered, packed, excerpts, n)
            else:
                n = 1
                for result_i in per_paper:
                    pairs = [
                        (chunk, by_id[chunk.chunk_id])
                        for chunk in result_i.ranked
                    ]
                    pairs.sort(key=lambda item: item[1], reverse=True)
                    cut = cut_reranked(
                        pairs,
                        top_n=Policy.retrieve_rerank_top_n,
                        margin=Policy.retrieve_rerank_margin,
                        floor=Policy.retrieve_rerank_floor,
                    )
                    packed = pack_hits(cut, k=len(cut))
                    if not packed:
                        continue
                    excerpts = expand_hits(packed, result_i.corpus)
                    n = _append_numbered(numbered, packed, excerpts, n)

        if walked and gap_step_indices:
            case = "t2a"
        else:
            case = "t3"

        result = {
            "evidence_chunks": numbered,
            "retrieve_query_used": query,
            "last_agent": "retrieve",
            "pgvector": "miss" if any_miss else "hit",
            "retrieve_ingest": {**ingest, "case": case},
            "hole_tasks": holes,
        }
        if not skip_walk and newly_admitted:
            result["papers"] = newly_admitted
        return result

    async def _formulate_query(
        self,
        task: str,
        *,
        feedback: str,
        previous_query: str,
    ) -> str:
        formulated = await self._formulate.ainvoke(
            [
                ("system", _FORMULATE_SYSTEM),
                (
                    "human",
                    formulate_human(
                        task=task,
                        feedback=feedback,
                        previous_query=previous_query,
                    ),
                ),
            ]
        )
        if not isinstance(formulated, FormulatedQuery):
            formulated = FormulatedQuery.model_validate(formulated)
        query = formulated.query.strip()
        return query or task
