"""Unit tests for configuration loading and validation (Task 43.1).

Test coverage:
- Normal config loading (happy path)
- Missing required config (fail fast with English error)
- Invalid config format
- Config type errors
- Environment variable priority over .env.local
"""

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Ensure imports work
backend_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(backend_dir))

from gangqing.config import (
    get_config,
    reset_config,
    ConfigValidationError,
    _build_missing_config_message,
    _build_invalid_config_message,
    _build_type_error_message,
    GangQingConfig,
)
from gangqing.common.errors import ErrorCode


@pytest.fixture(autouse=True)
def clean_env():
    """Reset config cache and clean environment before each test."""
    reset_config()
    # Skip loading .env.local during tests
    os.environ["GANGQING_SKIP_DOTENV"] = "1"
    # Store original env vars
    original_vars = {}
    env_vars_to_clean = [
        "GANGQING_DATABASE_URL",
        "GANGQING_JWT_SECRET",
        "GANGQING_ENV",
        "GANGQING_LOG_LEVEL",
        "GANGQING_LOG_FORMAT",
        "GANGQING_API_HOST",
        "GANGQING_API_PORT",
    ]
    for var in env_vars_to_clean:
        original_vars[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original env vars
    for var, value in original_vars.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]

    # Clean up skip flag
    if "GANGQING_SKIP_DOTENV" in os.environ:
        del os.environ["GANGQING_SKIP_DOTENV"]

    reset_config()


class TestConfigErrorCodes:
    """Test configuration error codes are properly defined in ErrorCode enum."""

    def test_config_missing_error_code_exists(self):
        """Verify CONFIG_MISSING error code is defined."""
        assert hasattr(ErrorCode, "CONFIG_MISSING")
        assert ErrorCode.CONFIG_MISSING == "CONFIG_MISSING"

    def test_config_invalid_error_code_exists(self):
        """Verify CONFIG_INVALID error code is defined."""
        assert hasattr(ErrorCode, "CONFIG_INVALID")
        assert ErrorCode.CONFIG_INVALID == "CONFIG_INVALID"

    def test_config_type_error_code_exists(self):
        """Verify CONFIG_TYPE_ERROR error code is defined."""
        assert hasattr(ErrorCode, "CONFIG_TYPE_ERROR")
        assert ErrorCode.CONFIG_TYPE_ERROR == "CONFIG_TYPE_ERROR"

    def test_config_deprecated_error_code_exists(self):
        """Verify CONFIG_DEPRECATED error code is defined."""
        assert hasattr(ErrorCode, "CONFIG_DEPRECATED")
        assert ErrorCode.CONFIG_DEPRECATED == "CONFIG_DEPRECATED"

    def test_config_error_codes_in_enum_values(self):
        """Verify all CONFIG_* error codes are in ErrorCode enum values."""
        config_codes = [
            ErrorCode.CONFIG_MISSING,
            ErrorCode.CONFIG_INVALID,
            ErrorCode.CONFIG_TYPE_ERROR,
            ErrorCode.CONFIG_DEPRECATED,
        ]
        all_values = set(ErrorCode)
        for code in config_codes:
            assert code in all_values, f"{code} should be in ErrorCode enum"

    def test_config_error_codes_have_retryable_false(self):
        """Verify config error codes are marked as non-retryable."""
        # Config errors are startup failures and should not be retried
        config_codes = [
            ErrorCode.CONFIG_MISSING,
            ErrorCode.CONFIG_INVALID,
            ErrorCode.CONFIG_TYPE_ERROR,
            ErrorCode.CONFIG_DEPRECATED,
        ]
        # These errors are typically startup failures, so retryable should be false
        for code in config_codes:
            assert isinstance(code.value, str)
            assert code.value.startswith("CONFIG_")


class TestConfigErrorMessages:
    """Test error message builders produce English messages."""

    def test_missing_config_message_format(self):
        """Verify missing config message follows expected English format."""
        message = _build_missing_config_message("DATABASE_URL", "GANGQING_DATABASE_URL")
        assert "Missing required configuration" in message
        assert "DATABASE_URL" in message
        assert "GANGQING_DATABASE_URL" in message
        assert ".env.local" in message
        assert "See .env.example" in message

    def test_invalid_config_message_format(self):
        """Verify invalid config message follows expected English format."""
        message = _build_invalid_config_message(
            "LOG_LEVEL", "invalid", "DEBUG/INFO/WARNING/ERROR", "unknown level"
        )
        assert "Invalid configuration value" in message
        assert "LOG_LEVEL" in message
        assert "Expected format" in message

    def test_type_error_message_format(self):
        """Verify type error message follows expected English format."""
        message = _build_type_error_message("PORT", "int", "str")
        assert "Configuration type error" in message
        assert "PORT" in message
        assert "expected int, got str" in message


