from langchain_voyageai import VoyageAIEmbeddings
from plan_based_researcher.ports.embeddings import EmbeddingPort  # structural only

EMBEDDING_MODEL_ID = "voyage-4-large"


class VoyageEmbeddingAdapter:
    def __init__(self, api_key: str | None = None) -> None:
        kwargs = {"model": EMBEDDING_MODEL_ID, "truncation": True}
        if api_key is not None:
            kwargs["api_key"] = api_key
        self._embeddings = VoyageAIEmbeddings(**kwargs)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embeddings.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self._embeddings.aembed_query(text)
