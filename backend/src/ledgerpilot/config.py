"""Settings from environment variables (and ``.env`` at the repo root, if present).

Keys are only ever read from the environment, never logged or written to disk.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env", override=False)  # real env vars win over .env


@dataclass(frozen=True)
class Settings:
    llm_model: str
    llm_vision_model: str
    llm_min_interval_s: float
    llm_max_retries: int
    cache_dir: Path | None


def get_settings() -> Settings:
    model = os.getenv("LLM_MODEL") or "gemini/gemini-3.5-flash-lite"
    cache = os.getenv("LLM_CACHE_DIR", str(REPO_ROOT / ".cache" / "llm"))
    return Settings(
        llm_model=model,
        llm_vision_model=os.getenv("LLM_VISION_MODEL") or model,
        llm_min_interval_s=float(os.getenv("LLM_MIN_INTERVAL_S", "0")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        cache_dir=None if cache.lower() in ("", "off", "none") else Path(cache),
    )