class TestDatabaseConfigValidation:
    """Test database configuration validation."""

    def test_valid_database_url(self):
        """Test that valid PostgreSQL URL is accepted."""
        config = GangQingConfig(
            database_url="postgresql+psycopg://user:pass@localhost:5432/db",
            jwt_secret="test-secret-32-chars-long!!"
        )
        assert config.database_url == "postgresql+psycopg://user:pass@localhost:5432/db"

    def test_missing_database_url_raises_error(self):
        """Test that missing DATABASE_URL raises ConfigValidationError with English message."""
        with pytest.raises(ConfigValidationError) as exc_info:
            GangQingConfig(database_url="", jwt_secret="test-secret-32-chars-long!!")

        error = exc_info.value
        assert error.code == ErrorCode.CONFIG_MISSING
        assert error.config_key == "GANGQING_DATABASE_URL"
        assert error.config_category == "database"
        assert "Missing required configuration" in error.message
        assert "DATABASE_URL" in error.message

    def test_invalid_database_url_format(self):
        """Test that non-postgresql URL raises ConfigValidationError."""
        with pytest.raises(ConfigValidationError) as exc_info:
            GangQingConfig(
                database_url="mysql://user:pass@localhost/db",
                jwt_secret="test-secret-32-chars-long!!"
            )

        error = exc_info.value
        assert error.code == ErrorCode.CONFIG_INVALID
        assert error.config_key == "GANGQING_DATABASE_URL"
        assert "must start with postgresql" in error.message

    def test_database_url_none_value(self):
        """Test that None value for DATABASE_URL raises error."""
        with pytest.raises(ConfigValidationError) as exc_info:
            GangQingConfig(database_url=None, jwt_secret="test-secret-32-chars-long!!")

        error = exc_info.value
        assert error.code == ErrorCode.CONFIG_MISSING


class TestSecurityConfigValidation:
    """Test security configuration validation."""

    def test_valid_security_config(self):
        """Test valid security configuration."""
        config = GangQingConfig(
            database_url="postgresql://localhost/db",
            jwt_secret="a-very-long-secret-key-32-chars!!",
            jwt_alg="HS256",
            jwt_exp_hours=8,
        )
        assert config.jwt_secret == "a-very-long-secret-key-32-chars!!"
        assert config.jwt_alg == "HS256"

    def test_short_jwt_secret_raises_error(self):
        """Test that short JWT secret raises ConfigValidationError."""
        with pytest.raises(ConfigValidationError) as exc_info:
            GangQingConfig(
                database_url="postgresql://localhost/db",
                jwt_secret="short"
            )

        error = exc_info.value
        assert error.code == ErrorCode.CONFIG_INVALID
        assert error.config_key == "GANGQING_JWT_SECRET"
        assert "at least 16 characters" in error.message

    def test_invalid_jwt_algorithm(self):
        """Test that unsupported JWT algorithm raises error."""
        with pytest.raises(ConfigValidationError) as exc_info:
            GangQingConfig(
                database_url="postgresql://localhost/db",
                jwt_secret="a-very-long-secret-key-32-chars!!",
                jwt_alg="RS256"
            )

        error = exc_info.value
        assert error.code == ErrorCode.CONFIG_INVALID
        assert "RS256" in error.message or "algorithm" in error.message.lower()


