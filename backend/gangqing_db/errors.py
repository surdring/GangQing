"""Structured error models for GangQing database operations.

This module defines stable error codes and structured error responses
that align with docs/contracts/api-and-events-draft.md.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import Field

try:
    from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, TimeoutError
except Exception:  # pragma: no cover
    DBAPIError = Exception  # type: ignore[assignment,misc]
    IntegrityError = Exception  # type: ignore[assignment,misc]
    OperationalError = Exception  # type: ignore[assignment,misc]
    TimeoutError = Exception  # type: ignore[assignment,misc]


class ErrorCode(str, Enum):
    """Stable error codes for database operations."""

    # Configuration errors
    CONFIG_MISSING = "CONFIG_MISSING"

    # Upstream errors
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"

    # Auth & access control errors
    AUTH_ERROR = "AUTH_ERROR"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"

    # Evidence / lineage errors
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"

    # Migration errors
    MIGRATION_FAILED = "MIGRATION_FAILED"
    MIGRATION_ROLLBACK_FAILED = "MIGRATION_ROLLBACK_FAILED"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    """Unified error response model.

    Aligns with docs/contracts/api-and-events-draft.md section 2.1.
    """

    code: str
    message: str
    details: dict[str, Any] | None = None
    retryable: bool = False
    request_id: str | None = Field(default=None, alias="requestId")

    model_config = {
        "populate_by_name": True,
    }


class MigrationError(Exception):
    """Base exception for migration-related errors.

    Provides structured error output with stable code and English message.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.retryable = retryable
        self.request_id = request_id

    def to_response(self) -> ErrorResponse:
        """Convert to ErrorResponse model."""
        return ErrorResponse(
            code=self.code.value,
            message=self.message,
            details=self.details,
            retryable=self.retryable,
            request_id=self.request_id,
        )


class ConfigMissingError(MigrationError):
    """Raised when required configuration is missing."""

    def __init__(self, env_var: str, *, request_id: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.CONFIG_MISSING,
            message=f"Missing required configuration: {env_var}",
            details={"env_var": env_var},
            retryable=False,
            request_id=request_id,
        )


class UpstreamUnavailableError(MigrationError):
    """Raised when upstream service (e.g., Postgres) is unavailable."""

    def __init__(
        self,
        service: str,
        *,
        cause: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"service": service}
        if cause:
            details["cause"] = cause
        super().__init__(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message=f"{service} is unavailable",
            details=details,
            retryable=True,
            request_id=request_id,
        )


class MigrationFailedError(MigrationError):
    """Raised when migration fails."""

    def __init__(
        self,
        operation: str,
        *,
        version: str | None = None,
        cause: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"operation": operation}
        if version:
            details["version"] = version
        if cause:
            details["cause"] = cause
        super().__init__(
            code=ErrorCode.MIGRATION_FAILED,
            message=f"Migration {operation} failed",
            details=details,
            retryable=False,
            request_id=request_id,
        )


class RollbackVerificationError(MigrationError):
    """Raised when rollback verification fails."""

    def __init__(
        self,
        expected_version: str,
        actual_version: str | None,
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.MIGRATION_ROLLBACK_FAILED,
            message="Rollback verification failed: version mismatch",
            details={
                "expected_version": expected_version,
                "actual_version": actual_version,
            },
            retryable=False,
            request_id=request_id,
        )


class UpstreamTimeoutError(MigrationError):
    """Raised when upstream query times out."""

    def __init__(
        self,
        service: str,
        *,
        cause: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"service": service}
        if cause:
            details["cause"] = cause
        super().__init__(
            code=ErrorCode.UPSTREAM_TIMEOUT,
            message=f"{service} query timed out",
            details=details,
            retryable=True,
            request_id=request_id,
        )


class ValidationError(MigrationError):
    """Raised when DB constraint violations indicate invalid input."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details=details,
            retryable=False,
            request_id=request_id,
        )


class ContractViolationError(MigrationError):
    """Raised when DB constraint violations indicate an internal contract issue."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.CONTRACT_VIOLATION,
            message=message,
            details=details,
            retryable=False,
            request_id=request_id,
        )


class AuthError(MigrationError):
    """Raised when authentication context is missing/invalid."""

    def __init__(
        self,
        message: str = "Authentication required",
        *,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.AUTH_ERROR,
            message=message,
            details=details,
            retryable=False,
            request_id=request_id,
        )


class ForbiddenError(MigrationError):
    """Raised when RBAC denies the operation."""

    def __init__(
        self,
        capability: str,
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message="Forbidden",
            details={"capability": capability},
            retryable=False,
            request_id=request_id,
        )


class NotFoundError(MigrationError):
    """Raised when requested resource does not exist."""

    def __init__(
        self,
        resource: str,
        *,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        payload = {"resource": resource}
        if details:
            payload.update(details)
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message="Resource not found",
            details=payload,
            retryable=False,
            request_id=request_id,
        )


