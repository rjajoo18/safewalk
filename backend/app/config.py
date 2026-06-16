from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: backend/app/config.py -> parents[2]. prebake.py writes the canonical
# scored parquet to <repo>/outputs/, so resolve that absolutely (CWD-independent).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SCORED_PATH = str(_REPO_ROOT / "outputs" / "scored_segments.parquet")


class Settings(BaseSettings):
    # extra="ignore": the .env also carries SUPABASE_* (read directly via os.environ
    # in layers/hazards.py), which would otherwise trip pydantic's extra_forbidden.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    mapbox_access_token: str = ""
    scored_segments_path: str = _DEFAULT_SCORED_PATH
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