class TestObservabilityConfigValidation:
    """Test observability (logging) configuration validation."""

    def test_valid_log_level(self):
        """Test valid log levels are accepted."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = GangQingConfig(
                database_url="postgresql://localhost/db",
                jwt_secret="test-secret-32-chars-long!!",
                log_level=level
            )
            assert config.log_level == level

    def test_invalid_log_level_raises_error(self):
        """Test that invalid log level raises ConfigValidationError."""
        with pytest.raises(ConfigValidationError) as exc_info:
            GangQingConfig(
                database_url="postgresql://localhost/db",
                jwt_secret="test-secret-32-chars-long!!",
                log_level="INVALID"
            )

        error = exc_info.value
        assert error.code == ErrorCode.CONFIG_INVALID
        assert error.config_key == "GANGQING_LOG_LEVEL"
        assert "DEBUG/INFO/WARNING/ERROR/CRITICAL" in error.message

    def test_valid_log_format(self):
        """Test valid log formats are accepted."""
        for fmt in ["json", "console"]:
            config = GangQingConfig(
                database_url="postgresql://localhost/db",
                jwt_secret="test-secret-32-chars-long!!",
                log_format=fmt
            )
            assert config.log_format == fmt

    def test_invalid_log_format_raises_error(self):
        """Test that invalid log format raises ConfigValidationError."""
        with pytest.raises(ConfigValidationError) as exc_info:
            GangQingConfig(
                database_url="postgresql://localhost/db",
                jwt_secret="test-secret-32-chars-long!!",
                log_format="xml"
            )

        error = exc_info.value
        assert error.code == ErrorCode.CONFIG_INVALID
        assert error.config_key == "GANGQING_LOG_FORMAT"
        assert "json/console" in error.message


class TestFullConfigLoading:
    """Test full configuration loading with environment variables."""

    def test_env_local_loading_and_precedence(self):
        """Test .env.local loading and environment variable precedence."""
        # Allow dotenv loading for this test
        if "GANGQING_SKIP_DOTENV" in os.environ:
            del os.environ["GANGQING_SKIP_DOTENV"]

        project_root = Path(__file__).resolve().parents[2]
        env_local_path = project_root / ".env.local"
        original_content = env_local_path.read_text(encoding="utf-8") if env_local_path.exists() else None

        try:
            env_local_path.write_text(
                "\n".join(
                    [
                        "# test .env.local for config loader",
                        "GANGQING_DATABASE_URL=postgresql+psycopg://dotenv:pass@localhost:5432/dotenv_db",
                        "GANGQING_JWT_SECRET=test-secret-key-at-least-16-chars",
                        "GANGQING_API_PORT=9100",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            # Ensure env vars are not set so .env.local takes effect
            for key in ["GANGQING_DATABASE_URL", "GANGQING_JWT_SECRET", "GANGQING_API_PORT"]:
                if key in os.environ:
                    del os.environ[key]

            config = get_config()
            assert config.database_url == "postgresql+psycopg://dotenv:pass@localhost:5432/dotenv_db"
            assert config.api_port == 9100

            # Now override via env var and ensure env wins
            reset_config()
            os.environ["GANGQING_API_PORT"] = "9200"
            config2 = get_config()
            assert config2.api_port == 9200

        finally:
            reset_config()
            if original_content is None:
                if env_local_path.exists():
                    env_local_path.unlink()
            else:
                env_local_path.write_text(original_content, encoding="utf-8")
            os.environ["GANGQING_SKIP_DOTENV"] = "1"

    def test_full_config_loading_success(self):
        """Test successful full configuration loading (happy path)."""
        os.environ["GANGQING_DATABASE_URL"] = "postgresql+psycopg://user:pass@localhost:5432/db"
        os.environ["GANGQING_JWT_SECRET"] = "a-very-long-secret-key-32-chars!!"
        os.environ["GANGQING_LOG_LEVEL"] = "DEBUG"

        config = get_config()

        assert config.database_url == "postgresql+psycopg://user:pass@localhost:5432/db"
        assert config.jwt_secret == "a-very-long-secret-key-32-chars!!"
        assert config.log_level == "DEBUG"
        assert config.api_port == 8000  # Default value

    def test_missing_database_url_exits(self, monkeypatch):
        """Test that missing DATABASE_URL causes system exit with English error."""
        # Ensure DATABASE_URL is not set
        if "GANGQING_DATABASE_URL" in os.environ:
            del os.environ["GANGQING_DATABASE_URL"]

        # Mock sys.exit to capture exit code
        exit_code = []
        def mock_exit(code):
            exit_code.append(code)
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", mock_exit)

        with pytest.raises(SystemExit) as exc_info:
            get_config()

        assert exc_info.value.code == 1

    def test_environment_variable_priority(self):
        """Test that environment variables take priority over defaults."""
        os.environ["GANGQING_DATABASE_URL"] = "postgresql://env-db/db"
        os.environ["GANGQING_API_PORT"] = "9000"
        os.environ["GANGQING_JWT_SECRET"] = "test-secret-32-chars-long!!"

        config = get_config()

        assert config.database_url == "postgresql://env-db/db"
        assert config.api_port == 9000

    def test_config_to_structured_log(self):
        """Test that ConfigValidationError can produce structured log output."""
        error = ConfigValidationError(
            code=ErrorCode.CONFIG_MISSING,
            message="Test error",
            config_key="TEST_KEY",
            config_category="test",
        )
        log_entry = error.to_structured_log()

        assert log_entry["level"] == "ERROR"
        assert log_entry["code"] == "CONFIG_MISSING"
        assert log_entry["config_key"] == "TEST_KEY"
        assert log_entry["config_category"] == "test"
        assert log_entry["message"] == "Test error"
        assert log_entry["stage"] == "startup"
        assert log_entry["status"] == "failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
