"""In-memory compaction row for unittest. One row per thread_id."""

from __future__ import annotations

from dataclasses import replace

from plan_based_researcher.repo.compaction import CompactionRow, check_status


class MemoryCompactionStore:
    def __init__(self) -> None:
        self.rows: dict[str, CompactionRow] = {}

    async def get(self, thread_id: str) -> CompactionRow | None:
        row = self.rows.get(thread_id)
        if row is None:
            return None
        return replace(row)

    async def upsert(self, row: CompactionRow) -> None:
        check_status(row.status)
        self.rows[row.thread_id] = row
