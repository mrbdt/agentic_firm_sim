from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FIRM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Paths
    sqlite_path: str = Field(default="./data/firm.db", alias="SQLITE_PATH")
    agents_config: str = Field(default="./configs/agents.yaml", alias="AGENTS_CONFIG")

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    # Runtime
    llm_max_concurrency: int = Field(default=2, alias="LLM_MAX_CONCURRENCY")
    bus_ring_size: int = Field(default=500, alias="BUS_RING_SIZE")
    persist_flush_interval_s: float = Field(default=0.5, alias="PERSIST_FLUSH_INTERVAL_S")

    # Risk limits (USD)
    max_position_usd: float = Field(default=5_000.0, alias="MAX_POSITION_USD")
    max_gross_exposure_usd: float = Field(default=20_000.0, alias="MAX_GROSS_EXPOSURE_USD")


class AlpacaSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALPACA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    paper: bool = Field(default=True, alias="PAPER")
    key_id: str | None = Field(default=None, alias="KEY_ID")
    secret_key: str | None = Field(default=None, alias="SECRET_KEY")
    base_url: str = Field(default="https://paper-api.alpaca.markets", alias="BASE_URL")
    data_url: str = Field(default="https://data.alpaca.markets", alias="DATA_URL")


settings = Settings()
alpaca_settings = AlpacaSettings()
