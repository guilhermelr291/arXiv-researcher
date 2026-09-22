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

    async def update_open_job(self, row: CompactionRow, *, watermark: str) -> bool:
        check_status(row.status)
        current = self.rows.get(row.thread_id)
        if (
            current is None
            or current.watermark != watermark
            or current.status not in {"running", "failed"}
        ):
            return False
        self.rows[row.thread_id] = row
        return True
