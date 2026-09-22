"""One compaction row per thread (CREATE-only)."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool

__all__ = ["ALLOWED_STATUS", "COMPACTION_SCHEMA_SQL", "CompactionRow", "PgCompactionStore"]

ALLOWED_STATUS = frozenset({"running", "ready", "applied", "failed", "discarded"})

COMPACTION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS compaction (
  thread_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('running', 'ready', 'applied', 'failed', 'discarded')),
  watermark TEXT NOT NULL DEFAULT '',
  base_watermark TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  token_count_before INTEGER NOT NULL DEFAULT 0,
  estimated_token_count_after INTEGER NOT NULL DEFAULT 0,
  summary_token_count INTEGER NOT NULL DEFAULT 0,
  summarizer_input_tokens INTEGER NOT NULL DEFAULT 0,
  summarizer_output_tokens INTEGER NOT NULL DEFAULT 0,
  running_started_at DOUBLE PRECISION,
  failed_at DOUBLE PRECISION
);
"""


def _schema_statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


@dataclass(frozen=True, slots=True)
class CompactionRow:
    thread_id: str
    status: str
    watermark: str = ""
    base_watermark: str = ""
    summary: str = ""
    error: str = ""
    token_count_before: int = 0
    estimated_token_count_after: int = 0
    summary_token_count: int = 0
    summarizer_input_tokens: int = 0
    summarizer_output_tokens: int = 0
    running_started_at: float | None = None
    failed_at: float | None = None


def check_status(status: str) -> None:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"invalid compaction status: {status}")


_COLUMNS = (
    "thread_id",
    "status",
    "watermark",
    "base_watermark",
    "summary",
    "error",
    "token_count_before",
    "estimated_token_count_after",
    "summary_token_count",
    "summarizer_input_tokens",
    "summarizer_output_tokens",
    "running_started_at",
    "failed_at",
)


def _row_from_mapping(mapping: dict) -> CompactionRow:
    return CompactionRow(
        thread_id=str(mapping["thread_id"]),
        status=str(mapping["status"]),
        watermark=str(mapping.get("watermark") or ""),
        base_watermark=str(mapping.get("base_watermark") or ""),
        summary=str(mapping.get("summary") or ""),
        error=str(mapping.get("error") or ""),
        token_count_before=int(mapping.get("token_count_before") or 0),
        estimated_token_count_after=int(mapping.get("estimated_token_count_after") or 0),
        summary_token_count=int(mapping.get("summary_token_count") or 0),
        summarizer_input_tokens=int(mapping.get("summarizer_input_tokens") or 0),
        summarizer_output_tokens=int(mapping.get("summarizer_output_tokens") or 0),
        running_started_at=mapping.get("running_started_at"),
        failed_at=mapping.get("failed_at"),
    )


class PgCompactionStore:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def ensure_schema(self) -> None:
        async with self._pool.connection() as conn:
            for statement in _schema_statements(COMPACTION_SCHEMA_SQL):
                await conn.execute(statement)

    async def get(self, thread_id: str) -> CompactionRow | None:
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM compaction WHERE thread_id = %s",
                (thread_id,),
            )
            fetched = await cursor.fetchone()
        if fetched is None:
            return None
        return _row_from_mapping(fetched)

    async def upsert(self, row: CompactionRow) -> None:
        check_status(row.status)
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO compaction (
                  thread_id, status, watermark, base_watermark, summary, error,
                  token_count_before, estimated_token_count_after, summary_token_count,
                  summarizer_input_tokens, summarizer_output_tokens,
                  running_started_at, failed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (thread_id) DO UPDATE SET
                  status = EXCLUDED.status,
                  watermark = EXCLUDED.watermark,
                  base_watermark = EXCLUDED.base_watermark,
                  summary = EXCLUDED.summary,
                  error = EXCLUDED.error,
                  token_count_before = EXCLUDED.token_count_before,
                  estimated_token_count_after = EXCLUDED.estimated_token_count_after,
                  summary_token_count = EXCLUDED.summary_token_count,
                  summarizer_input_tokens = EXCLUDED.summarizer_input_tokens,
                  summarizer_output_tokens = EXCLUDED.summarizer_output_tokens,
                  running_started_at = EXCLUDED.running_started_at,
                  failed_at = EXCLUDED.failed_at
                """,
                (
                    row.thread_id,
                    row.status,
                    row.watermark,
                    row.base_watermark,
                    row.summary,
                    row.error,
                    row.token_count_before,
                    row.estimated_token_count_after,
                    row.summary_token_count,
                    row.summarizer_input_tokens,
                    row.summarizer_output_tokens,
                    row.running_started_at,
                    row.failed_at,
                ),
            )

    async def update_open_job(self, row: CompactionRow, *, watermark: str) -> bool:
        """Write the job result only while this watermark is still running or failed."""
        check_status(row.status)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE compaction SET
                  status = %s,
                  summary = %s,
                  error = %s,
                  token_count_before = %s,
                  estimated_token_count_after = %s,
                  summary_token_count = %s,
                  summarizer_input_tokens = %s,
                  summarizer_output_tokens = %s,
                  running_started_at = %s,
                  failed_at = %s
                WHERE thread_id = %s
                  AND watermark = %s
                  AND status IN ('running', 'failed')
                """,
                (
                    row.status,
                    row.summary,
                    row.error,
                    row.token_count_before,
                    row.estimated_token_count_after,
                    row.summary_token_count,
                    row.summarizer_input_tokens,
                    row.summarizer_output_tokens,
                    row.running_started_at,
                    row.failed_at,
                    row.thread_id,
                    watermark,
                ),
            )
            return cursor.rowcount == 1
