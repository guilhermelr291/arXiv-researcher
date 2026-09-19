"""Product transcript store: desk-visible turns outside the checkpointer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Protocol

__all__ = ["ThreadSummary", "TranscriptItem", "TranscriptStore"]

TranscriptKind = Literal["user", "assistant_turn"]


@dataclass(frozen=True, slots=True)
class ThreadSummary:
    thread_id: str
    title: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class TranscriptItem:
    id: str
    thread_id: str
    kind: TranscriptKind
    payload: dict


class TranscriptStore(Protocol):
    async def ensure_schema(self) -> None: ...

    async def insert_user(self, thread_id: str, item_id: str, content: str) -> None: ...

    async def insert_assistant_turn(
        self, thread_id: str, item_id: str, payload: Mapping[str, object]
    ) -> None: ...

    async def insert(
        self,
        thread_id: str,
        item_id: str,
        kind: str,
        payload: Mapping[str, object],
    ) -> None: ...

    async def list_threads(self) -> list[ThreadSummary]: ...

    async def list_items(self, thread_id: str) -> list[TranscriptItem]: ...
