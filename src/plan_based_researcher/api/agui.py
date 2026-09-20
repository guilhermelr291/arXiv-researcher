"""AG-UI adapter: graph.astream custom+updates → EventEncoder SSE frames."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from collections.abc import AsyncIterator

from ag_ui.core import (
    ActivityDeltaEvent,
    ActivitySnapshotEvent,
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.encoder import EventEncoder

from plan_based_researcher.api.json_patch import json_patch
from plan_based_researcher.graph.project import project_turn

__all__ = ["AguiAdapter", "STREAM_MODES"]

STREAM_MODES = ["custom", "updates"]

_EVAL_STATUS = {
    "pass": "passed",
    "passed": "passed",
    "retry": "retry",
    "fail": "replan",
    "replan": "replan",
}

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def stream_headers() -> dict[str, str]:
    return dict(_SSE_HEADERS)


def _fold(running: dict, update: object) -> None:
    if not isinstance(update, dict):
        return
    for value in update.values():
        if isinstance(value, dict):
            running.update(value)


def _pending_plan_items(steps: object) -> list[dict]:
    items: list[dict] = []
    if not isinstance(steps, list):
        return items
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            step = {}
        items.append(
            {
                "index": index,
                "agent": step.get("agent") or "",
                "task": step.get("task") or "",
                "status": "pending",
                "feedback": None,
            }
        )
    return items


def _sources_items(citations: object) -> list[dict]:
    items: list[dict] = []
    if not isinstance(citations, list):
        return items
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        items.append(
            {
                "n": citation.get("n"),
                "arxiv_id": citation.get("arxiv_id"),
                "title": citation.get("title"),
                "year": citation.get("year"),
                "url": citation.get("url"),
                "excerpt": citation.get("excerpt"),
                "chunk_id": citation.get("chunk_id"),
            }
        )
    items.sort(key=lambda row: int(row.get("n") or 0))
    return items


class AguiAdapter:
    def __init__(
        self, graph, *, encoder: EventEncoder | None = None, transcript=None
    ) -> None:
        self._graph = graph
        self._encoder = encoder or EventEncoder()
        self._transcript = transcript

    async def stream(
        self,
        *,
        thread_id: str,
        run_id: str,
        input: dict | None,
        timeout_seconds: float,
        config: dict | None = None,
    ) -> AsyncIterator[str]:
        encoder = self._encoder
        yield encoder.encode(
            RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=thread_id,
                run_id=run_id,
            )
        )
        running: dict = dict(input or {})
        plan_message_id: str | None = None
        last_plan_content: dict | None = None
        assistant_id: str | None = None
        text_open = False
        markdown = ""
        query_used = ""
        step_nodes: list[dict] = []
        started = time.monotonic()
        config = config or {"configurable": {"thread_id": thread_id}}
        stream = None

        async def persist(outcome: str, reason: str | None) -> None:
            if self._transcript is None:
                return
            projected = project_turn({**running, "outcome": outcome})
            writer_id = str(running.get("writer_message_id") or "")
            item_id = writer_id or assistant_id or run_id
            gate = projected.get("gate") if isinstance(projected.get("gate"), dict) else {}
            plan = projected.get("plan") if isinstance(projected.get("plan"), list) else []
            citations = (
                projected.get("citations")
                if isinstance(projected.get("citations"), list)
                else []
            )
            steps = projected.get("steps") if isinstance(projected.get("steps"), dict) else {}
            elapsed = steps.get("elapsed_ms") or int(
                max(0, (time.monotonic() - started) * 1000)
            )
            count = steps.get("count") or len(step_nodes)
            payload = {
                "outcome": outcome,
                "content": markdown if outcome == "done" else str(reason or markdown or ""),
                "gate": gate,
                "plan": plan,
                "steps": {
                    "count": int(count or 0),
                    "elapsed_ms": int(elapsed or 0),
                    "nodes": [dict(node) for node in step_nodes],
                },
                "citations": citations,
            }
            await self._transcript.insert_assistant_turn(thread_id, str(item_id), payload)
        try:
            stream = self._graph.astream(
                input,
                config,
                stream_mode=STREAM_MODES,
            )
            aiter = stream.__aiter__()
            deadline = time.monotonic() + timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await persist("insufficient", "timeout")
                    yield encoder.encode(
                        RunFinishedEvent(
                            type=EventType.RUN_FINISHED,
                            thread_id=thread_id,
                            run_id=run_id,
                            result={"outcome": "insufficient", "reason": "timeout"},
                        )
                    )
                    return
                try:
                    item = await asyncio.wait_for(anext(aiter, None), timeout=remaining)
                except (TimeoutError, asyncio.TimeoutError):
                    await persist("insufficient", "timeout")
                    yield encoder.encode(
                        RunFinishedEvent(
                            type=EventType.RUN_FINISHED,
                            thread_id=thread_id,
                            run_id=run_id,
                            result={"outcome": "insufficient", "reason": "timeout"},
                        )
                    )
                    return
                if item is None:
                    return
                mode, chunk = item
                if mode == "updates":
                    previous = (
                        {"items": last_plan_content["items"]}
                        if last_plan_content is not None
                        else None
                    )
                    _fold(running, chunk)
                    projected = project_turn(running)
                    plan_content = {"items": projected["plan"]}
                    if (
                        plan_message_id is not None
                        and previous is not None
                        and plan_content != previous
                    ):
                        patch = json_patch(previous, plan_content)
                        if patch:
                            yield encoder.encode(
                                ActivityDeltaEvent(
                                    type=EventType.ACTIVITY_DELTA,
                                    message_id=plan_message_id,
                                    activity_type="PLAN",
                                    patch=patch,
                                )
                            )
                        last_plan_content = plan_content
                    continue
                if mode != "custom" or not isinstance(chunk, dict):
                    continue
                event = chunk.get("event")
                data = chunk.get("data") or {}
                if not isinstance(data, dict):
                    data = {}
                if event == "node_start":
                    name = str(data.get("node") or "")
                    step_nodes.append({"name": name, "query_used": ""})
                    metadata = {
                        key: data[key]
                        for key in ("step_index", "agent", "task")
                        if key in data
                    }
                    yield encoder.encode(
                        StepStartedEvent(
                            type=EventType.STEP_STARTED,
                            step_name=name,
                            metadata=metadata or None,
                        )
                    )
                elif event == "node_end":
                    name = str(data.get("node") or "")
                    metadata = {}
                    if name in ("search", "execute") and query_used:
                        metadata["query_used"] = query_used
                        if step_nodes and step_nodes[-1].get("name") == name:
                            step_nodes[-1]["query_used"] = query_used
                    yield encoder.encode(
                        StepFinishedEvent(
                            type=EventType.STEP_FINISHED,
                            step_name=name,
                            metadata=metadata or None,
                        )
                    )
                    query_used = ""
                elif event == "step_end":
                    query_used = str(data.get("query_used") or "")
                elif event == "gate":
                    running["gate"] = data
                elif event == "plan":
                    items = _pending_plan_items(data.get("steps"))
                    running["plan"] = data.get("steps") or []
                    plan_message_id = str(uuid.uuid4())
                    last_plan_content = {"items": items}
                    yield encoder.encode(
                        ActivitySnapshotEvent(
                            type=EventType.ACTIVITY_SNAPSHOT,
                            message_id=plan_message_id,
                            activity_type="PLAN",
                            content=last_plan_content,
                        )
                    )
                elif event == "eval":
                    idx = data.get("step_index")
                    status = _EVAL_STATUS.get(str(data.get("status") or ""), "pending")
                    feedback = data.get("feedback")
                    by_step = dict(running.get("eval_by_step") or {})
                    by_step[str(idx)] = {"status": status, "feedback": feedback}
                    running["eval_by_step"] = by_step
                    if status == "passed":
                        passed = list(running.get("passed_steps") or [])
                        try:
                            passed_i = int(idx)
                        except (TypeError, ValueError):
                            passed_i = -1
                        if passed_i >= 0 and passed_i not in passed:
                            passed.append(passed_i)
                            running["passed_steps"] = passed
                    projected = project_turn(running)
                    plan_content = {"items": projected["plan"]}
                    if plan_message_id is not None and last_plan_content is not None:
                        patch = json_patch(last_plan_content, plan_content)
                        if patch:
                            yield encoder.encode(
                                ActivityDeltaEvent(
                                    type=EventType.ACTIVITY_DELTA,
                                    message_id=plan_message_id,
                                    activity_type="PLAN",
                                    patch=patch,
                                )
                            )
                    last_plan_content = plan_content
                elif event == "answer_start":
                    assistant_id = str(data.get("message_id") or uuid.uuid4())
                    text_open = True
                    yield encoder.encode(
                        TextMessageStartEvent(
                            type=EventType.TEXT_MESSAGE_START,
                            message_id=assistant_id,
                            role="assistant",
                        )
                    )
                elif event == "answer_delta":
                    if assistant_id is None:
                        continue
                    delta = str(data.get("text") or "")
                    markdown += delta
                    yield encoder.encode(
                        TextMessageContentEvent(
                            type=EventType.TEXT_MESSAGE_CONTENT,
                            message_id=assistant_id,
                            delta=delta,
                        )
                    )
                elif event == "citations":
                    if assistant_id is not None and text_open:
                        text_open = False
                        yield encoder.encode(
                            TextMessageEndEvent(
                                type=EventType.TEXT_MESSAGE_END,
                                message_id=assistant_id,
                            )
                        )
                    items = _sources_items(data.get("citations"))
                    running["citations"] = items
                    yield encoder.encode(
                        ActivitySnapshotEvent(
                            type=EventType.ACTIVITY_SNAPSHOT,
                            message_id=str(uuid.uuid4()),
                            activity_type="SOURCES",
                            content={"items": items},
                        )
                    )
                elif event in ("done", "insufficient", "error"):
                    if assistant_id is not None and text_open:
                        text_open = False
                        yield encoder.encode(
                            TextMessageEndEvent(
                                type=EventType.TEXT_MESSAGE_END,
                                message_id=assistant_id,
                            )
                        )
                    if event == "done":
                        outcome = str(data.get("outcome") or "done")
                        reason = None if outcome == "done" else data.get("reason")
                    elif event == "insufficient":
                        outcome = "insufficient"
                        reason = data.get("reason")
                    else:
                        outcome = "error"
                        reason = data.get("message")
                    await persist(outcome, None if reason is None else str(reason))
                    yield encoder.encode(
                        RunFinishedEvent(
                            type=EventType.RUN_FINISHED,
                            thread_id=thread_id,
                            run_id=run_id,
                            result={"outcome": outcome, "reason": reason},
                        )
                    )
                    return
        except Exception as exc:
            await persist("error", str(exc))
            yield encoder.encode(
                RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message=str(exc),
                )
            )
        finally:
            aclose = getattr(stream, "aclose", None) if stream is not None else None
            if aclose is not None:
                result = aclose()
                if inspect.isawaitable(result):
                    await result
