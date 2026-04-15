from core.llm.base import LLMProvider


class OllamaEmbeddings:
    """Generates text embeddings via Ollama."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def embed(self, text: str) -> list[float]:
        return await self.llm.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self.llm.embed_batch(texts)
