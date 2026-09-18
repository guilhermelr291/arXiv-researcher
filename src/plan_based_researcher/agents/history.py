"""Trim conversation transcripts for gate, planner, and Writer prompts."""

from __future__ import annotations

from plan_based_researcher.policy import Policy

__all__ = [
    "format_transcript",
    "last_exchanges",
    "message_content",
    "message_role",
    "prior_citation_chunks",
]


def message_role(item: object) -> str:
    if isinstance(item, dict):
        role = item.get("role") or item.get("type") or ""
    else:
        role = getattr(item, "type", None) or getattr(item, "role", None) or ""
    text = str(role)
    if text in ("human", "user"):
        return "user"
    if text in ("ai", "assistant"):
        return "assistant"
    return text


def message_content(item: object) -> str:
    if isinstance(item, dict):
        content = item.get("content")
    else:
        content = getattr(item, "content", None)
    if content is None:
        return ""
    return str(content)


def message_id(item: object) -> str:
    if isinstance(item, dict):
        value = item.get("id")
    else:
        value = getattr(item, "id", None)
    return str(value) if value else ""


def last_exchanges(messages: object, n_exchanges: int) -> list:
    if not isinstance(messages, list) or n_exchanges <= 0:
        return []
    window = n_exchanges * 2
    return list(messages[-window:])


def format_transcript(messages: object) -> str:
    lines: list[str] = []
    if not isinstance(messages, list):
        return ""
    for item in messages:
        role = message_role(item)
        content = message_content(item)
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _citations_of(item: object) -> list[dict]:
    if isinstance(item, dict):
        metadata = item.get("response_metadata") or item.get("additional_kwargs") or {}
    else:
        metadata = getattr(item, "response_metadata", None) or {}
    if not isinstance(metadata, dict):
        return []
    citations = metadata.get("citations") or []
    return [c for c in citations if isinstance(c, dict)]


def prior_citation_chunks(state: dict, *, n_exchanges: int | None = None) -> list[dict]:
    """Renumber citations from the last Writer turns, first chunk_id wins."""
    window = (
        Policy.writer_history_exchanges if n_exchanges is None else n_exchanges
    )
    messages = last_exchanges(state.get("messages") or [], window)
    seen: set[str] = set()
    chunks: list[dict] = []
    for item in messages:
        if message_role(item) != "assistant":
            continue
        for citation in _citations_of(item):
            chunk_id = str(citation.get("chunk_id") or "")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            n = len(chunks) + 1
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "n": n,
                    "arxiv_id": str(citation.get("arxiv_id") or ""),
                    "version": str(citation.get("version") or ""),
                    "title": str(citation.get("title") or ""),
                    "year": int(citation.get("year") or 0),
                    "url": str(citation.get("url") or ""),
                    "excerpt": str(citation.get("excerpt") or ""),
                }
            )
    return chunks
