"""Finalize node: persist the turn on messages, then emit terminal custom events."""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from plan_based_researcher.graph.project import project_turn
from plan_based_researcher.graph.state import GraphState

__all__ = ["make_finalize_node"]


def _reason(state: GraphState, outcome: str) -> str:
    if outcome == "refused":
        return str((state.get("gate") or {}).get("reason") or "")
    if outcome == "insufficient":
        return str(
            (state.get("last_eval") or {}).get("feedback") or "insufficient evidence"
        )
    if outcome == "error":
        return str(state.get("error_message") or "research failed")
    return ""


def make_finalize_node():
    async def finalize(state: GraphState) -> dict:
        writer = get_stream_writer()
        outcome = state.get("outcome") or "error"
        reason = _reason(state, outcome)
        projection = project_turn(state)
        if outcome == "done":
            content = str(state.get("writer_markdown") or "")
            writer({"event": "done", "data": {"outcome": "done"}})
        elif outcome == "refused":
            content = reason
            writer({
                "event": "done",
                "data": {"outcome": "refused", "reason": reason},
            })
        elif outcome == "insufficient":
            content = reason
            writer({"event": "insufficient", "data": {"reason": reason}})
        else:
            content = reason
            writer({
                "event": "error",
                "data": {"message": state.get("error_message") or "research failed"},
            })
        message_id = str(state.get("writer_message_id") or "")
        kwargs: dict = {
            "content": content,
            "response_metadata": projection,
        }
        if message_id:
            kwargs["id"] = message_id
        return {"messages": [AIMessage(**kwargs)]}

    return finalize
