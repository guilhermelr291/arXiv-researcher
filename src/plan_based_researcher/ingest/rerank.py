"""Voyage rerank-3 scoring, index mapping, and adaptive relevance-score cut."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import voyageai

from plan_based_researcher.ports.chunks import ChunkRecord

RERANK_MODEL_ID = "rerank-3"
RERANK_TIMEOUT_SECONDS = 30.0

__all__ = [
    "RERANK_MODEL_ID",
    "RERANK_TIMEOUT_SECONDS",
    "build_rerank_query",
    "cut_reranked",
    "document_text",
    "score_chunks",
    "scores_from_rerank_results",
]


def build_rerank_query(task: str, feedback: str) -> str:
    """Task, plus this step's eval feedback on retry. Not FormulatedQuery."""
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


def score_chunks(chunks: list[ChunkRecord], query: str, *, api_key: str) -> list[float]:
    """One Client.rerank call. Returns one relevance_score per chunk, same order.

    Raises on HTTP/SDK failure or incomplete index coverage.
    """
    if not chunks:
        return []
    ranking = voyageai.Client(
        api_key=api_key,
        timeout=RERANK_TIMEOUT_SECONDS,
        max_retries=0,
    ).rerank(
        query,
        [document_text(c) for c in chunks],
        model=RERANK_MODEL_ID,
        truncation=True,
    )
    return scores_from_rerank_results(len(chunks), ranking.results)
