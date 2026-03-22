from __future__ import annotations

from functools import lru_cache
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

    cors_allow_origins: str = Field(default="")

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

    tool_default_timeout_seconds: float = Field(default=10.0, gt=0)
    tool_max_timeout_seconds: float = Field(default=60.0, gt=0)

    tool_max_retries: int = Field(default=3, ge=0, le=3)
    tool_backoff_base_ms: int = Field(default=200, ge=0)
    tool_backoff_multiplier: float = Field(default=2.0, ge=1.0)
    tool_backoff_max_ms: int = Field(default=2000, ge=0)
    tool_backoff_jitter_ratio: float = Field(default=0.2, ge=0.0, le=1.0)

    tool_registry_enabled: bool = Field(default=True)
    tool_enabled_list: str = Field(default="")
    tool_disabled_list: str = Field(default="")

    llamacpp_base_url: str = Field(default="")
    llamacpp_api_key: str = Field(default="")
    llamacpp_models_path: str = Field(default="/models")
    llamacpp_timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    llamacpp_max_concurrency: int = Field(default=4, ge=1, le=128)
    llamacpp_trust_env: bool = Field(default=False)

    provider_base_url: str = Field(default="")
    provider_api_key: str = Field(default="")
    provider_timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    provider_trust_env: bool = Field(default=False)
    provider_model: str = Field(default="")

    contract_validation_strict: bool = Field(default=False)
    contract_validation_max_errors: int = Field(default=20, ge=1, le=200)

    isolation_enabled: bool = Field(default=True)
    isolation_extra_dimensions: str = Field(default="")

    masking_default_action: str = Field(default="mask")
    masking_audit_include_policy_hits: bool = Field(default=True)
    masking_policy_required: bool = Field(default=False)
    masking_policy_json: str = Field(default="")

    guardrail_policy_required: bool = Field(default=False)
    guardrail_policy_json: str = Field(default="")

    # Database configuration (required)
    database_url: str = Field(default="", description="PostgreSQL connection URL")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        value = (v or "").strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if value not in allowed:
            raise ValueError("Invalid log level. Allowed: DEBUG/INFO/WARNING/ERROR/CRITICAL")
        return value

    @field_validator("cors_allow_origins")
    @classmethod
    def validate_cors_allow_origins(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            return ""
        origins = [item.strip() for item in value.split(",") if item.strip()]
        normalized = []
        for origin in origins:
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError("Invalid cors_allow_origins entry: must start with http:// or https://")
            normalized.append(origin.rstrip("/"))
        return ",".join(normalized)

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

    @field_validator("llamacpp_base_url")
    @classmethod
    def validate_llamacpp_base_url(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            return ""
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("Invalid llamacpp_base_url: must start with http:// or https://")
        return value.rstrip("/")

    @field_validator("llamacpp_models_path")
    @classmethod
    def validate_llamacpp_models_path(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            return "/models"
        if not value.startswith("/"):
            value = "/" + value
        return value

    @field_validator("provider_base_url")
    @classmethod
    def validate_provider_base_url(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            return ""
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("Invalid provider_base_url: must start with http:// or https://")
        return value.rstrip("/")

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Missing required configuration: DATABASE_URL. Please set GANGQING_DATABASE_URL in .env.local or environment.")
        if not value.startswith("postgresql"):
            raise ValueError("Invalid DATABASE_URL: must start with postgresql://")
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

    @field_validator("tool_max_timeout_seconds")
    @classmethod
    def validate_tool_timeout_bounds(cls, v: float, info) -> float:
        default_timeout = info.data.get("tool_default_timeout_seconds")
        if default_timeout is not None and float(v) < float(default_timeout):
            raise ValueError("tool_max_timeout_seconds must be >= default")
        return float(v)

    @field_validator("tool_backoff_max_ms")
    @classmethod
    def validate_tool_backoff_bounds(cls, v: int, info) -> int:
        base = info.data.get("tool_backoff_base_ms")
        if base is not None and int(v) < int(base):
            raise ValueError("tool_backoff_max_ms must be >= tool_backoff_base_ms")
        return int(v)


def _load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    preexisting_keys = set(os.environ.keys())
    parsed_values: dict[str, str] = {}

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

        parsed_values[key] = value

    for key, value in parsed_values.items():
        if key in preexisting_keys:
            continue
        os.environ[key] = value


def reset_settings_cache() -> None:
    load_settings.cache_clear()


@lru_cache(maxsize=1)
def load_settings() -> GangQingSettings:
    project_root = Path(__file__).resolve().parents[3]
    _load_dotenv_file(project_root / ".env.local")
    return GangQingSettings()
