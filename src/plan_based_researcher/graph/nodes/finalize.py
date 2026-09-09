"""Finalize node: terminal SSE events after writer pass or halt (SSE-02, GROUND-02, CAP-01)."""

from __future__ import annotations

from langgraph.config import get_stream_writer

from plan_based_researcher.graph.state import GraphState

__all__ = ["make_finalize_node"]


def make_finalize_node():
    async def finalize(state: GraphState) -> dict:
        writer = get_stream_writer()
        outcome = state.get("outcome") or "error"
        if outcome == "done":
            writer({"event": "done", "data": {"outcome": "done"}})
        elif outcome == "refused":
            writer({
                "event": "done",
                "data": {
                    "outcome": "refused",
                    "reason": (state.get("gate") or {}).get("reason"),
                },
            })
        elif outcome == "insufficient":
            writer({
                "event": "insufficient",
                "data": {
                    "reason": (state.get("last_eval") or {}).get("feedback")
                    or "insufficient evidence",
                },
            })
        else:
            writer({
                "event": "error",
                "data": {"message": state.get("error_message") or "research failed"},
            })
        return {}

    return finalize
