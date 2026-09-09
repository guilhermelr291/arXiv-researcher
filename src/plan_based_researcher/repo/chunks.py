"""Postgres papers/chunks store; RAG is scoped to selected (arxiv_id, version) keys."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
from uuid import uuid4

from pgvector import Vector
from pgvector.psycopg import register_vector_async
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkDraft, ChunkRecord, PaperRecord

_METADATA_KEYS = frozenset({"section", "caption", "unit_ids"})

_PREAMBLE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS papers (
  arxiv_id TEXT NOT NULL,
  version TEXT NOT NULL,
  title TEXT NOT NULL,
  year INT NOT NULL,
  url TEXT NOT NULL,
  categories TEXT[] NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (arxiv_id, version)
);
"""

_CHUNKS_SQL = f"""
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id UUID PRIMARY KEY,
  arxiv_id TEXT NOT NULL,
  version TEXT NOT NULL,
  chunk_index INT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('prose', 'table', 'equation')),
  unit_id TEXT,
  embedding_text TEXT NOT NULL,
  content TEXT NOT NULL,
  embedding vector({Policy.embedding_dimensions}) NOT NULL,
  metadata JSONB NOT NULL,
  UNIQUE (arxiv_id, version, chunk_index),
  FOREIGN KEY (arxiv_id, version) REFERENCES papers (arxiv_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS chunks_atomic_identity
  ON chunks (arxiv_id, version, unit_id)
  WHERE unit_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS chunks_papers_idx ON chunks (arxiv_id, version);
"""

_GET_PAPER_SQL = """
SELECT arxiv_id, version, title, year, url, categories
FROM papers
WHERE arxiv_id = %s AND version = %s
"""

_PAPER_HAS_CHUNKS_SQL = """
SELECT EXISTS (
  SELECT 1 FROM chunks WHERE arxiv_id = %s AND version = %s
) AS has_chunks
"""

_UPSERT_PAPER_SQL = """
INSERT INTO papers (arxiv_id, version, title, year, url, categories)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (arxiv_id, version) DO UPDATE SET
  title = EXCLUDED.title,
  year = EXCLUDED.year,
  url = EXCLUDED.url,
  categories = EXCLUDED.categories
"""

_DELETE_CHUNKS_SQL = """
DELETE FROM chunks WHERE arxiv_id = %s AND version = %s
"""

_INSERT_CHUNK_SQL = """
INSERT INTO chunks (
  chunk_id, arxiv_id, version, chunk_index,
  kind, unit_id, embedding_text, content, embedding, metadata
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_CHUNK_SELECT = """
  c.chunk_id,
  c.arxiv_id,
  c.version,
  p.title,
  p.year,
  p.url,
  c.kind,
  c.unit_id,
  c.content,
  c.metadata
"""

_SIMILARITY_SEARCH_SQL = f"""
SELECT
{_CHUNK_SELECT}
FROM chunks AS c
JOIN papers AS p
  ON p.arxiv_id = c.arxiv_id AND p.version = c.version
WHERE (c.arxiv_id, c.version) IN (
  SELECT * FROM unnest(%s::text[], %s::text[]) AS t(arxiv_id, version)
)
ORDER BY c.embedding <=> %s
LIMIT %s
"""

_LIST_CHUNKS_SQL = f"""
SELECT
{_CHUNK_SELECT}
FROM chunks AS c
JOIN papers AS p
  ON p.arxiv_id = c.arxiv_id AND p.version = c.version
