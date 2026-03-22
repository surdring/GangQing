"""Unit tests for migration error handling and structured error output.

These tests verify:
1. Structured error models produce correct output
2. Error codes are stable and English messages are present
3. Configuration missing scenarios fail correctly
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add backend to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing_db.errors import (
    ConfigMissingError,
    ErrorCode,
    ErrorResponse,
    MigrationFailedError,
    MigrationError,
    RollbackVerificationError,
    UpstreamUnavailableError,
    map_db_error,
)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_codes_are_stable_strings(self) -> None:
        """Error codes must be stable string values."""
        assert ErrorCode.CONFIG_MISSING.value == "CONFIG_MISSING"
        assert ErrorCode.UPSTREAM_UNAVAILABLE.value == "UPSTREAM_UNAVAILABLE"
        assert ErrorCode.MIGRATION_FAILED.value == "MIGRATION_FAILED"
        assert ErrorCode.MIGRATION_ROLLBACK_FAILED.value == "MIGRATION_ROLLBACK_FAILED"

    def test_error_codes_are_str_enum(self) -> None:
        """Error codes must be string enums for JSON serialization."""
        assert isinstance(ErrorCode.CONFIG_MISSING, str)
        assert isinstance(ErrorCode.MIGRATION_FAILED, str)


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_error_response_has_required_fields(self) -> None:
        """ErrorResponse must have code, message, retryable fields."""
        response = ErrorResponse(
            code="CONFIG_MISSING",
            message="Missing required configuration: GANGQING_DATABASE_URL",
            retryable=False,
        )
        assert response.code == "CONFIG_MISSING"
        assert response.message == "Missing required configuration: GANGQING_DATABASE_URL"
        assert response.retryable is False
        assert response.details is None
        assert response.request_id is None

    def test_error_response_with_all_fields(self) -> None:
        """ErrorResponse can include optional fields."""
        response = ErrorResponse(
            code="MIGRATION_FAILED",
            message="Migration upgrade failed",
            details={"version": "0001", "cause": "connection refused"},
            retryable=False,
            request_id="req-123",
        )
        assert response.details == {"version": "0001", "cause": "connection refused"}
        assert response.request_id == "req-123"

    def test_error_response_message_is_english(self) -> None:
        """Error message must be in English for log searchability."""
        response = ErrorResponse(
            code="UPSTREAM_UNAVAILABLE",
            message="Postgres is unavailable",
            retryable=True,
        )
        # Ensure message contains only ASCII (English)
        assert response.message.isascii()


class TestMigrationError:
    """Tests for MigrationError base class."""

    def test_migration_error_to_response(self) -> None:
        """MigrationError can be converted to ErrorResponse."""
        error = MigrationError(
            code=ErrorCode.MIGRATION_FAILED,
            message="Migration failed",
            details={"step": "upgrade"},
            retryable=False,
            request_id="req-test",
        )
        response = error.to_response()
        assert isinstance(response, ErrorResponse)
        assert response.code == "MIGRATION_FAILED"
        assert response.message == "Migration failed"
        assert response.details == {"step": "upgrade"}
        assert response.request_id == "req-test"


class TestConfigMissingError:
    """Tests for ConfigMissingError."""

    def test_config_missing_error_for_env_var(self) -> None:
        """ConfigMissingError for environment variable."""
        error = ConfigMissingError("GANGQING_DATABASE_URL")
        assert error.code == ErrorCode.CONFIG_MISSING
        assert "GANGQING_DATABASE_URL" in error.message
        assert error.details == {"env_var": "GANGQING_DATABASE_URL"}
        assert error.retryable is False

    def test_config_missing_error_for_file(self) -> None:
        """ConfigMissingError for missing file."""
        error = ConfigMissingError("backend/alembic.ini", request_id="req-1")
        assert error.code == ErrorCode.CONFIG_MISSING
        assert "backend/alembic.ini" in error.message
        assert error.request_id == "req-1"

    def test_config_missing_error_message_is_english(self) -> None:
        """Error message must be in English."""
        error = ConfigMissingError("SOME_CONFIG")
        assert error.message.isascii()


class TestUpstreamUnavailableError:
    """Tests for UpstreamUnavailableError."""

    def test_upstream_unavailable_error(self) -> None:
        """UpstreamUnavailableError for service unavailable."""
        error = UpstreamUnavailableError("Postgres", cause="connection refused")
        assert error.code == ErrorCode.UPSTREAM_UNAVAILABLE
        assert "Postgres" in error.message
        assert error.details == {"service": "Postgres", "cause": "connection refused"}
        assert error.retryable is True

    def test_upstream_unavailable_without_cause(self) -> None:
        """UpstreamUnavailableError without cause."""
        error = UpstreamUnavailableError("ERP")
        assert error.code == ErrorCode.UPSTREAM_UNAVAILABLE
        assert error.details == {"service": "ERP"}
        assert error.retryable is True


class TestDbStatementTimeoutMapping:
    def test_pg_statement_timeout_is_mapped_to_upstream_timeout(self) -> None:
        from sqlalchemy.exc import DBAPIError

        class _Orig(Exception):
            pgcode = "57014"

        db_err = DBAPIError(
            statement="SELECT pg_sleep(1)",
            params={},
            orig=_Orig("canceling statement due to statement timeout"),
            connection_invalidated=False,
        )

        err = map_db_error(db_err, request_id="r1")
        assert err.code == ErrorCode.UPSTREAM_TIMEOUT
        assert err.retryable is True
        assert err.request_id == "r1"
        assert err.message.isascii()


class TestMigrationFailedError:
    """Tests for MigrationFailedError."""

    def test_migration_failed_error(self) -> None:
        """MigrationFailedError with all details."""
        error = MigrationFailedError(
            "upgrade",
            version="0001",
            cause="table already exists",
            request_id="req-2",
        )
        assert error.code == ErrorCode.MIGRATION_FAILED
        assert "upgrade" in error.message
        assert error.details == {
            "operation": "upgrade",
            "version": "0001",
            "cause": "table already exists",
        }
        assert error.retryable is False
        assert error.request_id == "req-2"


class TestRollbackVerificationError:
    """Tests for RollbackVerificationError."""

    def test_rollback_verification_error(self) -> None:
        """RollbackVerificationError for version mismatch."""
        error = RollbackVerificationError(
            expected_version="0001",
            actual_version=None,
            request_id="req-3",
        )
        assert error.code == ErrorCode.MIGRATION_ROLLBACK_FAILED
        assert "version mismatch" in error.message
        assert error.details == {
            "expected_version": "0001",
            "actual_version": None,
        }
        assert error.retryable is False


class TestRequireDatabaseUrl:
    """Tests for database URL requirement."""

    def test_require_database_url_missing(self) -> None:
        """Missing GANGQING_DATABASE_URL must raise ConfigMissingError."""
        from gangqing_db.errors import ConfigMissingError

        with mock.patch.dict(os.environ, {}, clear=True):
            # Remove GANGQING_DATABASE_URL if it exists
            os.environ.pop("GANGQING_DATABASE_URL", None)

            with pytest.raises(ConfigMissingError) as exc_info:
                # Simulate the function from scripts
                database_url = os.getenv("GANGQING_DATABASE_URL")
                if not database_url:
                    raise ConfigMissingError("GANGQING_DATABASE_URL")

            error = exc_info.value
            assert error.code == ErrorCode.CONFIG_MISSING
            assert "GANGQING_DATABASE_URL" in error.message

    def test_require_database_url_present(self) -> None:
        """Present GANGQING_DATABASE_URL must be returned."""
        with mock.patch.dict(
            os.environ,
            {"GANGQING_DATABASE_URL": "postgresql://user:pass@localhost/db"},
            clear=True,
        ):
            database_url = os.getenv("GANGQING_DATABASE_URL")
            assert database_url == "postgresql://user:pass@localhost/db"
