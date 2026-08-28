from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://lia:lia@localhost:5433/lia"
    storage_dir: str = "./storage"

    # --- providers -------------------------------------------------------
    # embeddings: "openai" (text-embedding-3-large @1024) or "local" (BAAI/bge-m3)
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-large"
    embedding_dim: int = 1024

    llm_provider: str = "anthropic"          # anthropic | openai
    llm_model: str = "claude-sonnet-4-5"
    judge_model: str = "claude-haiku-4-5"    # cheap model for verification/eval

    openai_api_key: str | None = None
    openai_base_url: str | None = None   # set for Gemini/Groq/OpenRouter
    anthropic_api_key: str | None = None

    # --- retrieval knobs (recorded in every eval run) --------------------
    candidates_per_arm: int = 40   # top-N from vector arm and keyword arm
    rrf_k: int = 60
    rerank_enabled: bool = True
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    top_k: int = 6                 # chunks handed to the generator
    chunk_target_tokens: int = 320
    chunk_overlap_tokens: int = 60

    whisper_model: str = "small"
    whisper_compute_type: str = "int8"


@lru_cache
def settings() -> Settings:
    return Settings()
