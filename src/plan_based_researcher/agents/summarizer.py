"""English conversation summary for the planner. Not a plan agent."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from plan_based_researcher.agents.registry import REGISTRY
from plan_based_researcher.policy import Policy

__all__ = ["ConversationSummary", "SummarizerRunner", "SummaryResult", "render_summary"]

_FIELDS: tuple[tuple[str, str], ...] = (
    ("current_user_goal", "## Current user goal"),
    (
        "decisions_made",
        "## Decisions made (with the reason, when it matters)",
    ),
    ("constraints_and_preferences", "## Stated constraints and preferences"),
    ("important_entities_and_values", "## Important entities and values"),
    ("what_has_been_done", "## What has already been done"),
    ("open_items", "## Open items and unanswered questions"),
)


class ConversationSummary(BaseModel):
    current_user_goal: str = Field(
        description=(
            "English. The student's current research goal in this thread, "
            "even when they wrote in another language."
        )
    )
    decisions_made: str = Field(
        description=(
            "English. Choices already settled in this thread and the reason, "
            "when it matters for the next plan. Empty string if none."
        )
    )
    constraints_and_preferences: str = Field(
        description=(
            "English. Constraints the student stated in this thread "
            "(scope, language, recency, what to compare or leave out). "
            "Not a profile that applies to other chats. Empty string if none."
        )
    )
    important_entities_and_values: str = Field(
        description=(
            "English. Paper ids, method names, and other values from this thread "
            "that a later plan must not drop. Empty string if none."
        )
    )
    what_has_been_done: str = Field(
        description=(
            "English. Searches, papers, and answers already produced in this thread, "
            "so the next plan does not repeat them. Empty string if none."
        )
    )
    open_items: str = Field(
        description=(
            "English. Questions still unanswered in this thread. Empty string if none."
        )
    )


@dataclass(frozen=True, slots=True)
class SummaryResult:
    text: str
    input_tokens: int
    output_tokens: int


def render_summary(fields: dict) -> str:
    parts = [f"{heading}\n{fields.get(key) or ''}" for key, heading in _FIELDS]
    return "\n\n".join(parts)


class SummarizerRunner:
    def __init__(self, api_key: str | None = None) -> None:
        spec = REGISTRY["summarizer"]
        kwargs: dict = {
            "model": spec.model,
            "reasoning_effort": Policy.summarizer_reasoning_effort,
            "max_completion_tokens": Policy.summarizer_max_completion_tokens,
        }
        if api_key is not None:
            kwargs["api_key"] = api_key
        self._structured = ChatOpenAI(**kwargs).with_structured_output(
            ConversationSummary,
            include_raw=True,
        )

    async def summarize(self, prompt: str) -> SummaryResult:
        raw = await self._structured.ainvoke(prompt)
        parsed = raw["parsed"] if isinstance(raw, dict) else raw
        usage = {}
        if isinstance(raw, dict):
            message = raw.get("raw")
            usage = getattr(message, "usage_metadata", None) or {}
        data = parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)
        return SummaryResult(
            text=render_summary(data),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )
