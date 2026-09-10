"""Chainlit chat: HTTP client of FastAPI ``POST /research`` (UI-01, UI-02, UI-03)."""

from __future__ import annotations

import json
import os
import uuid

import chainlit as cl
import httpx

from plan_based_researcher.ui.sse_map import iter_sse_frames, side_panel_texts

# Chainlit loads `.env` on import and treats DATABASE_URL as ChainlitDataLayer
# (asyncpg). That URL is for the FastAPI/pgvector process, not this UI.
os.environ.pop("DATABASE_URL", None)

RESEARCH_URL = os.environ.get("RESEARCH_API_URL", "http://127.0.0.1:8001/research")


@cl.on_chat_start
async def on_chat_start() -> None:
    cl.user_session.set("thread_id", str(uuid.uuid4()))


@cl.on_message
async def on_message(message: cl.Message) -> None:
    thread_id = cl.user_session.get("thread_id")
    if not thread_id:
        thread_id = str(uuid.uuid4())
        cl.user_session.set("thread_id", thread_id)

    open_steps: dict[object, cl.Step] = {}
    answer: dict = {"message": None, "finalized": False}
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                RESEARCH_URL,
                json={"query": message.content, "thread_id": thread_id},
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    await cl.Message(
                        content=f"API error {response.status_code}: {body}"
                    ).send()
                    return
                async for event, data in iter_sse_frames(response.aiter_lines()):
                    await _handle_event(event, data, open_steps, answer)
    except httpx.HTTPError as exc:
        await cl.Message(content=f"Research request failed: {exc}").send()
    finally:
        for step in open_steps.values():
            await step.update()


async def _handle_event(
    event: str, data: dict, open_steps: dict[object, cl.Step], answer: dict
) -> None:
    if event == "step_start":
        await _on_step_start(data, open_steps)
        return
    if event == "step_end":
        await _on_step_end(data, open_steps)
        return
    if event == "plan":
        async with cl.Step(name="plan", type="llm", default_open=True) as step:
            step.output = _plan_text(data)
        return
    if event == "eval":
        async with cl.Step(
            name=f"eval:{data.get('agent') or 'step'}",
            default_open=True,
        ) as step:
            status = data.get("status") or ""
            feedback = data.get("feedback") or ""
            step.output = f"{status}\n{feedback}".strip()
            if status == "fail":
                step.is_error = True
        return
    if event == "answer_delta":
        text = data.get("text") or ""
        if not text:
            return
        msg = answer["message"]
        if msg is None:
            msg = cl.Message(content="")
            answer["message"] = msg
        await msg.stream_token(text)
        return
    if event == "citations":
        citations = data.get("citations") or []
        if not isinstance(citations, list):
            citations = []
        elements = [
            cl.Text(name=name, content=excerpt, display="side")
            for name, excerpt in side_panel_texts(citations)
        ]
        msg = answer["message"]
        if msg is None:
            msg = cl.Message(content="")
            answer["message"] = msg
        msg.elements = elements
        await msg.send()
        answer["finalized"] = True
        return
    if event == "gate":
        await cl.Message(content=_gate_text(data)).send()
        return
    if event == "done":
        outcome = data.get("outcome")
        await cl.Message(content=str(outcome) if outcome else "Done.").send()
        return
    if event == "insufficient":
        await cl.Message(
            content=str(data.get("reason") or "Insufficient evidence.")
        ).send()
        return
    if event == "error":
        msg = answer.get("message")
        if msg is not None and not answer.get("finalized"):
            await msg.send()
            answer["finalized"] = True
        await cl.Message(content=str(data.get("message") or "Research error.")).send()
        return


def _step_key(data: dict) -> object:
    idx = data.get("step_index")
    if isinstance(idx, int):
        return idx
    return data.get("agent") or "step"


async def _on_step_start(
    data: dict, open_steps: dict[object, cl.Step]
) -> None:
    agent = str(data.get("agent") or "step")
    idx = data.get("step_index")
    name = f"{idx}: {agent}" if idx is not None else agent
    step = cl.Step(name=name, type="tool", show_input=True, default_open=True)
    step.input = data.get("task") or ""
    await step.send()
    open_steps[_step_key(data)] = step


async def _on_step_end(data: dict, open_steps: dict[object, cl.Step]) -> None:
    output = _step_end_output(data)
    key = _step_key(data)
    step = open_steps.pop(key, None)
    if step is None and len(open_steps) == 1:
        step = open_steps.pop(next(iter(open_steps)))
    if step is None:
        async with cl.Step(
            name=str(data.get("agent") or "step"),
            show_input=True,
            default_open=True,
        ) as step:
            step.output = output
        return
    step.output = output
    await step.update()


def _step_end_output(data: dict) -> str:
    pgvector = data.get("pgvector", "unknown")
    paper_ids = data.get("paper_ids") or []
    papers = ", ".join(str(pid) for pid in paper_ids) if paper_ids else "(none)"
    query_used = str(data.get("query_used") or "").strip()
    lines = [f"pgvector: {pgvector}", f"paper_ids: {papers}"]
    if query_used:
        lines.append(f"query_used: {query_used}")
    return "\n".join(lines)


def _plan_text(data: dict) -> str:
    steps = data.get("steps") or []
    if not isinstance(steps, list):
        return json.dumps(data, ensure_ascii=False, indent=2)
    lines: list[str] = []
    for i, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            lines.append(f"{i}. {item}")
            continue
        agent = item.get("agent") or ""
        task = item.get("task") or ""
        reasoning = item.get("reasoning") or ""
        hist = " [historical]" if item.get("historical") else ""
        lines.append(f"{i}. {agent}{hist}: {task}")
        if reasoning:
            lines.append(f"   {reasoning}")
    return "\n".join(lines) if lines else json.dumps(data, ensure_ascii=False, indent=2)


def _gate_text(data: dict) -> str:
    reason = str(data.get("reason") or "")
    if data.get("in_domain"):
        language = data.get("language") or ""
        suffix = f" ({language})" if language else ""
        return reason or f"In domain{suffix}."
    return reason or "Out of domain."
