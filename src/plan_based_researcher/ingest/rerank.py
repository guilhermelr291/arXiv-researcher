"""Voyage rerank-3 scoring, index mapping, and adaptive relevance-score cut."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any

from langchain_core.documents import Document
from langchain_voyageai import VoyageAIRerank
from langsmith import traceable

from plan_based_researcher.ports.chunks import ChunkRecord

RERANK_MODEL_ID = "rerank-3"

__all__ = [
    "RERANK_MODEL_ID",
    "build_rerank_query",
    "chunks_for_trace",
    "cut_reranked",
    "document_text",
    "score_chunks",
    "scores_from_rerank_results",
]


def build_rerank_query(task: str, feedback: str) -> str:
    """English retrieve task, plus this step's English eval feedback on retry.

    Not FormulatedQuery. Planner/eval emit English even when the student query
    is another language (LANG-05).
    """
    task = task.strip()
    feedback = feedback.strip()
    if feedback:
        return f"{task}\n\n{feedback}"
    return task


def document_text(chunk: ChunkRecord) -> str:
    """metadata.section + newline + content, or content if section is empty."""
    section = (chunk.metadata.get("section") or "").strip()
    if section:
        return f"{section}\n{chunk.content}"
    return chunk.content


def cut_reranked(
    ranked: list[tuple[ChunkRecord, float]],
    *,
    top_n: int = 12,
    margin: float = 0.20,
    floor: float | None = 0.30,
) -> list[ChunkRecord]:
    """Keep a prefix of *ranked* (already sorted by Voyage relevance_score descending).

    Scores are Voyage relevance scores (~0–1), not logits. The cut is relative
    to the best score of this query's candidate list, except the optional
    absolute floor on that list's best.
    """
    if not ranked:
        return []
    best = ranked[0][1]
    if floor is not None and best < floor:
        return []
    kept: list[ChunkRecord] = []
    for chunk, score in ranked:
        if (best - score) > margin:
            break
        kept.append(chunk)
        if len(kept) == top_n:
            break
    return kept


def scores_from_rerank_results(n_docs: int, results: Sequence[Any]) -> list[float]:
    """Map Voyage results (sorted by score; each has .index and .relevance_score)
    back to the input document order. Raise if a slot is missing or duplicated."""
    scores: list[float | None] = [None] * n_docs
    for result in results:
        idx = int(result.index)
        if idx < 0 or idx >= n_docs or scores[idx] is not None:
            raise ValueError("rerank result index missing, duplicated, or out of range")
        scores[idx] = float(result.relevance_score)
    mapped: list[float] = []
    for score in scores:
        if score is None:
            raise ValueError("rerank result index missing, duplicated, or out of range")
        mapped.append(score)
    return mapped


_TRACE_PREVIEW_CHARS = 240


def chunks_for_trace(
    chunks: Sequence[Any],
    *,
    scores: Mapping[str, float] | None = None,
    preview_chars: int = _TRACE_PREVIEW_CHARS,
) -> list[dict]:
    """Serialize chunks for a LangSmith span: rank, ids, section, preview, optional score."""
    rows: list[dict] = []
    for i, chunk in enumerate(chunks):
        chunk_id = getattr(chunk, "chunk_id", None)
        metadata = getattr(chunk, "metadata", None)
        section = ""
        if isinstance(metadata, dict):
            section = (metadata.get("section") or "").strip()
        content = str(getattr(chunk, "content", "") or "").replace("\n", " ")
        if preview_chars >= 0 and len(content) > preview_chars:
            content = content[:preview_chars]
        row: dict[str, Any] = {
            "rank": i + 1,
            "chunk_id": chunk_id,
            "kind": getattr(chunk, "kind", None),
            "unit_id": getattr(chunk, "unit_id", None),
            "section": section,
            "arxiv_id": getattr(chunk, "arxiv_id", None),
            "version": getattr(chunk, "version", None),
            "content_preview": content,
        }
        if scores is not None and chunk_id is not None and chunk_id in scores:
            row["score"] = scores[chunk_id]
        rows.append(row)
    return rows


def _voyage_rerank_inputs(inputs: dict) -> dict:
    """Log query + chunks. Never send the Voyage API key to LangSmith."""
    raw = inputs.get("chunks") or []
    chunks = raw if isinstance(raw, list) else []
    return {
        "query": inputs.get("query"),
        "n_docs": len(chunks),
        "chunks": chunks_for_trace(chunks),
        "model": RERANK_MODEL_ID,
    }


def _voyage_rerank_outputs(outputs: object) -> dict:
    if not isinstance(outputs, list):
        return {"output": outputs}
    return {"n_scores": len(outputs), "scores": outputs}


@traceable(
    name="voyage_rerank",
    run_type="chain",
    process_inputs=_voyage_rerank_inputs,
    process_outputs=_voyage_rerank_outputs,
    metadata={"model": RERANK_MODEL_ID},
    tags=["rerank"],
)
def score_chunks(chunks: list[ChunkRecord], query: str, *, api_key: str) -> list[float]:
    """One VoyageAIRerank.compress_documents call. Returns one relevance_score per chunk, same order.

    Raises on HTTP/SDK failure or incomplete index coverage.
    """
    if not chunks:
        return []
    docs = [
        Document(page_content=document_text(c), metadata={"input_index": i})
        for i, c in enumerate(chunks)
    ]
    compressor = VoyageAIRerank(
        model=RERANK_MODEL_ID,
        api_key=api_key,
        top_k=len(docs),
        truncation=True,
    )
    compressed = compressor.compress_documents(docs, query)
    results = [
        SimpleNamespace(
            index=doc.metadata["input_index"],
            relevance_score=doc.metadata["relevance_score"],
        )
        for doc in compressed
    ]
    return scores_from_rerank_results(len(chunks), results)
