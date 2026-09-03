"""LangChain EnsembleRetriever hybrid adapter (RETR-01)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from plan_based_researcher.policy import Policy
from plan_based_researcher.ports.chunks import ChunkRecord, ChunkRepository
from plan_based_researcher.ports.embeddings import EmbeddingPort


@dataclass(frozen=True, slots=True)
class HybridResult:
    ranked: list[ChunkRecord]
    corpus: list[ChunkRecord]


class HybridRetrievePort(Protocol):
    async def retrieve(
        self,
        query: str,
        paper_keys: list[tuple[str, str]],
        k: int,
    ) -> HybridResult: ...


def _to_document(chunk: ChunkRecord) -> Document:
    return Document(
        page_content=chunk.content,
        metadata={
            "chunk_id": chunk.chunk_id,
            "kind": chunk.kind,
            "unit_id": chunk.unit_id,
            "metadata": chunk.metadata,
            "arxiv_id": chunk.arxiv_id,
            "version": chunk.version,
            "title": chunk.title,
            "year": chunk.year,
            "url": chunk.url,
        },
    )


def _from_document(doc: Document) -> ChunkRecord:
    metadata = doc.metadata
    unit_id = metadata["unit_id"]
    return ChunkRecord(
        chunk_id=str(metadata["chunk_id"]),
        arxiv_id=str(metadata["arxiv_id"]),
        version=str(metadata["version"]),
        title=str(metadata["title"]),
        year=int(metadata["year"]),
        url=str(metadata["url"]),
        kind=cast(Literal["prose", "table", "equation"], str(metadata["kind"])),
        unit_id=None if unit_id is None else str(unit_id),
        content=doc.page_content,
        metadata=dict(metadata["metadata"]),
    )


class _VectorRetriever(BaseRetriever):
    """BaseRetriever wrapping ChunkRepository.similarity_search."""

    chunks: Any
    embeddings: Any
    paper_keys: list[tuple[str, str]]
    k: int

    def _get_relevant_documents(self, query: str) -> list[Document]:
        raise NotImplementedError("vector retriever is async-only")

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        query_embedding = await self.embeddings.embed_query(query)
        found = await self.chunks.similarity_search(
            query_embedding, self.paper_keys, self.k
        )
        return [_to_document(chunk) for chunk in found]


class HybridRetrieveAdapter:
    """HybridRetrievePort backed by EnsembleRetriever (vector 0.7 + BM25 0.3)."""

    def __init__(self, chunks: ChunkRepository, embeddings: EmbeddingPort) -> None:
        self._chunks = chunks
        self._embeddings = embeddings

    async def retrieve(
        self,
        query: str,
        paper_keys: list[tuple[str, str]],
        k: int,
    ) -> HybridResult:
        if not paper_keys:
            return HybridResult([], [])
        corpus = await self._chunks.list_chunks(paper_keys)
        if not corpus:
            return HybridResult([], [])
        vector = _VectorRetriever(
            chunks=self._chunks,
            embeddings=self._embeddings,
            paper_keys=paper_keys,
            k=k,
        )
        bm25 = BM25Retriever.from_documents(
            [_to_document(chunk) for chunk in corpus],
            k=k,
        )
        ensemble = EnsembleRetriever(
            retrievers=[vector, bm25],
            weights=[Policy.hybrid_vector_weight, Policy.hybrid_lexical_weight],
            id_key="chunk_id",
        )
        ranked = await ensemble.ainvoke(query)
        return HybridResult(
            ranked=[_from_document(doc) for doc in ranked],
            corpus=corpus,
        )
