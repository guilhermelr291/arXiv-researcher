"""Map LangSmith-like Writer execute runs to RAGAS triples (WSTR-07)."""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "WriterTriple",
    "excerpts_from_evidence_chunks",
    "map_execute_run",
    "unwrap_node_payload",
]

_GRAPH_STATE_KEYS = frozenset(
    {
        "query",
        "writer_markdown",
        "evidence_chunks",
        "messages",
        "citations",
        "papers",
        "plan",
        "last_agent",
        "outcome",
        "hole_tasks",
        "retrieve_ingest",
        "retrieve_query_used",
        "eval_next",
        "gate",
    }
)

_RERANK_RUN_NAMES = frozenset({"rerank", "voyage_rerank"})


class WriterTriple(TypedDict):
    user_input: str
    retrieved_contexts: list[str]
    response: str
    run_id: str | None


def unwrap_node_payload(payload: object) -> dict:
    """Return a GraphState-like dict, unwrapping one LangGraph node wrapper."""
    if not isinstance(payload, dict):
        return {}
    if _GRAPH_STATE_KEYS.intersection(payload.keys()):
        return payload
    if len(payload) == 1:
        (value,) = payload.values()
        if isinstance(value, dict):
            return value
    return payload


def excerpts_from_evidence_chunks(chunks: object) -> list[str] | None:
    """Writer-prompt excerpts in list order, or None if chunks is missing/not a list."""
    if not isinstance(chunks, list):
        return None
    excerpts: list[str] = []
    for item in chunks:
        if not isinstance(item, dict):
            continue
        excerpt = item.get("excerpt")
        if isinstance(excerpt, str):
            excerpts.append(excerpt)
    return excerpts


def _nonempty_str(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _message_content(item: object) -> str | None:
    if isinstance(item, dict):
        return _nonempty_str(item.get("content"))
    content = getattr(item, "content", None)
    return _nonempty_str(content)


def _query_from_inputs(inputs: dict) -> str | None:
    query = _nonempty_str(inputs.get("query"))
    if query is not None:
        return query
    messages = inputs.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    return _message_content(messages[0])


def _run_id(run: object) -> str | None:
    value = getattr(run, "id", None)
    if value is None:
        return None
    return str(value)


def _trace_id(run: object) -> str | None:
    value = getattr(run, "trace_id", None)
    if value is None:
        return None
    return str(value)


def _contexts_from_run(
    inputs: dict,
    run: object,
    retrieve_chunks_by_trace: dict[str, list[str]] | None,
) -> list[str] | None:
    if "evidence_chunks" in inputs:
        return excerpts_from_evidence_chunks(inputs.get("evidence_chunks"))
    if not retrieve_chunks_by_trace:
        return None
    trace_id = _trace_id(run)
    if trace_id is None:
        return None
    fallback = retrieve_chunks_by_trace.get(trace_id)
    if not isinstance(fallback, list):
        return None
    return fallback


def map_execute_run(
    run: object,
    *,
    retrieve_chunks_by_trace: dict[str, list[str]] | None = None,
) -> WriterTriple | None:
    """Build a Writer triple from an execute run, or None to skip."""
    name = getattr(run, "name", None)
    if name in _RERANK_RUN_NAMES:
        return None

    outputs = unwrap_node_payload(getattr(run, "outputs", None))
    markdown = _nonempty_str(outputs.get("writer_markdown"))
    if markdown is None:
        return None

    inputs = unwrap_node_payload(getattr(run, "inputs", None))
    query = _query_from_inputs(inputs)
    if query is None:
        return None

    excerpts = _contexts_from_run(inputs, run, retrieve_chunks_by_trace)
    if not excerpts:
        return None

    return WriterTriple(
        user_input=query,
        retrieved_contexts=excerpts,
        response=markdown,
        run_id=_run_id(run),
    )
