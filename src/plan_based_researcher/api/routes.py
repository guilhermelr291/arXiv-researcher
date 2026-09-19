"""POST /agent and GET /threads (AG-UI)."""

from __future__ import annotations

from typing import Any

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from plan_based_researcher.api.agui import AguiAdapter, stream_headers
from plan_based_researcher.api.deps import get_graph, get_settings, get_transcript
from plan_based_researcher.api.replay import (
    items_to_agui_messages,
    snapshot_status,
)

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
    transcript: Any = Depends(get_transcript),
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
        last = body.messages[-1]
        query = _user_text(last)
        await transcript.insert_user(
            body.thread_id,
            str(getattr(last, "id", "") or ""),
            query,
        )
        graph_input = graph.initial_graph_state(query)
    adapter = AguiAdapter(graph, transcript=transcript)
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


@router.get("/threads")
async def list_threads(transcript: Any = Depends(get_transcript)) -> JSONResponse:
    rows = await transcript.list_threads()
    payload = [
        {
            "threadId": row.thread_id,
            "title": row.title,
            "updatedAt": row.updated_at,
        }
        for row in rows
    ]
    return JSONResponse(payload)


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    graph: Any = Depends(get_graph),
    transcript: Any = Depends(get_transcript),
) -> JSONResponse:
    items = await transcript.list_items(thread_id)
    if not items:
        raise HTTPException(status_code=404, detail="thread not found")
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    payload = {
        "threadId": thread_id,
        "messages": [
            message.model_dump(by_alias=True, exclude_none=True)
            for message in items_to_agui_messages(items)
        ],
        "status": snapshot_status(getattr(snapshot, "next", ())),
    }
    return JSONResponse(payload)
