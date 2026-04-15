from pydantic import BaseModel


class CoreConfig(BaseModel):
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "llama3.2"
    embedding_model: str = "nomic-embed-text"
    temperature: float = 0.1
    max_tokens: int = 2000
    request_timeout: float = 300.0
    # Business context from the shell (e.g. "You are an online store assistant")
    business_prompt: str = ""
    # Language for responses
    language: str = "english"