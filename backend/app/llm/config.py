from pydantic import BaseModel


class CoreConfig(BaseModel):
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "llama3.2"
    temperature: float = 0.1
    max_tokens: int = 2000
    request_timeout: float = 300.0
    # Timeout for the schema planner LLM call (seconds)
    planner_schema_timeout: float = 120.0
    # --- Ollama runtime tuning ---
    # How long Ollama keeps the model loaded in RAM after a request.
    # Ollama API accepts: duration string ("10m", "24h") OR an int (seconds,
    # negative = keep forever). String "-1" is rejected with HTTP 400 — must
    # be int. -1 = never unload → eliminates the 60-90s cold-reload cost
    # on the first query after long idle. Model occupies ~2GB RAM, fine for
    # our 13GB host.
    keep_alive: int | str = -1
    # LLM context window size (tokens)
    num_ctx: int = 4096