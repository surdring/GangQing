from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    retryable: bool
    request_id: str = Field(alias="requestId")

    model_config = {"populate_by_name": True}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        request_id: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.retryable = retryable
        self.request_id = request_id

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            code=self.code.value,
            message=self.message,
            details=self.details,
            retryable=self.retryable,
            request_id=self.request_id,
        )
