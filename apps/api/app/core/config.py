from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env", "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    web_origin: str = "http://localhost:3000"
    storage_backend: Literal["memory", "postgres"] = "memory"
    database_url: str = "postgresql://qaagent:qaagent@localhost:5432/qaagent"
    paper_storage_dir: str = "storage/pdfs"

    openalex_mailto: str | None = None
    crossref_mailto: str | None = None
    semantic_scholar_api_key: str | None = None
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4.1-mini"

    request_timeout_seconds: float = 18.0
    max_search_results_per_source: int = 12
    max_answer_context_chunks: int = 6
    embedding_dimensions: int = Field(default=384, ge=64, le=2048)

    @computed_field
    @property
    def storage_path(self) -> Path:
        path = Path(self.paper_storage_dir)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[4] / path
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
