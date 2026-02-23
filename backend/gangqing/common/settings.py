from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GangQingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GANGQING_", extra="ignore")

    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000, ge=1, le=65535)

    jwt_secret: str = Field(default="dev-secret-change-me")
    jwt_alg: str = Field(default="HS256")
    jwt_exp_hours: int = Field(default=8, ge=1)

    bootstrap_admin_user_id: str = Field(default="")
    bootstrap_admin_password: str = Field(default="")
    bootstrap_finance_user_id: str = Field(default="")
    bootstrap_finance_password: str = Field(default="")

    audit_async_enabled: bool = Field(default=False)
    audit_async_max_workers: int = Field(default=4, ge=1, le=64)

    postgres_tool_default_timeout_seconds: float = Field(default=5.0, gt=0)
    postgres_tool_max_timeout_seconds: float = Field(default=30.0, gt=0)

    isolation_enabled: bool = Field(default=True)
    isolation_extra_dimensions: str = Field(default="")

    masking_default_action: str = Field(default="mask")
    masking_audit_include_policy_hits: bool = Field(default=True)
    masking_policy_required: bool = Field(default=False)
    masking_policy_json: str = Field(default="")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        value = (v or "").strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if value not in allowed:
            raise ValueError("Invalid log level. Allowed: DEBUG/INFO/WARNING/ERROR/CRITICAL")
        return value

    @field_validator("masking_default_action")
    @classmethod
    def validate_masking_default_action(cls, v: str) -> str:
        value = (v or "").strip().lower()
        allowed = {"mask", "allow", "deny"}
        if value not in allowed:
            raise ValueError("Invalid masking default action. Allowed: mask/allow/deny")
        return value

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        value = (v or "").strip().lower()
        allowed = {"json", "console"}
        if value not in allowed:
            raise ValueError("Invalid log format. Allowed: json/console")
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Missing JWT secret")
        if len(value) < 16:
            raise ValueError("JWT secret too short")
        return value

    @field_validator("jwt_alg")
    @classmethod
    def validate_jwt_alg(cls, v: str) -> str:
        value = (v or "").strip().upper()
        if value != "HS256":
            raise ValueError("Unsupported JWT algorithm")
        return value

    @field_validator("postgres_tool_max_timeout_seconds")
    @classmethod
    def validate_postgres_tool_timeout_bounds(cls, v: float, info) -> float:
        default_timeout = info.data.get("postgres_tool_default_timeout_seconds")
        if default_timeout is not None and v < float(default_timeout):
            raise ValueError("postgres_tool_max_timeout_seconds must be >= default")
        return float(v)


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


def load_settings() -> GangQingSettings:
    project_root = Path(__file__).resolve().parents[3]
    _load_dotenv_file(project_root / ".env.local")
    return GangQingSettings()
