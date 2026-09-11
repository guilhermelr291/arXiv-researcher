"""Dump ingested paper chunks as qrel-labeling JSON (chunk_id, index, kind, section, content)."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from plan_based_researcher.config import Settings

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT_DIR = _REPO_ROOT / "eval" / "retrieve"

_ABS_ID_RE = re.compile(
    r"(?P<arxiv_id>\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v(?P<version>\d+))?",
    re.IGNORECASE,
)

_LIST_CHUNKS_SQL = """
SELECT
  chunk_id,
  chunk_index,
  kind,
  metadata->>'section' AS section,
  content
FROM chunks
WHERE arxiv_id = %s AND version = %s
ORDER BY chunk_index
"""

_GET_PAPER_SQL = """
SELECT arxiv_id, version
FROM papers
WHERE arxiv_id = %s AND version = %s
"""


def parse_paper_ref(raw: str, version_override: str | None = None) -> tuple[str, str]:
    text = raw.strip()
    match = _ABS_ID_RE.fullmatch(text)
    if match is None:
        raise ValueError(
            f"Invalid paper id {raw!r}; expected e.g. 2609.01617 or 2609.01617v1."
        )
    arxiv_id = match.group("arxiv_id")
    if version_override is not None and str(version_override).strip():
        version = str(version_override).strip().lstrip("vV")
        if not version.isdigit():
            raise ValueError(f"Invalid version {version_override!r}.")
        return arxiv_id, version
    return arxiv_id, match.group("version") or "1"


def dump_row(row: Mapping[str, Any]) -> dict[str, Any]:
    section = row["section"]
    return {
        "chunk_id": str(row["chunk_id"]),
        "chunk_index": int(row["chunk_index"]),
        "kind": str(row["kind"]),
        "section": "" if section is None else str(section),
        "content": str(row["content"]),
    }


def dump_output_path(arxiv_id: str, version: str, *, as_array: bool) -> Path:
    paper_key = f"{arxiv_id}v{version}"
    suffix = ".chunks.json" if as_array else ".chunks.jsonl"
    return _DEFAULT_OUT_DIR / paper_key / f"{paper_key}{suffix}"


def format_dump(rows: Sequence[Mapping[str, Any]], *, as_array: bool) -> str:
    payload = [dump_row(row) for row in rows]
    if as_array:
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return "".join(
        json.dumps(item, ensure_ascii=False) + "\n" for item in payload
    )


def main() -> None:
    args = _parse_args()
    try:
        arxiv_id, version = parse_paper_ref(args.paper, args.version)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from None
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_dump(arxiv_id, version, as_array=args.array))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dump ingested Postgres chunks for a paper as UTF-8 JSONL under "
            "eval/retrieve/{arxiv_id}v{version}/."
        )
    )
    parser.add_argument(
        "paper",
        help="arXiv id, optionally with version suffix (e.g. 2609.01617v1).",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Version digit(s); overrides a vN suffix. Default 1 if omitted.",
    )
    parser.add_argument(
        "--array",
        action="store_true",
        help="Pretty-printed JSON array (.chunks.json) instead of JSONL.",
    )
    return parser.parse_args()


async def _dump(
    arxiv_id: str,
    version: str,
    *,
    as_array: bool,
) -> None:
    settings = Settings()
    async with await AsyncConnection.connect(
        settings.database_url,
        autocommit=True,
        row_factory=dict_row,
    ) as conn:
        paper_cur = await conn.execute(_GET_PAPER_SQL, (arxiv_id, version))
        paper_row = await paper_cur.fetchone()
        if paper_row is None:
            print(
                f"Paper {arxiv_id}v{version} is not in Postgres. "
                "Ingest it before dumping chunks.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        cur = await conn.execute(_LIST_CHUNKS_SQL, (arxiv_id, version))
        rows = await cur.fetchall()
    if not rows:
        print(
            f"Paper {arxiv_id}v{version} has no chunks.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    text = format_dump(rows, as_array=as_array)
    out = dump_output_path(arxiv_id, version, as_array=as_array)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)
    print(f"{len(rows)} chunks for {arxiv_id}v{version}", file=sys.stderr)


if __name__ == "__main__":
    main()
