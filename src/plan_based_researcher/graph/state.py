"""LangGraph state schema and reducers (THR-01, ARX-04, LOOP-01, SEARCH-01, REPLAN-01, CAP-02, ADM-03, RETR-04)."""

from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages

from plan_based_researcher.policy import Policy

__all__ = [
    "EvidenceChunk",
    "GraphState",
    "PaperRef",
    "RankedKey",
    "RetrieveIngestReport",
    "SearchArtifact",
    "SearchHit",
    "last_write",
    "merge_eval_by_step",
    "merge_hole_tasks",
    "merge_papers",
    "merge_search_artifacts",
]


class PaperRef(TypedDict):
    arxiv_id: str
    version: str
    title: str
    year: int
    url: str
    categories: list[str]


class SearchHit(TypedDict):
    arxiv_id: str
    version: str
    title: str
    year: int
    url: str
    categories: list[str]
    abstract: str


class RankedKey(TypedDict):
    arxiv_id: str
    version: str


class SearchArtifact(TypedDict):
    step_index: int
    query_used: str
    hits: list[SearchHit]
    ranked_keys: NotRequired[list[RankedKey]]


class RetrieveIngestReport(TypedDict):
    case: Literal["t1", "t2a", "t3"]
    gap_step_indices: list[int]
    gap_tasks: NotRequired[list[str]]
    walked: bool


class EvidenceChunk(TypedDict):
    chunk_id: str
    n: int
    arxiv_id: str
    version: str
    title: str
    year: int
    url: str
    excerpt: str


def last_write(existing: str | None, new: str | None) -> str:
    """Last write wins so parallel Send workers can set the same scalar."""
    if new is not None:
        return new
    return existing or ""


def merge_papers(
    existing: list[PaperRef] | None,
    new: list[PaperRef] | None,
) -> list[PaperRef]:
    """Union papers by (arxiv_id, version), last write wins, trim to Policy.max_papers."""
    merged: dict[tuple[str, str], PaperRef] = {}
    for paper in (existing or []) + (new or []):
        merged[(paper["arxiv_id"], paper["version"])] = paper
    return list(merged.values())[: Policy.max_papers]


def _merge_or_clear(existing: dict | None, new: dict | None) -> dict:
    """Merge by key, last write wins. An empty dict clears (new-turn reset)."""
    if new is None:
        return dict(existing or {})
    if not new:
        return {}
    return {**(existing or {}), **new}


def merge_search_artifacts(
    existing: dict[str, SearchArtifact] | None,
    new: dict[str, SearchArtifact] | None,
) -> dict[str, SearchArtifact]:
    """Merge search artifacts by step key, last write wins.

    Empty `new` clears the map so `initial_graph_state` resets scratchpads
    between turns. Omit the key to leave the checkpoint unchanged. Non-empty
    patches still merge for parallel `Send` and remaining replan.
    """
    return _merge_or_clear(existing, new)


def merge_eval_by_step(
    existing: dict[str, dict] | None,
    new: dict[str, dict] | None,
) -> dict[str, dict]:
    """Merge per-step eval records by step key, last write wins (LOOP-02).

    Empty `new` clears, same contract as `merge_search_artifacts`.
    """
    return _merge_or_clear(existing, new)


def merge_hole_tasks(existing: object, extras: list | None = None) -> list[dict]:
    """Dedupe hole rows by task text; keep first reason (WRITE-02)."""
    result: list[dict] = []
    seen: set[str] = set()
    sequences: list = []
    if isinstance(existing, list):
        sequences.append(existing)
    if extras:
        sequences.append(extras)
    for source in sequences:
        for item in source:
            if not isinstance(item, dict):
                continue
            task = str(item.get("task") or "").strip()
            if not task or task in seen:
                continue
            reason = str(item.get("reason") or "gap")
            if reason not in ("unpassed", "gap"):
                reason = "gap"
            seen.add(task)
            result.append({"task": task, "reason": reason})
    return result


class GraphState(TypedDict):
    query: str
    messages: Annotated[list, add_messages]
    papers: Annotated[list[PaperRef], merge_papers]
    plan: list[dict]
    step_index: int
    passed_steps: list[int]
    retry_counts: dict[str, int]
    retry_count: int
    replan_used: bool
    steps_executed: int
    search_artifacts: Annotated[dict[str, SearchArtifact], merge_search_artifacts]
    last_agent: Annotated[str, last_write]
    last_eval: dict
    eval_by_step: Annotated[dict[str, dict], merge_eval_by_step]
    retrieve_query_used: str
    retrieve_ingest: RetrieveIngestReport
    # hole_tasks survive remaining replan (task text, not plan index) for WRITE-02.
    hole_tasks: list[dict]
    evidence_chunks: list[EvidenceChunk]
    writer_markdown: str
    writer_message_id: str
    started_at_ms: int
    citations: list[dict]
    outcome: Literal["pending", "refused", "done", "insufficient", "error"]
    # SPEC_DEVIATION: eval_next is not in the design TypedDict.
    # Reason: LangGraph drops undeclared keys; evaluate→replan routing needs a channel.
    eval_next: Literal["dispatch", "replan", "finalize"]
    gate: dict
    error_message: str
    reuse_existing_papers: bool
    conversation_summary: NotRequired[str]
    applied_watermark: NotRequired[str]