WHERE (c.arxiv_id, c.version) IN (
  SELECT * FROM unnest(%s::text[], %s::text[]) AS t(arxiv_id, version)
)
ORDER BY c.arxiv_id, c.version, c.chunk_index
"""


def _schema_statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


def _paper_from_row(row: Mapping[str, Any]) -> PaperRecord:
    return PaperRecord(
        arxiv_id=str(row["arxiv_id"]),
        version=str(row["version"]),
        title=str(row["title"]),
        year=int(row["year"]),
        url=str(row["url"]),
        categories=list(row["categories"]),
    )


def _chunk_kind(value: Any) -> Literal["prose", "table", "equation"]:
    kind = str(value)
    if kind == "prose":
        return "prose"
    if kind == "table":
        return "table"
    if kind == "equation":
        return "equation"
    raise ValueError(f"invalid chunk kind: {kind}")


def _metadata_from_row(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(
        f"chunk metadata must be a dict, got {type(value).__name__}"
    )


def _validated_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    keys = frozenset(metadata)
    if keys != _METADATA_KEYS:
        raise ValueError(
            "chunk metadata keys must be exactly {section, caption, unit_ids}, "
            f"got {sorted(keys)}"
        )
    return dict(metadata)


def _chunk_from_row(row: Mapping[str, Any]) -> ChunkRecord:
    unit_id = row["unit_id"]
    return ChunkRecord(
        chunk_id=str(row["chunk_id"]),
        arxiv_id=str(row["arxiv_id"]),
        version=str(row["version"]),
        title=str(row["title"]),
        year=int(row["year"]),
        url=str(row["url"]),
        kind=_chunk_kind(row["kind"]),
        unit_id=None if unit_id is None else str(unit_id),
        content=str(row["content"]),
        metadata=_metadata_from_row(row["metadata"]),
    )


class PgChunkRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def ensure_schema(self) -> None:
        async with self._pool.connection() as conn:
            for statement in _schema_statements(_PREAMBLE_SQL):
                await conn.execute(statement)
            for statement in _schema_statements(_CHUNKS_SQL):
                await conn.execute(statement)

    async def get_paper(self, arxiv_id: str, version: str) -> PaperRecord | None:
        async with self._pool.connection() as conn:
            await register_vector_async(conn)
            cur = await conn.execute(_GET_PAPER_SQL, (arxiv_id, version))
            row = await cur.fetchone()
        if row is None:
            return None
        return _paper_from_row(row)

    async def paper_has_chunks(self, arxiv_id: str, version: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(_PAPER_HAS_CHUNKS_SQL, (arxiv_id, version))
            row = await cur.fetchone()
        if row is None:
            return False
        return bool(row["has_chunks"])

    async def upsert_paper_with_chunks(
        self,
        paper: PaperRecord,
        drafts: list[ChunkDraft],
        embeddings: list[list[float]],
    ) -> None:
        if len(drafts) != len(embeddings):
            raise ValueError(
                "drafts and embeddings must have the same length "
                f"({len(drafts)} != {len(embeddings)})"
            )
        rows = [
            (
                uuid4(),
                paper.arxiv_id,
                paper.version,
                index,
                draft.kind,
                draft.unit_id,
                draft.embedding_text,
                draft.content,
                Vector(embedding),
                Jsonb(_validated_metadata(draft.metadata)),
            )
            for index, (draft, embedding) in enumerate(zip(drafts, embeddings))
        ]
        async with self._pool.connection() as conn:
            await register_vector_async(conn)
            await conn.execute(
                _UPSERT_PAPER_SQL,
                (
                    paper.arxiv_id,
                    paper.version,
                    paper.title,
                    paper.year,
                    paper.url,
                    paper.categories,
                ),
            )
            await conn.execute(_DELETE_CHUNKS_SQL, (paper.arxiv_id, paper.version))
            if rows:
                async with conn.cursor() as cur:
                    await cur.executemany(_INSERT_CHUNK_SQL, rows)

    async def similarity_search(
        self,
        query_embedding: list[float],
        paper_keys: list[tuple[str, str]],
        k: int,
    ) -> list[ChunkRecord]:
        if not paper_keys:
            return []
        ids = [key[0] for key in paper_keys]
        vers = [key[1] for key in paper_keys]
        async with self._pool.connection() as conn:
            await register_vector_async(conn)
            cur = await conn.execute(
                _SIMILARITY_SEARCH_SQL,
                (ids, vers, Vector(query_embedding), k),
            )
            rows = await cur.fetchall()
        return [_chunk_from_row(row) for row in rows]

    async def list_chunks(
        self,
        paper_keys: list[tuple[str, str]],
    ) -> list[ChunkRecord]:
        if not paper_keys:
            return []
        ids = [key[0] for key in paper_keys]
        vers = [key[1] for key in paper_keys]
        async with self._pool.connection() as conn:
            await register_vector_async(conn)
            cur = await conn.execute(_LIST_CHUNKS_SQL, (ids, vers))
            rows = await cur.fetchall()
        return [_chunk_from_row(row) for row in rows]
