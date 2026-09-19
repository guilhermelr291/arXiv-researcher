"""Postgres product transcript: threads + transcript_items (CREATE-only)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from plan_based_researcher.ports.transcript import (
    ThreadSummary,
    TranscriptItem,
    TranscriptKind,
)

__all__ = ["TRANSCRIPT_SCHEMA_SQL", "PgTranscriptStore"]

ALLOWED_KINDS = frozenset({"user", "assistant_turn"})

TRANSCRIPT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS threads (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transcript_items (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES threads (id),
  seq BIGINT GENERATED ALWAYS AS IDENTITY,
  kind TEXT NOT NULL CHECK (kind IN ('user', 'assistant_turn')),
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS transcript_items_thread_seq
  ON transcript_items (thread_id, seq);
"""


def _schema_statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        stamp = value.isoformat()
        if stamp.endswith("+00:00"):
            return stamp[:-6] + "Z"
        return stamp
    text = str(value)
    return text[:-6] + "Z" if text.endswith("+00:00") else text


class PgTranscriptStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def ensure_schema(self) -> None:
        async with self._pool.connection() as conn:
            for statement in _schema_statements(TRANSCRIPT_SCHEMA_SQL):
                await conn.execute(statement)

    async def insert_user(self, thread_id: str, item_id: str, content: str) -> None:
        await self.insert(thread_id, item_id, "user", {"content": content})

    async def insert_assistant_turn(
        self, thread_id: str, item_id: str, payload: Mapping[str, object]
    ) -> None:
        await self.insert(thread_id, item_id, "assistant_turn", payload)

    async def insert(
        self,
        thread_id: str,
        item_id: str,
        kind: str,
        payload: Mapping[str, object],
    ) -> None:
        if kind not in ALLOWED_KINDS:
            return
        title = ""
        if kind == "user":
            title = str(payload.get("content") or "")[:80]
        async with self._pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO threads (id, title)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET updated_at = now()
                    """,
                    (thread_id, title or ""),
                )
                await conn.execute(
                    """
                    INSERT INTO transcript_items (id, thread_id, kind, payload)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (item_id, thread_id, kind, Jsonb(dict(payload))),
                )

    async def list_threads(self) -> list[ThreadSummary]:
        async with self._pool.connection() as conn:
            rows = await conn.execute(
                """
                SELECT id, title, updated_at
                FROM threads
                ORDER BY updated_at DESC
                """
            )
            fetched = await rows.fetchall()
        return [
            ThreadSummary(
                thread_id=str(row["id"]),
                title=str(row["title"]),
                updated_at=_iso(row["updated_at"]),
            )
            for row in fetched
        ]

    async def list_items(self, thread_id: str) -> list[TranscriptItem]:
        async with self._pool.connection() as conn:
            rows = await conn.execute(
                """
                SELECT id, thread_id, kind, payload
                FROM transcript_items
                WHERE thread_id = %s
                ORDER BY seq
                """,
                (thread_id,),
            )
            fetched = await rows.fetchall()
        items: list[TranscriptItem] = []
        for row in fetched:
            kind = str(row["kind"])
            if kind not in ALLOWED_KINDS:
                continue
            payload = row["payload"]
            stored: TranscriptKind = "user" if kind == "user" else "assistant_turn"
            items.append(
                TranscriptItem(
                    id=str(row["id"]),
                    thread_id=str(row["thread_id"]),
                    kind=stored,
                    payload=dict(payload) if isinstance(payload, dict) else {},
                )
            )
        return items
