"""GangQing unified configuration loading and validation.

Task 43.1: Configuration externalization with schema validation and fail-fast behavior.
All configuration values are loaded from environment variables or .env.local file.
Missing required configurations cause immediate failure with clear English error messages.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from gangqing.common.errors import AppError, ErrorCode


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        config_key: str | None = None,
        config_category: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.config_key = config_key
        self.config_category = config_category

    def to_structured_log(self) -> dict[str, Any]:
        """Return structured log entry for configuration errors."""
        return {
            "level": "ERROR",
            "code": self.code.value,
            "config_key": self.config_key,
            "config_category": self.config_category,
            "message": self.message,
            "stage": "startup",
            "status": "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def _new_request_id() -> str:
    return uuid.uuid4().hex


def _to_error_response_json(*, error: AppError, timestamp: str) -> str:
    payload = error.to_response().model_dump(by_alias=True)
    details = payload.get("details")
    if details is None:
        payload["details"] = {"timestamp": timestamp}
    elif isinstance(details, dict):
        payload["details"] = {**details, "timestamp": timestamp}
    return json.dumps(payload, ensure_ascii=False)


def _apply_deprecated_env_var_compat(env: dict[str, str]) -> list[dict[str, str]]:
    deprecated_to_new = {
        "PROVIDER_API_KEY": "GANGQING_PROVIDER_API_KEY",
        "PROVIDER_BASE_URL": "GANGQING_PROVIDER_BASE_URL",
        "PROVIDER_MODEL_ID": "GANGQING_PROVIDER_MODEL",
        "LLM_LLAMA_BASE_URL": "GANGQING_LLAMACPP_BASE_URL",
        "LLM_LLAMA_API_KEY": "GANGQING_LLAMACPP_API_KEY",
    }
    deprecated_in_use: list[dict[str, str]] = []
    for deprecated_key, new_key in deprecated_to_new.items():
        deprecated_val = (env.get(deprecated_key) or "").strip()
        if not deprecated_val:
            continue
        new_val = (env.get(new_key) or "").strip()
        if new_val:
            continue
        env[new_key] = deprecated_val
        deprecated_in_use.append({"deprecatedKey": deprecated_key, "newKey": new_key})

    return deprecated_in_use


def _build_missing_config_message(config_name: str, env_var: str) -> str:
    """Build English error message for missing required configuration."""
    return (
        f"Missing required configuration: {config_name}. "
        f"Please set {env_var} in .env.local or environment. "
        f"See .env.example for all available options."
    )


def _build_invalid_config_message(
    config_name: str, value: Any, expected_format: str, validation_error: str
) -> str:
    """Build English error message for invalid configuration value."""
    return (
        f"Invalid configuration value for {config_name}: {value}. "
        f"Expected format: {expected_format}. "
        f"Error: {validation_error}"
    )


def _build_type_error_message(
    config_name: str, expected_type: str, actual_type: str
) -> str:
    """Build English error message for configuration type error."""
    return (
        f"Configuration type error for {config_name}: "
        f"expected {expected_type}, got {actual_type}. "
        f"Please check .env.example for correct format."
    )


class GangQingConfig(BaseSettings):
    """Unified GangQing configuration aggregation.

    Loads configuration from environment variables and .env.local file.
    Priority: environment variables > .env.local > defaults

    Required configurations (fail-fast if missing):
    - GANGQING_DATABASE_URL: PostgreSQL connection URL
    - GANGQING_JWT_SECRET: JWT signing secret (required in production)
    """

    model_config = SettingsConfigDict(
        env_prefix="GANGQING_",
        extra="ignore",
        env_file_encoding="utf-8",
    )

    # Core settings
    env: str = Field(default="dev", description="Environment: dev/prod")
    service_name: str = Field(default="gangqing-api", description="Service name")
    build: str = Field(default="unknown", description="Build identifier")
    commit: str = Field(default="unknown", description="Git commit hash")

    # API settings
    api_host: str = Field(default="127.0.0.1", description="API bind address")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API port")
    cors_allow_origins: str = Field(default="", description="CORS allowed origins")

    # Required: Database configuration
    database_url: str = Field(default="", description="PostgreSQL connection URL (required)")

    # Security configuration
    jwt_secret: str = Field(default="", description="JWT signing secret (required in prod)")
    jwt_alg: str = Field(default="HS256", description="JWT algorithm")
    jwt_exp_hours: int = Field(default=8, ge=1, description="JWT expiration in hours")

    # Tool configuration
    tool_max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")
    tool_backoff_base_ms: int = Field(default=200, ge=0, description="Base backoff delay in ms")
    tool_backoff_multiplier: float = Field(default=2.0, ge=1.0, description="Backoff multiplier")
    tool_backoff_max_ms: int = Field(default=2000, ge=0, description="Maximum backoff delay in ms")
    tool_backoff_jitter_ratio: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Jitter ratio for backoff"
    )
    tool_default_timeout_seconds: float = Field(
        default=10.0, gt=0, description="Default tool timeout in seconds"
    )
    tool_max_timeout_seconds: float = Field(
        default=60.0, gt=0, description="Maximum tool timeout in seconds"
    )
    postgres_tool_default_timeout_seconds: float = Field(
        default=5.0, gt=0, description="Postgres tool default timeout"
    )
    postgres_tool_max_timeout_seconds: float = Field(
        default=30.0, gt=0, description="Postgres tool maximum timeout"
    )

    # LLM configuration
    llamacpp_base_url: str = Field(default="", description="llama.cpp base URL")
    llamacpp_api_key: str = Field(default="", description="llama.cpp API key")
    llamacpp_timeout_seconds: float = Field(
        default=10.0, gt=0, le=120, description="llama.cpp timeout"
    )
    llamacpp_max_concurrency: int = Field(
        default=4, ge=1, le=128, description="Maximum concurrent requests"
    )
    llamacpp_models_path: str = Field(default="/models", description="llama.cpp models path")
    llamacpp_trust_env: bool = Field(default=False, description="Trust env proxy for llama.cpp")

    # Provider configuration
    provider_base_url: str = Field(default="", description="Provider fallback base URL")
    provider_api_key: str = Field(default="", description="Provider API key")
    provider_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    provider_trust_env: bool = Field(default=False)
    provider_model: str = Field(default="", description="Provider model name")

    # Audit configuration
    audit_async_enabled: bool = Field(default=False, description="Enable async audit writing")
    audit_async_max_workers: int = Field(default=4, ge=1, le=64, description="Async worker pool size")

    # Observability configuration
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format: json or console")
    healthcheck_cache_ttl_seconds: int = Field(
        default=0, ge=0, description="Health check response cache TTL"
    )

    # Isolation configuration
    isolation_enabled: bool = Field(default=True, description="Enable tenant isolation")
    isolation_extra_dimensions: str = Field(default="", description="Additional isolation dimensions")

    # Masking configuration
    masking_default_action: str = Field(default="mask", description="Default masking action")
    masking_audit_include_policy_hits: bool = Field(default=True, description="Include policy hits in audit")
    masking_policy_required: bool = Field(default=False, description="Require masking policy")
    masking_policy_json: str = Field(default="", description="Masking policy JSON")

    # Guardrail configuration
    guardrail_policy_required: bool = Field(default=False, description="Require guardrail policy")
    guardrail_policy_json: str = Field(default="", description="Guardrail policy JSON")

    # Contract validation
    contract_validation_strict: bool = Field(default=False)
    contract_validation_max_errors: int = Field(default=20, ge=1, le=200)

    # Tool registry
    tool_registry_enabled: bool = Field(default=True)
    tool_enabled_list: str = Field(default="")
    tool_disabled_list: str = Field(default="")

    # Bootstrap
    bootstrap_admin_user_id: str = Field(default="")
    bootstrap_admin_password: str = Field(default="")
    bootstrap_finance_user_id: str = Field(default="")
    bootstrap_finance_password: str = Field(default="")

    # Data quality
    data_quality_expected_interval_seconds: int = Field(default=60)
    data_quality_anomaly_method: str = Field(default="zscore")
    data_quality_anomaly_z_threshold: float = Field(default=3.0)

    # Connectors
    connectors_check_timeout_seconds: float = Field(default=0.5)

    # Seed data
    seed: int = Field(default=42)
    tenant_id: str = Field(default="t1")
    project_id: str = Field(default="p1")
    seed_start_date: str = Field(default="2026-02-01")
    seed_days: int = Field(default=14)

    @field_validator("database_url", mode="before")
    @classmethod
    def _validate_database_url(cls, v: Any) -> str:
        """Validate database URL - required configuration."""
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_MISSING,
                message=_build_missing_config_message("DATABASE_URL", "GANGQING_DATABASE_URL"),
                config_key="GANGQING_DATABASE_URL",
                config_category="database",
            )
        url = str(v).strip()
        if not url.startswith("postgresql"):
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "DATABASE_URL",
                    url,
                    "postgresql+psycopg://user:password@host:port/database",
                    "URL must start with postgresql",
                ),
                config_key="GANGQING_DATABASE_URL",
                config_category="database",
            )
        return url

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _validate_jwt_secret(cls, v: Any, info) -> str:
        """Validate JWT secret - required in production."""
        value = str(v or "").strip()
        # Get env from already validated data
        env = info.data.get("env", "dev") if hasattr(info, 'data') else "dev"
        # In production, JWT secret is required
        if not value and env == "prod":
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_MISSING,
                message=_build_missing_config_message("JWT_SECRET", "GANGQING_JWT_SECRET"),
                config_key="GANGQING_JWT_SECRET",
                config_category="security",
            )
        if value and len(value) < 16:
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "JWT_SECRET",
                    "[REDACTED]",
                    "at least 16 characters",
                    f"secret length is {len(value)}, minimum is 16",
                ),
                config_key="GANGQING_JWT_SECRET",
                config_category="security",
            )
        return value if value else "dev-secret-change-me-in-production"

    @field_validator("jwt_alg", mode="before")
    @classmethod
    def _validate_jwt_alg(cls, v: Any) -> str:
        """Validate JWT algorithm."""
        value = str(v or "HS256").strip().upper()
        allowed = {"HS256", "HS384", "HS512"}
        if value not in allowed:
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "JWT_ALG", value, "HS256/HS384/HS512", f"algorithm '{value}' not supported"
                ),
                config_key="GANGQING_JWT_ALG",
                config_category="security",
            )
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, v: Any) -> str:
        """Validate log level."""
        value = str(v or "INFO").strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if value not in allowed:
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "LOG_LEVEL", value, "DEBUG/INFO/WARNING/ERROR/CRITICAL", "invalid log level"
                ),
                config_key="GANGQING_LOG_LEVEL",
                config_category="observability",
            )
        return value

    @field_validator("log_format", mode="before")
    @classmethod
    def _validate_log_format(cls, v: Any) -> str:
        """Validate log format."""
        value = str(v or "json").strip().lower()
        allowed = {"json", "console"}
        if value not in allowed:
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "LOG_FORMAT", value, "json/console", "invalid log format"
                ),
                config_key="GANGQING_LOG_FORMAT",
                config_category="observability",
            )
        return value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _validate_cors_origins(cls, v: Any) -> str:
        """Validate CORS origins."""
        value = str(v or "").strip()
        if not value:
            return ""
        origins = [item.strip() for item in value.split(",") if item.strip()]
        normalized = []
        for origin in origins:
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ConfigValidationError(
                    code=ErrorCode.CONFIG_INVALID,
                    message=_build_invalid_config_message(
                        "CORS_ALLOW_ORIGINS",
                        origin,
                        "http://host:port or https://host:port",
                        "origin must start with http:// or https://",
                    ),
                    config_key="GANGQING_CORS_ALLOW_ORIGINS",
                    config_category="api",
                )
            normalized.append(origin.rstrip("/"))
        return ",".join(normalized)

    @field_validator("tool_max_timeout_seconds")
    @classmethod
    def _validate_max_timeout(cls, v: float, info) -> float:
        """Validate max timeout >= default timeout."""
        data = info.data if hasattr(info, 'data') else {}
        default_timeout = data.get("tool_default_timeout_seconds")
        if default_timeout is not None and v < default_timeout:
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "TOOL_MAX_TIMEOUT_SECONDS",
                    v,
                    f">= TOOL_DEFAULT_TIMEOUT_SECONDS ({default_timeout})",
                    "max timeout must be >= default timeout",
                ),
                config_key="GANGQING_TOOL_MAX_TIMEOUT_SECONDS",
                config_category="tool",
            )
        return v

    @field_validator("llamacpp_base_url", mode="before")
    @classmethod
    def _validate_llamacpp_url(cls, v: Any) -> str:
        """Validate llama.cpp base URL format."""
        value = str(v or "").strip()
        if not value:
            return ""
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "LLAMACPP_BASE_URL",
                    value,
                    "http://host:port or https://host:port",
                    "URL must start with http:// or https://",
                ),
                config_key="GANGQING_LLAMACPP_BASE_URL",
                config_category="llm",
            )
        return value.rstrip("/")

    @field_validator("masking_default_action", mode="before")
    @classmethod
    def _validate_masking_action(cls, v: Any) -> str:
        """Validate masking default action."""
        value = str(v or "mask").strip().lower()
        allowed = {"mask", "allow", "deny"}
        if value not in allowed:
            raise ConfigValidationError(
                code=ErrorCode.CONFIG_INVALID,
                message=_build_invalid_config_message(
                    "MASKING_DEFAULT_ACTION",
                    value,
                    "mask/allow/deny",
                    "invalid masking action",
                ),
                config_key="GANGQING_MASKING_DEFAULT_ACTION",
                config_category="security",
            )
        return value


def _load_dotenv_file(path: Path) -> None:
    """Load environment variables from .env.local file.

    Only loads keys that are not already set in environment.
    This ensures environment variables take priority over .env.local.

    Skips loading if GANGQING_SKIP_DOTENV=1 is set (useful for testing).
    """
    # Skip dotenv loading in test mode
    if os.environ.get("GANGQING_SKIP_DOTENV") == "1":
        return

    if not path.exists() or not path.is_file():
        return

    preexisting_keys = set(os.environ.keys())
    parsed_values: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        # Remove surrounding quotes if present
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        parsed_values[key] = value

    # Only set keys that are not already in environment
    for key, value in parsed_values.items():
        if key in preexisting_keys:
            continue
        os.environ[key] = value


def _get_project_root() -> Path:
    """Get project root directory (2 levels up from this file)."""
    return Path(__file__).resolve().parents[2]


# Module-level cache for configuration instance
_config_instance: GangQingConfig | None = None


def get_config() -> GangQingConfig:
    """Get the global configuration instance (singleton).

    This function loads configuration from environment variables and .env.local file.
    On first call, it validates all configurations and fails fast if required
    configurations are missing.

    Returns:
        GangQingConfig: Validated configuration instance

    Raises:
        ConfigValidationError: If required configuration is missing or invalid
        SystemExit: On configuration failure, exits with code 1
    """
    global _config_instance

    if _config_instance is None:
        try:
            # Load .env.local first (lowest priority after defaults)
            project_root = _get_project_root()
            _load_dotenv_file(project_root / ".env.local")

            deprecated_in_use = _apply_deprecated_env_var_compat(os.environ)
            if deprecated_in_use:
                warning = {
                    "level": "WARNING",
                    "code": ErrorCode.CONFIG_DEPRECATED.value,
                    "message": "Deprecated configuration keys detected. Please migrate to the new keys.",
                    "details": {"deprecated": deprecated_in_use, "stage": "startup"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                print(json.dumps(warning, ensure_ascii=False), file=sys.stderr)

            # Build and validate configuration
            _config_instance = GangQingConfig()

        except ConfigValidationError as e:
            request_id = _new_request_id()
            timestamp = datetime.now(timezone.utc).isoformat()
            app_error = AppError(
                e.code,
                e.message,
                request_id=request_id,
                retryable=False,
                details={
                    "configKey": e.config_key,
                    "configCategory": e.config_category,
                    "stage": "startup",
                },
            )
            print(_to_error_response_json(error=app_error, timestamp=timestamp), file=sys.stderr)
            sys.exit(1)

        except ValidationError as e:
            request_id = _new_request_id()
            timestamp = datetime.now(timezone.utc).isoformat()
            field_errors: list[dict[str, str]] = []
            for item in e.errors():
                loc = item.get("loc", ())
                path = ".".join(str(x) for x in loc) if loc else "unknown"
                msg = str(item.get("msg") or "Unknown validation error")
                field_errors.append({"path": path, "reason": msg})
            app_error = AppError(
                ErrorCode.CONFIG_INVALID,
                "Configuration validation failed.",
                request_id=request_id,
                retryable=False,
                details={
                    "stage": "startup",
                    "fieldErrors": field_errors,
                    "errorCount": len(e.errors()),
                },
            )
            print(_to_error_response_json(error=app_error, timestamp=timestamp), file=sys.stderr)
            sys.exit(1)

        except Exception as e:
            request_id = _new_request_id()
            timestamp = datetime.now(timezone.utc).isoformat()
            app_error = AppError(
                ErrorCode.CONFIG_INVALID,
                "Unexpected error during configuration loading.",
                request_id=request_id,
                retryable=False,
                details={"stage": "startup", "errorClass": type(e).__name__},
            )
            print(_to_error_response_json(error=app_error, timestamp=timestamp), file=sys.stderr)
            sys.exit(1)

    return _config_instance


def reset_config() -> None:
    """Reset configuration cache. Useful for testing."""
    global _config_instance
    _config_instance = None


# Convenience accessors for common configurations
def get_database_url() -> str:
    """Get database URL from configuration."""
    return get_config().database_url


def get_jwt_secret() -> str:
    """Get JWT secret from configuration."""
    return get_config().jwt_secret


def get_jwt_settings() -> dict[str, Any]:
    """Get JWT settings as a dictionary."""
    cfg = get_config()
    return {
        "secret": cfg.jwt_secret,
        "algorithm": cfg.jwt_alg,
        "exp_hours": cfg.jwt_exp_hours,
    }


if __name__ == "__main__":
    # CLI validation: python -m gangqing.config
    # This triggers configuration loading and validation
    try:
        config = get_config()
        print(f"Configuration loaded successfully: env={config.env}")
        print(f"  Database: [REDACTED]")
        print(f"  API: {config.api_host}:{config.api_port}")
        print(f"  Log level: {config.log_level}")
    except SystemExit:
        raise
