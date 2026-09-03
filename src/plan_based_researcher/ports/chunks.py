"""Chunk persistence port: identity by (arxiv_id, version); RAG scoped to selected papers."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class PaperRecord:
    arxiv_id: str
    version: str
    title: str
    year: int
    url: str
    categories: list[str]


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    kind: Literal["prose", "table", "equation"]
    unit_id: str | None
    embedding_text: str
    content: str
    metadata: dict  # exactly section, caption, unit_ids


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_id: str
    arxiv_id: str
    version: str
    title: str
    year: int
    url: str
    kind: Literal["prose", "table", "equation"]
    unit_id: str | None
    content: str
    metadata: dict


class ChunkRepository(Protocol):
    async def get_paper(self, arxiv_id: str, version: str) -> PaperRecord | None: ...

    async def paper_has_chunks(self, arxiv_id: str, version: str) -> bool: ...

    async def upsert_paper_with_chunks(
        self,
        paper: PaperRecord,
        drafts: list[ChunkDraft],
        embeddings: list[list[float]],
    ) -> None: ...

    async def similarity_search(
        self,
        query_embedding: list[float],
        paper_keys: list[tuple[str, str]],
        k: int,
    ) -> list[ChunkRecord]: ...

    async def list_chunks(
        self,
        paper_keys: list[tuple[str, str]],
    ) -> list[ChunkRecord]: ...