class EvidenceMissingError(MigrationError):
    """Raised when metric lineage is required but missing."""

    def __init__(
        self,
        metric_name: str,
        *,
        lineage_version: str | None = None,
        request_id: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"metric_name": metric_name}
        if lineage_version is not None:
            details["lineage_version"] = lineage_version
        super().__init__(
            code=ErrorCode.EVIDENCE_MISSING,
            message=(
                "Metric lineage is missing. "
                "Specify lineageVersion explicitly or provide scenarioKey, "
                "or add the missing metric lineage/mapping record for this scope."
            ),
            details=details,
            retryable=False,
            request_id=request_id,
        )


class EvidenceMismatchError(MigrationError):
    """Raised when lineage selection is ambiguous or conflicts with policy."""

    @staticmethod
    def _build_message(reason: str) -> str:
        if reason == "lineage_version_required":
            return (
                "Metric lineage version is required. "
                "Specify lineageVersion explicitly or provide scenarioKey."
            )
        if reason == "multiple_active_lineage_versions":
            return (
                "Metric lineage selection is ambiguous (multiple active versions). "
                "Specify lineageVersion explicitly."
            )
        if reason == "duplicate_metric_lineage":
            return (
                "Metric lineage records are inconsistent (duplicate versions). "
                "Fix metric_lineage uniqueness for this scope."
            )
        if reason == "lineage_version_not_active":
            return (
                "Metric lineage version is not active. "
                "Use an active lineageVersion or explicitly allow inactive versions by policy."
            )
        if reason == "lineage_version_deprecated":
            return (
                "Metric lineage version is deprecated. "
                "Use a non-deprecated lineageVersion or explicitly allow deprecated versions by policy."
            )
        if reason == "scenario_mapping_conflict":
            return (
                "Scenario mapping is ambiguous (multiple active mappings). "
                "Fix the mapping table or specify lineageVersion explicitly."
            )
        if reason == "evidence_time_range_unavailable":
            return (
                "Evidence timeRange is unavailable. "
                "Provide data_time_range from the computation window or ensure metric lineage has created_at."
            )
        return "Metric lineage mismatch. Review details.reason for remediation guidance."

    def __init__(
        self,
        metric_name: str,
        *,
        reason: str,
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"metric_name": metric_name, "reason": reason}
        if details:
            payload.update(details)
        super().__init__(
            code=ErrorCode.EVIDENCE_MISMATCH,
            message=self._build_message(reason),
            details=payload,
            retryable=False,
            request_id=request_id,
        )


def map_db_error(exc: Exception, *, request_id: str | None = None) -> MigrationError:
    """Map DB exceptions to structured MigrationError.

    This function is intentionally conservative: it returns English messages,
    stable codes, and avoids leaking sensitive internal details.
    """

    if isinstance(exc, MigrationError):
        return exc

    if isinstance(exc, TimeoutError):
        return UpstreamTimeoutError("Postgres", cause="timeout", request_id=request_id)

    if isinstance(exc, OperationalError):
        orig = getattr(exc, "orig", None)
        pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
        if str(pgcode or "").strip() == "57014":
            return UpstreamTimeoutError(
                "Postgres",
                cause="query_canceled",
                request_id=request_id,
            )
        return UpstreamUnavailableError("Postgres", cause="operational_error", request_id=request_id)

    if isinstance(exc, IntegrityError):
        orig = getattr(exc, "orig", None)
        pgcode = getattr(orig, "pgcode", None)
        constraint_name = getattr(orig, "diag", None)
        constraint = getattr(constraint_name, "constraint_name", None)
        details: dict[str, Any] = {"pgcode": pgcode, "constraint": constraint}

        if pgcode == "23505":
            return ValidationError(
                "Unique constraint violation",
                details=details,
                request_id=request_id,
            )
        if pgcode == "23503":
            return ValidationError(
                "Foreign key constraint violation",
                details=details,
                request_id=request_id,
            )
        if pgcode == "23514":
            return ValidationError(
                "Check constraint violation",
                details=details,
                request_id=request_id,
            )

        return ContractViolationError(
            "Database integrity error",
            details=details,
            request_id=request_id,
        )

    if isinstance(exc, DBAPIError):
        orig = getattr(exc, "orig", None)
        pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)

        if str(pgcode or "").strip() == "57014":
            return UpstreamTimeoutError(
                "Postgres",
                cause="query_canceled",
                request_id=request_id,
            )
        details: dict[str, Any] = {
            "exception": exc.__class__.__name__,
            "pgcode": pgcode,
        }
        return MigrationError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Database error",
            details=details,
            retryable=False,
            request_id=request_id,
        )

    return MigrationError(
        code=ErrorCode.INTERNAL_ERROR,
        message="Internal error",
        details={"exception": exc.__class__.__name__},
        retryable=False,
        request_id=request_id,
    )
