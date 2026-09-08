"""POST /research SSE route (API-01, SSE-01, SSE-02, CAP-01)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from plan_based_researcher.api.deps import get_executor, get_settings
from plan_based_researcher.api.schemas import ResearchRequest
from plan_based_researcher.api.sse import SSE_HEADERS

router = APIRouter()


def _parse_research_request(body: object) -> ResearchRequest:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="thread_id is required")
    thread_id = body.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required")
    query = body.get("query")
    if not isinstance(query, str):
        query = "" if query is None else str(query)
    return ResearchRequest(query=query, thread_id=thread_id.strip())


@router.post("/research")
async def research(
    request: Request,
    executor: Any = Depends(get_executor),
    settings: Any = Depends(get_settings),
) -> StreamingResponse:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="thread_id is required") from None

    research_request = _parse_research_request(body)
    timeout_seconds = int(getattr(settings, "research_timeout_seconds", 120))
    return StreamingResponse(
        executor.execute(
            research_request.query,
            research_request.thread_id,
            timeout_seconds,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
