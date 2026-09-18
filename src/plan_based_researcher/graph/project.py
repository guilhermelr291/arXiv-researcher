"""Turn projection shared by finalize metadata and the AG-UI adapter."""

from __future__ import annotations

import time

from plan_based_researcher.graph.state import GraphState

__all__ = ["project_turn"]

_STATUS = {
    "pass": "passed",
    "passed": "passed",
    "retry": "retry",
    "fail": "replan",
    "replan": "replan",
}


def _eval_record(state: GraphState, index: int) -> dict:
    by_step = state.get("eval_by_step") or {}
    if not isinstance(by_step, dict):
        return {}
    rec = by_step.get(str(index))
    if rec is None:
        rec = by_step.get(index)
    return rec if isinstance(rec, dict) else {}


def _item_status(state: GraphState, index: int) -> str:
    passed = set()
    for item in state.get("passed_steps") or []:
        try:
            passed.add(int(item))
        except (TypeError, ValueError):
            continue
    if index in passed:
        return "passed"
    rec = _eval_record(state, index)
    mapped = _STATUS.get(str(rec.get("status") or ""))
    return mapped or "pending"


def _plan_items(state: GraphState) -> list[dict]:
    plan = state.get("plan") or []
    if not isinstance(plan, list):
        return []
    items: list[dict] = []
    for index, step in enumerate(plan):
        if not isinstance(step, dict):
            step = {}
        rec = _eval_record(state, index)
        items.append(
            {
                "index": index,
                "agent": step.get("agent") or "",
                "task": step.get("task") or "",
                "status": _item_status(state, index),
                "feedback": rec.get("feedback"),
            }
        )
    return items


def _elapsed_ms(state: GraphState) -> int:
    started = state.get("started_at_ms") or 0
    try:
        started_i = int(started)
    except (TypeError, ValueError):
        started_i = 0
    if started_i <= 0:
        return 0
    now = int(time.time() * 1000)
    return max(0, now - started_i)


def project_turn(state: GraphState) -> dict:
    outcome = state.get("outcome") or "error"
    citations = state.get("citations") or []
    if not isinstance(citations, list):
        citations = []
    return {
        "outcome": outcome,
        "gate": state.get("gate") or {},
        "plan": _plan_items(state),
        "steps": {
            "count": int(state.get("steps_executed") or 0),
            "elapsed_ms": _elapsed_ms(state),
        },
        "citations": citations,
    }
