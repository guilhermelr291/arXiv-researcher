"""Dispatch node: interpret plan, Send search waves, else execute (LOOP-01, SEARCH-01, CAP-02)."""

from __future__ import annotations

from langgraph.types import Command, Send

from plan_based_researcher.graph.state import GraphState
from plan_based_researcher.policy import Policy

__all__ = ["make_dispatch_node", "search_wave_indices"]


def search_wave_indices(state: GraphState) -> list[int]:
    """Consecutive unpassed search indices from the first unpassed plan index."""
    plan = state.get("plan") or []
    passed = set(state.get("passed_steps") or [])
    first: int | None = None
    for i in range(len(plan)):
        if i not in passed:
            first = i
            break
    if first is None:
        return []
    wave: list[int] = []
    for i in range(first, len(plan)):
        if i in passed:
            break
        step = plan[i]
        agent = step.get("agent") if isinstance(step, dict) else None
        if agent != "search":
            break
        wave.append(i)
    return wave


def _first_unpassed_index(state: GraphState) -> int | None:
    plan = state.get("plan") or []
    passed = set(state.get("passed_steps") or [])
    for i in range(len(plan)):
        if i not in passed:
            return i
    return None


def _writer_has_passed(state: GraphState) -> bool:
    plan = state.get("plan") or []
    passed = set(state.get("passed_steps") or [])
    for i, step in enumerate(plan):
        if i not in passed or not isinstance(step, dict):
            continue
        if step.get("agent") == "writer":
            return True
    return False


def _insufficient() -> Command:
    return Command(update={"outcome": "insufficient"}, goto="finalize")


def make_dispatch_node(*, halt_before_writer: bool = False):
    async def dispatch(state: GraphState) -> Command:
        outcome = state.get("outcome") or "pending"
        if outcome != "pending":
            return Command(goto="finalize")

        steps_executed = state.get("steps_executed") or 0
        if steps_executed >= Policy.max_steps:
            return _insufficient()

        wave = search_wave_indices(state)
        if wave:
            if steps_executed + len(wave) > Policy.max_steps:
                return _insufficient()
            return Command(
                goto=[Send("search", {**state, "step_index": i}) for i in wave],
            )

        first = _first_unpassed_index(state)
        if first is None:
            if not _writer_has_passed(state):
                return _insufficient()
            return Command(goto="finalize")

        plan = state.get("plan") or []
        step = plan[first] if 0 <= first < len(plan) else {}
        if not isinstance(step, dict):
            step = {}
        agent = step.get("agent") or ""
        if halt_before_writer and agent == "writer":
            return Command(update={"outcome": "done"}, goto="finalize")
        if agent in ("retrieve", "writer"):
            return Command(update={"step_index": first}, goto="execute")
        return Command(
            update={
                "outcome": "error",
                "error_message": f"unknown agent: {agent!r}",
            },
            goto="finalize",
        )

    return dispatch
