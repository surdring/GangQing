from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic import Field

from gangqing.common.context import RequestContext


class SseCapabilities(BaseModel):
    streaming: bool = True
    evidence_incremental: bool = Field(alias="evidenceIncremental")
    cancellation_supported: bool = Field(alias="cancellationSupported")

    model_config = {"populate_by_name": True}


class SseMetaPayload(BaseModel):
    capabilities: SseCapabilities


class SseEnvelope(BaseModel):
    type: str
    timestamp: datetime
    request_id: str = Field(alias="requestId")
    tenant_id: str = Field(alias="tenantId")
    project_id: str = Field(alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    sequence: int
    payload: dict

    model_config = {"populate_by_name": True}


def build_meta_envelope(*, ctx: RequestContext, sequence: int, timestamp: datetime) -> SseEnvelope:
    payload = SseMetaPayload(
        capabilities=SseCapabilities(
            evidence_incremental=True,
            cancellation_supported=True,
        )
    ).model_dump(by_alias=True)

    return SseEnvelope(
        type="meta",
        timestamp=timestamp,
        request_id=ctx.request_id,
        tenant_id=ctx.tenant_id,
        project_id=ctx.project_id,
        session_id=ctx.session_id,
        sequence=sequence,
        payload=payload,
    )
