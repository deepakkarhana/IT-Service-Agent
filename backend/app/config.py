"""Runtime configuration.

Everything that could differ between machines (paths, LLM credentials) is read
from environment variables. No secret is ever hardcoded here.
"""

from __future__ import annotations

import os
from pathlib import Path

# <repo>/backend/app/config.py -> parents[2] == <repo>
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data"))
RUNTIME_DIR = DATA_DIR / "runtime"


def _load_dotenv() -> None:
    """Minimal .env loader so the project works without extra dependencies."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Real environment variables always win over the .env file.
        os.environ.setdefault(key, value)


_load_dotenv()


class Settings:
    """Small settings object, read once at import time."""

    llm_api_key: str = os.getenv("LLM_API_KEY", "").strip()
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    llm_base_url: str = os.getenv(
        "LLM_BASE_URL", "https://api.openai.com/v1"
    ).strip().rstrip("/")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "12"))

    @property
    def llm_enabled(self) -> bool:
        """LLM mode is only possible when an API key was supplied."""
        return bool(self.llm_api_key)


settings = Settings()
