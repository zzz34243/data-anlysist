from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Local credentials live in .env, which is excluded by .gitignore.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "multi-agent-marketing")
    storage_path: Path = Path(os.getenv("STORAGE_PATH", "storage"))
    retention_days: int = int(os.getenv("RETENTION_DAYS", "7"))
    cleanup_interval_seconds: int = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "3600"))
    max_filter_rows: int = int(os.getenv("MAX_FILTER_ROWS", "5000"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "1"))
    max_excel_upload_mb: int = int(os.getenv("MAX_EXCEL_UPLOAD_MB", "100"))
    # LLM credentials are read only from the process environment. Never put
    # real keys in source control or in the frontend request body.
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")
    siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
    siliconflow_api_key_fallback: str = os.getenv("SILICONFLOW_API_KEY_FALLBACK", "")
    siliconflow_base_url: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    siliconflow_model: str = os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1800"))

    @property
    def database_path(self) -> Path:
        return Path(os.getenv("DATABASE_PATH", str(self.storage_path / "app.db")))

    def ensure_directories(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        for name in ("runs", "history", "charts", "reports", "logs"):
            (self.storage_path / name).mkdir(parents=True, exist_ok=True)


settings = Settings()
