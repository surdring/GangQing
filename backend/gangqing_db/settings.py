from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GangQingDbSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GANGQING_", extra="ignore")

    database_url: str = Field(min_length=1)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("database_url must not be empty")
        value = v.strip()
        if not (
            value.startswith("postgresql://")
            or value.startswith("postgresql+psycopg://")
        ):
            raise ValueError(
                "database_url must start with 'postgresql://' or 'postgresql+psycopg://'"
            )
        return value


def _load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def load_settings() -> GangQingDbSettings:
    project_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(project_root / ".env.local")
    return GangQingDbSettings()
