from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from gangqing.common.redaction import redact_sensitive
from gangqing_db.errors import MigrationError, map_db_error
from gangqing_db.settings import load_settings


AuditResultLiteral = Literal["success", "failure"]


class AuditLogEvent(BaseModel):
    event_type: str = Field(min_length=1, alias="eventType")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str = Field(min_length=1, alias="requestId")
    tenant_id: str = Field(min_length=1, alias="tenantId")
    project_id: str = Field(min_length=1, alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    user_id: str | None = Field(default=None, alias="userId")
    role: str | None = None
    resource: str | None = None
    action_summary: dict[str, Any] | None = Field(default=None, alias="actionSummary")
    result_status: AuditResultLiteral = Field(alias="result")
    error_code: str | None = Field(default=None, alias="errorCode")
    evidence_refs: list[str] | None = Field(default=None, alias="evidenceRefs")

    model_config = {"populate_by_name": True}


def _engine_from_settings():
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def insert_audit_log_event(event: AuditLogEvent, *, ctx) -> None:
    """Insert audit event into Postgres audit_log (append-only).

    ctx must provide request_id/tenant_id/project_id; using ctx keeps requestId consistent.
    """

    try:
        engine = _engine_from_settings()
        with engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": ctx.project_id},
            )
            conn.commit()

            conn.execute(
                text(
                    """
                    INSERT INTO audit_log(
                        event_type,
                        timestamp,
                        request_id,
                        tenant_id,
                        project_id,
                        session_id,
                        user_id,
                        role,
                        resource,
                        action_summary,
                        result_status,
                        error_code,
                        evidence_refs
                    ) VALUES (
                        :event_type,
                        :timestamp,
                        :request_id,
                        :tenant_id,
                        :project_id,
                        :session_id,
                        :user_id,
                        :role,
                        :resource,
                        CAST(:action_summary AS jsonb),
                        :result_status,
                        :error_code,
                        CAST(:evidence_refs AS jsonb)
                    )
                    """
                ),
                {
                    "event_type": event.event_type,
                    "timestamp": event.timestamp,
                    "request_id": event.request_id,
                    "tenant_id": event.tenant_id,
                    "project_id": event.project_id,
                    "session_id": event.session_id,
                    "user_id": event.user_id,
                    "role": event.role,
                    "resource": event.resource,
                    "action_summary": None
                    if event.action_summary is None
                    else json.dumps(
                        redact_sensitive(event.action_summary),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "result_status": event.result_status,
                    "error_code": event.error_code,
                    "evidence_refs": None
                    if event.evidence_refs is None
                    else json.dumps(event.evidence_refs, ensure_ascii=False, sort_keys=True),
                },
            )
            conn.commit()

    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))
