from typing import Any, Protocol

from core.rag.embeddings import OllamaEmbeddings
from core.providers.base import DataProvider


class SemanticRetriever(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]: ...


class EmbeddingRetriever:
    """Retrieves similar products using embeddings + vector similarity."""

    def __init__(self, embeddings: OllamaEmbeddings, provider: DataProvider):
        self.embeddings = embeddings
        self.provider = provider

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = await self.embeddings.embed(query)
        return await self.provider.search_similar(query_embedding, limit=limit)
