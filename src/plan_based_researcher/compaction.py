"""Decide when a thread compacts and run the summary job off the turn."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace

import tiktoken
from langgraph.graph.message import RemoveMessage

from plan_based_researcher.agents.history import (
    format_transcript,
    message_content,
    message_id,
    message_role,
)
from plan_based_researcher.policy import Policy
from plan_based_researcher.repo.compaction import CompactionRow, check_status

__all__ = [
    "CompactResult",
    "WatermarkChoice",
    "build_summarizer_prompt",
    "commit_ready",
    "count_text",
    "message_tokens",
    "plan_compact",
    "select_watermark",
    "thread_token_count",
]

_ENCODING = None


def _encoding():
    global _ENCODING
    if _ENCODING is None:
        _ENCODING = tiktoken.get_encoding(Policy.history_token_encoding)
    return _ENCODING


def count_text(text: str) -> int:
    if not text:
        return 0
    return len(_encoding().encode(text))


def message_tokens(message: object) -> int:
    if message_role(message) == "system":
        return 0
    stored = _stored_token_count(message)
    if stored is not None:
        return stored
    return count_text(message_content(message))


def _stored_token_count(message: object) -> int | None:
    if isinstance(message, dict):
        if message.get("token_count") is not None:
            return int(message["token_count"])
        extra = message.get("additional_kwargs") or {}
    else:
        extra = getattr(message, "additional_kwargs", None) or {}
    if isinstance(extra, dict) and extra.get("token_count") is not None:
        return int(extra["token_count"])
    return None


def thread_token_count(state: dict) -> int:
    """Applied summary plus message texts. System messages and papers are omitted."""
    total = count_text(str(state.get("conversation_summary") or ""))
    messages = state.get("messages") or []
    if not isinstance(messages, list):
        return total
    for message in messages:
        total += message_tokens(message)
    return total


@dataclass(frozen=True, slots=True)
class WatermarkChoice:
    watermark_id: str
    prefix_tokens: int
    suffix_tokens: int
    suffix_index: int
    prefix_messages: tuple


def select_watermark(messages: list) -> WatermarkChoice | None:
    """Kept suffix is at least the suffix budget and starts on a user message."""
    if not messages:
        return None
    acc = 0
    start_index = len(messages) - 1
    reached = False
    for index in range(len(messages) - 1, -1, -1):
        acc += message_tokens(messages[index])
        start_index = index
        if acc >= Policy.compaction_min_suffix_tokens:
            reached = True
            break
    if not reached:
        return None
    if message_role(messages[start_index]) != "user":
        user_index = None
        for index in range(start_index, -1, -1):
            if message_role(messages[index]) == "user":
                user_index = index
                break
        if user_index is None:
            return None
        start_index = user_index
    if start_index <= 0:
        return None
    watermark = messages[start_index - 1]
    watermark_id = message_id(watermark)
    if not watermark_id:
        return None
    prefix = tuple(messages[:start_index])
    suffix = messages[start_index:]
    prefix_tokens = sum(message_tokens(message) for message in prefix)
    suffix_tokens = sum(message_tokens(message) for message in suffix)
    if suffix_tokens < Policy.compaction_min_suffix_tokens:
        return None
    return WatermarkChoice(
        watermark_id=watermark_id,
        prefix_tokens=prefix_tokens,
        suffix_tokens=suffix_tokens,
        suffix_index=start_index,
        prefix_messages=prefix,
    )


def build_summarizer_prompt(summary: str, messages: tuple | list) -> str:
    transcript = format_transcript(list(messages))
    return (
        "Summarize the conversation so far in English.\n\n"
        f"Applied summary:\n{summary}\n\n"
        f"Messages through the watermark:\n{transcript}"
    )


@dataclass(frozen=True, slots=True)
class CompactResult:
    update: dict
    job: asyncio.Task | None = None


def _ids(messages: list) -> list[str]:
    return [message_id(message) for message in messages]


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


def _job_still_open(row: CompactionRow | None, watermark: str) -> bool:
    return (
        row is not None
        and row.watermark == watermark
        and row.status in {"running", "failed"}
    )


async def commit_ready(
    store,
    thread_id: str,
    *,
    summary: str,
    watermark: str,
    token_count_before: int = 0,
    estimated_token_count_after: int = 0,
    summary_token_count: int = 0,
    summarizer_input_tokens: int = 0,
    summarizer_output_tokens: int = 0,
) -> None:
    current = await store.get(thread_id)
    base = current or CompactionRow(thread_id=thread_id, status="ready")
    check_status("ready")
    await store.upsert(
        replace(
            base,
            thread_id=thread_id,
            status="ready",
            summary=summary,
            watermark=watermark,
            error="",
            token_count_before=token_count_before,
            estimated_token_count_after=estimated_token_count_after,
            summary_token_count=summary_token_count,
            summarizer_input_tokens=summarizer_input_tokens,
            summarizer_output_tokens=summarizer_output_tokens,
        )
    )


async def _finish_job(
    store,
    thread_id: str,
    summarizer,
    prompt: str,
    *,
    watermark: str,
    suffix_tokens: int,
    clock,
) -> None:
    current = await store.get(thread_id)
    previous = current.summary if current is not None else ""
    try:
        result = await asyncio.wait_for(
            summarizer.summarize(prompt),
            timeout=Policy.compaction_timeout_seconds,
        )
    except Exception as exc:
        failed = await store.get(thread_id)
        if not _job_still_open(failed, watermark):
            return
        await store.update_open_job(
            replace(
                failed,
                status="failed",
                error=_error_text(exc),
                summary=previous,
                failed_at=float(clock()),
            ),
            watermark=watermark,
        )
        return
    ready = await store.get(thread_id)
    if not _job_still_open(ready, watermark):
        return
    summary_tokens = count_text(result.text)
    await store.update_open_job(
        replace(
            ready,
            status="ready",
            summary=result.text,
            error="",
            token_count_before=ready.token_count_before,
            estimated_token_count_after=summary_tokens + suffix_tokens,
            summary_token_count=summary_tokens,
            summarizer_input_tokens=int(result.input_tokens),
            summarizer_output_tokens=int(result.output_tokens),
        ),
        watermark=watermark,
    )


def _can_start(row: CompactionRow | None, now: float) -> bool:
    if row is None:
        return True
    if row.status in {"running", "ready"}:
        return False
    if row.status == "failed" and row.failed_at is not None:
        elapsed = now - float(row.failed_at)
        if elapsed < Policy.compaction_failed_cooldown_seconds:
            return False
    return True


async def plan_compact(
    state: dict,
    store,
    *,
    thread_id: str,
    summarizer=None,
    now=None,
) -> CompactResult:
    """One compaction pass. The summary job is not awaited."""
    clock = now or time.time
    moment = float(clock())
    row = await store.get(thread_id)
    messages = state.get("messages") or []
    if not isinstance(messages, list):
        messages = []

    if row is not None and row.status == "running":
        started = row.running_started_at
        if started is not None and moment - float(started) > Policy.compaction_timeout_seconds:
            await store.upsert(
                replace(
                    row,
                    status="failed",
                    error="timed out",
                    failed_at=moment,
                    summary=row.summary,
                )
            )
        return CompactResult(update={})

    if row is not None and row.status == "ready":
        applied = str(state.get("applied_watermark") or "")
        if row.watermark and applied == row.watermark:
            await store.upsert(replace(row, status="applied"))
            return CompactResult(update={})
        present = row.watermark in _ids(messages)
        if not present or row.base_watermark != applied:
            await store.upsert(replace(row, status="discarded", summary=row.summary))
            return CompactResult(update={})
        if thread_token_count(state) <= Policy.compaction_trigger_tokens:
            return CompactResult(update={})
        index = _ids(messages).index(row.watermark)
        removals = [
            RemoveMessage(id=message_id(message))
            for message in messages[: index + 1]
            if message_id(message)
        ]
        await store.upsert(replace(row, status="applied"))
        return CompactResult(
            update={
                "messages": removals,
                "conversation_summary": row.summary,
                "applied_watermark": row.watermark,
            }
        )

    if not _can_start(row, moment):
        return CompactResult(update={})
    if thread_token_count(state) <= Policy.compaction_trigger_tokens:
        return CompactResult(update={})
    choice = select_watermark(messages)
    if choice is None or choice.prefix_tokens < Policy.compaction_min_prefix_tokens:
        return CompactResult(update={})
    if summarizer is None:
        return CompactResult(update={})

    previous_summary = row.summary if row is not None else ""
    running = CompactionRow(
        thread_id=thread_id,
        status="running",
        watermark=choice.watermark_id,
        base_watermark=str(state.get("applied_watermark") or ""),
        summary=previous_summary,
        error=row.error if row is not None else "",
        token_count_before=thread_token_count(state),
        running_started_at=moment,
        failed_at=row.failed_at if row is not None else None,
    )
    await store.upsert(running)
    prompt = build_summarizer_prompt(
        str(state.get("conversation_summary") or ""),
        choice.prefix_messages,
    )
    job = asyncio.create_task(
        _finish_job(
            store,
            thread_id,
            summarizer,
            prompt,
            watermark=choice.watermark_id,
            suffix_tokens=choice.suffix_tokens,
            clock=clock,
        )
    )
    return CompactResult(update={}, job=job)
