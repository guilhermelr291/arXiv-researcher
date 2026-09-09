"""Drop local papers/chunks so the next API boot can CREATE vector(1024) chunks.

Does not touch LangGraph checkpointer tables. Refuses to run without --yes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from plan_based_researcher.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Drop the chunks table and delete papers rows. "
            "Checkpointer tables are left alone. Requires --yes."
        )
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually mutate the database (required).",
    )
    args = parser.parse_args()
    if not args.yes:
        print(
            "Refusing to wipe: pass --yes to DROP chunks and DELETE papers.",
            file=sys.stderr,
        )
        sys.exit(2)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_wipe())


async def _wipe() -> None:
    settings = Settings()
    async with await AsyncConnection.connect(
        settings.database_url,
        autocommit=True,
        row_factory=dict_row,
    ) as conn:
        chunk_n = await _count(conn, "chunks")
        paper_n = await _count(conn, "papers")
        await conn.execute("DROP TABLE IF EXISTS chunks")
        if await _table_exists(conn, "papers"):
            await conn.execute("DELETE FROM papers")
        print(
            f"Dropped chunks (was {chunk_n} rows); "
            f"deleted papers (was {paper_n} rows). "
            "Restart the API so ensure_schema can CREATE chunks."
        )


async def _table_exists(conn: AsyncConnection, name: str) -> bool:
    cur = await conn.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = current_schema()
            AND table_name = %s
        ) AS present
        """,
        (name,),
    )
    row = await cur.fetchone()
    return bool(row["present"]) if row is not None else False


async def _count(conn: AsyncConnection, name: str) -> int:
    if not await _table_exists(conn, name):
        return 0
    cur = await conn.execute(f"SELECT COUNT(*) AS n FROM {name}")
    row = await cur.fetchone()
    return int(row["n"]) if row is not None else 0


if __name__ == "__main__":
    main()
