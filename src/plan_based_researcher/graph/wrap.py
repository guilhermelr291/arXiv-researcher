"""Compile-time node wrapper: emit node_start / node_end without editing nodes."""

from __future__ import annotations

import inspect

from langgraph.config import get_stream_writer

__all__ = ["wrap_node"]


def _step_meta(name: str, state: dict) -> dict:
    if name not in ("search", "execute"):
        return {}
    plan = state.get("plan") or []
    try:
        idx = int(state.get("step_index") or 0)
    except (TypeError, ValueError):
        idx = 0
    step = plan[idx] if isinstance(plan, list) and 0 <= idx < len(plan) else {}
    if not isinstance(step, dict):
        step = {}
    return {
        "step_index": idx,
        "agent": step.get("agent") or name,
        "task": step.get("task") or "",
    }


def wrap_node(name: str, fn):
    async def wrapped(state):
        meta = _step_meta(name, state)
        try:
            get_stream_writer()({"event": "node_start", "data": {"node": name, **meta}})
        except RuntimeError:
            pass
        result = fn(state)
        if inspect.isawaitable(result):
            result = await result
        try:
            get_stream_writer()({"event": "node_end", "data": {"node": name, **meta}})
        except RuntimeError:
            pass
        return result

    wrapped.__name__ = getattr(fn, "__name__", name)
    wrapped.__wrapped__ = fn
    return wrapped
