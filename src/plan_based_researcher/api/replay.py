"""Replay checkpoint messages as AG-UI Message[] (messages channel only)."""

from __future__ import annotations

import uuid

from ag_ui.core import ActivityMessage, AssistantMessage, UserMessage

from plan_based_researcher.agents.history import message_content, message_id, message_role
from plan_based_researcher.graph.project import project_turn

__all__ = ["snapshot_status", "snapshot_to_agui_messages"]


def snapshot_status(next_nodes: object) -> str:
    if next_nodes:
        return "interrupted"
    return "idle"


def _metadata(item: object) -> dict:
    if isinstance(item, dict):
        meta = item.get("response_metadata") or {}
    else:
        meta = getattr(item, "response_metadata", None) or {}
    return meta if isinstance(meta, dict) else {}


def _activity(activity_type: str, content: dict, *, suffix: str) -> ActivityMessage:
    return ActivityMessage(
        id=suffix,
        role="activity",
        activity_type=activity_type,
        content=content,
    )


def snapshot_to_agui_messages(messages: object) -> list:
    out: list = []
    if not isinstance(messages, list):
        return out
    for index, item in enumerate(messages):
        role = message_role(item)
        item_id = message_id(item) or str(uuid.uuid4())
        if role == "user":
            out.append(
                UserMessage(id=item_id, role="user", content=message_content(item))
            )
            continue
        if role != "assistant":
            continue
        meta = _metadata(item)
        state = {
            "outcome": meta.get("outcome") or "done",
            "gate": meta.get("gate") or {},
            "plan": [
                {
                    "agent": row.get("agent"),
                    "task": row.get("task"),
                }
                for row in (meta.get("plan") or [])
                if isinstance(row, dict)
            ],
            "passed_steps": [
                row.get("index")
                for row in (meta.get("plan") or [])
                if isinstance(row, dict) and row.get("status") == "passed"
            ],
            "eval_by_step": {
                str(row.get("index")): {
                    "status": row.get("status"),
                    "feedback": row.get("feedback"),
                }
                for row in (meta.get("plan") or [])
                if isinstance(row, dict)
            },
            "steps_executed": (meta.get("steps") or {}).get("count") or 0,
            "started_at_ms": 0,
            "citations": meta.get("citations") or [],
        }
        # elapsed is already in stored steps; overlay after project_turn
        projected = project_turn(state)
        steps = meta.get("steps") or projected["steps"]
        projected["steps"] = {
            "count": steps.get("count", projected["steps"]["count"]),
            "elapsed_ms": steps.get("elapsed_ms", projected["steps"]["elapsed_ms"]),
        }
        projected["plan"] = meta.get("plan") or projected["plan"]
        projected["citations"] = meta.get("citations") or projected["citations"]
        projected["gate"] = meta.get("gate") or projected["gate"]
        outcome = str(projected.get("outcome") or "done")
        gate = projected.get("gate") or {}
        if gate:
            out.append(
                _activity("GATE", dict(gate), suffix=f"{item_id}-gate")
            )
        if outcome == "done":
            out.append(
                _activity("PLAN", {"items": projected["plan"]}, suffix=f"{item_id}-plan")
            )
            out.append(
                _activity("STEPS", dict(projected["steps"]), suffix=f"{item_id}-steps")
            )
            out.append(
                AssistantMessage(
                    id=item_id,
                    role="assistant",
                    content=message_content(item),
                )
            )
            out.append(
                _activity(
                    "SOURCES",
                    {"items": projected["citations"]},
                    suffix=f"{item_id}-sources",
                )
            )
            continue
        out.append(
            _activity(
                "OUTCOME",
                {"outcome": outcome, "reason": message_content(item)},
                suffix=f"{item_id}-outcome",
            )
        )
    return out
