from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

from gangqing.common.context import RequestContext
from gangqing.common.errors import ErrorResponse
from gangqing_db.evidence import Evidence


class SseCapabilities(BaseModel):
    streaming: bool = True
    evidence_incremental: bool = Field(alias="evidenceIncremental")
    cancellation_supported: bool = Field(alias="cancellationSupported")

    model_config = {"populate_by_name": True}


class SseEventEnvelope(BaseModel):
    timestamp: datetime
    request_id: str = Field(alias="requestId")
    tenant_id: str = Field(alias="tenantId")
    project_id: str = Field(alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    sequence: int

    model_config = {"populate_by_name": True}


class SseMetaPayload(BaseModel):
    capabilities: SseCapabilities


class SseEvent(BaseModel):
    type: str
    timestamp: datetime
    request_id: str = Field(alias="requestId")
    tenant_id: str = Field(alias="tenantId")
    project_id: str = Field(alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    sequence: int
    payload: Any

    model_config = {"populate_by_name": True}


class SseMetaEvent(SseEvent):
    type: Literal["meta"] = "meta"
    payload: SseMetaPayload


class SseErrorEvent(SseEvent):
    type: Literal["error"] = "error"
    payload: ErrorResponse


class SseFinalPayload(BaseModel):
    status: Literal["success", "error", "cancelled"]

    model_config = {"extra": "forbid"}


class SseFinalEvent(SseEvent):
    type: Literal["final"] = "final"
    payload: SseFinalPayload


class SseProgressPayload(BaseModel):
    stage: str
    message: str
    step_id: str | None = Field(default=None, alias="stepId")

    model_config = {"populate_by_name": True}


class SseProgressEvent(SseEvent):
    type: Literal["progress"] = "progress"
    payload: SseProgressPayload


class SseWarningPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class SseWarningEvent(SseEvent):
    type: Literal["warning"] = "warning"
    payload: SseWarningPayload


class SseToolCallPayload(BaseModel):
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    args_summary: dict[str, Any] = Field(alias="argsSummary")

    model_config = {"populate_by_name": True}


class SseToolCallEvent(SseEvent):
    type: Literal["tool.call"] = "tool.call"
    payload: SseToolCallPayload


class SseToolResultPayload(BaseModel):
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    status: Literal["success", "failure"]
    result_summary: dict[str, Any] | None = Field(default=None, alias="resultSummary")
    error: ErrorResponse | None = None
    evidence_refs: list[str] | None = Field(default=None, alias="evidenceRefs")

    model_config = {"populate_by_name": True}


class SseToolResultEvent(SseEvent):
    type: Literal["tool.result"] = "tool.result"
    payload: SseToolResultPayload


class SseMessageDeltaPayload(BaseModel):
    delta: str


class SseMessageDeltaEvent(SseEvent):
    type: Literal["message.delta"] = "message.delta"
    payload: SseMessageDeltaPayload


class SseEvidenceUpdatePayload(BaseModel):
    mode: Literal["append", "update", "reference"]
    evidences: list[Evidence] | None = None
    evidence_ids: list[str] | None = Field(default=None, alias="evidenceIds")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_mode_constraints(self) -> "SseEvidenceUpdatePayload":
        if self.mode in ("append", "update"):
            if not self.evidences:
                raise ValueError("evidence.update payload.evidences is required for mode append|update")
        if self.mode == "reference":
            if not self.evidence_ids:
                raise ValueError("evidence.update payload.evidenceIds is required for mode reference")
        return self


class SseEvidenceUpdateEvent(SseEvent):
    type: Literal["evidence.update"] = "evidence.update"
    payload: SseEvidenceUpdatePayload


def build_meta_envelope(*, ctx: RequestContext, sequence: int, timestamp: datetime) -> SseMetaEvent:
    payload = SseMetaPayload(
        capabilities=SseCapabilities(
            evidence_incremental=True,
            cancellation_supported=True,
        )
    )

    return SseMetaEvent(
        timestamp=timestamp,
        request_id=ctx.request_id,
        tenant_id=ctx.tenant_id,
        project_id=ctx.project_id,
        session_id=ctx.session_id,
        sequence=sequence,
        payload=payload,
    )


def build_error_envelope(
    *,
    ctx: RequestContext,
    sequence: int,
    timestamp: datetime,
    payload: ErrorResponse,
) -> SseErrorEvent:
    return SseErrorEvent(
        timestamp=timestamp,
        request_id=ctx.request_id,
        tenant_id=ctx.tenant_id,
        project_id=ctx.project_id,
        session_id=ctx.session_id,
        sequence=sequence,
        payload=payload,
    )
