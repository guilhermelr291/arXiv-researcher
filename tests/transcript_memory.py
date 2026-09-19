"""In-memory transcript store for unittest (no Postgres)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

ALLOWED_KINDS = frozenset({"user", "assistant_turn"})


@dataclass(slots=True)
class MemoryItem:
    id: str
    thread_id: str
    kind: str
    payload: dict


@dataclass(slots=True)
class MemoryThread:
    thread_id: str
    title: str
    updated_at: str


@dataclass(slots=True)
class MemoryTranscriptStore:
    threads: dict[str, MemoryThread] = field(default_factory=dict)
    items: list[MemoryItem] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    items_at_astream: list[MemoryItem] | None = None

    async def ensure_schema(self) -> None:
        return None

    async def insert_user(self, thread_id: str, item_id: str, content: str) -> None:
        await self.insert(thread_id, item_id, "user", {"content": content})

    async def insert_assistant_turn(
        self, thread_id: str, item_id: str, payload: dict
    ) -> None:
        self.log.append("assistant_turn")
        await self.insert(thread_id, item_id, "assistant_turn", dict(payload))

    async def insert(
        self, thread_id: str, item_id: str, kind: str, payload: dict
    ) -> None:
        if kind not in ALLOWED_KINDS:
            return
        if any(item.id == item_id for item in self.items):
            return
        if thread_id not in self.threads:
            title = ""
            if kind == "user":
                title = str(payload.get("content") or "")[:80]
            self.threads[thread_id] = MemoryThread(
                thread_id=thread_id,
                title=title,
                updated_at=_now(),
            )
        else:
            self.threads[thread_id].updated_at = _now()
        self.items.append(
            MemoryItem(id=item_id, thread_id=thread_id, kind=kind, payload=dict(payload))
        )

    async def list_threads(self) -> list[MemoryThread]:
        rows = list(self.threads.values())
        rows.sort(key=lambda row: row.updated_at, reverse=True)
        return rows

    async def list_items(self, thread_id: str) -> list[MemoryItem]:
        return [item for item in self.items if item.thread_id == thread_id]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
