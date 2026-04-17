from pydantic import BaseModel


class CoreConfig(BaseModel):
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "llama3.2"
    temperature: float = 0.1
    max_tokens: int = 2000
    request_timeout: float = 300.0
    # Business context from the shell (e.g. "You are an online store assistant")
    business_prompt: str = ""
    # Language for responses
    language: str = "english"
    # --- pipeline mode ---
    # True  -> Schema Router pipeline (single LLM call w/ JSON Schema)
    # False -> legacy native tool-calling loop (kept for A/B benchmarking)
    use_structured_output: bool = True
    # How many last user+assistant messages to keep in LLM context (tool role excluded)
    history_max_messages: int = 4
    # Timeout for the schema planner LLM call (seconds)
    planner_schema_timeout: float = 120.0
    # --- Ollama runtime tuning ---
    # How long Ollama keeps the model loaded in RAM after a request
    keep_alive: str = "10m"
    # LLM context window size (tokens)
    num_ctx: int = 4096