"""POST /agent and GET /threads/{thread_id} (AG-UI)."""

from __future__ import annotations

from typing import Any

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from plan_based_researcher.api.agui import AguiAdapter, stream_headers
from plan_based_researcher.api.deps import get_graph, get_settings
from plan_based_researcher.api.replay import snapshot_status, snapshot_to_agui_messages

router = APIRouter()


def _user_text(message: object) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return str(content or "")


def _resume_flag(body: RunAgentInput) -> bool:
    props = body.forwarded_props
    if isinstance(props, dict):
        return bool(props.get("resume"))
    return bool(getattr(props, "resume", False))


@router.post("/agent")
async def agent_run(
    body: RunAgentInput,
    graph: Any = Depends(get_graph),
    settings: Any = Depends(get_settings),
) -> StreamingResponse:
    resume = _resume_flag(body)
    if not body.messages and not resume:
        raise HTTPException(
            status_code=400,
            detail="one user message or resume is required",
        )
    config = {"configurable": {"thread_id": body.thread_id}}
    timeout = int(getattr(settings, "research_timeout_seconds", 120))
    if resume:
        snapshot = await graph.aget_state(config)
        next_nodes = getattr(snapshot, "next", ()) or ()
        if not next_nodes:
            raise HTTPException(status_code=409, detail="nothing to resume")
        graph_input: dict | None = None
    else:
        query = _user_text(body.messages[-1]) if body.messages else ""
        graph_input = graph.initial_graph_state(query)
    adapter = AguiAdapter(graph)
    return StreamingResponse(
        adapter.stream(
            thread_id=body.thread_id,
            run_id=body.run_id,
            input=graph_input,
            timeout_seconds=timeout,
            config=config,
        ),
        media_type="text/event-stream",
        headers=stream_headers(),
    )


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, graph: Any = Depends(get_graph)) -> JSONResponse:
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = getattr(snapshot, "values", None) or {}
    messages = values.get("messages") if isinstance(values, dict) else None
    if not messages:
        raise HTTPException(status_code=404, detail="thread not found")
    payload = {
        "threadId": thread_id,
        "messages": [
            message.model_dump(by_alias=True, exclude_none=True)
            for message in snapshot_to_agui_messages(messages)
        ],
        "status": snapshot_status(getattr(snapshot, "next", ())),
    }
    return JSONResponse(payload)
