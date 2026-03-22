from __future__ import annotations

import json
from datetime import datetime, timezone
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import create_engine, text

from gangqing.common.redaction import redact_sensitive
from gangqing_db.errors import MigrationError, map_db_error
from gangqing_db.settings import load_settings


AuditResultLiteral = Literal["success", "failure"]


_NON_ENGLISH_RE = re.compile(r"[\u4e00-\u9fff]")


class AuditError(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def _validate_message_english(cls, v: str) -> str:
        msg = (v or "").strip()
        if not msg:
            raise ValueError("Audit error message must not be empty")
        if _NON_ENGLISH_RE.search(msg) is not None:
            raise ValueError(
                "Audit error message must be English. Please translate the message into clear English."
            )
        return msg


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
    correlation_id: str | None = Field(default=None, alias="correlationId")
    supersedes_event_id: str | None = Field(default=None, alias="supersedesEventId")
    action_summary: dict[str, Any] | None = Field(default=None, alias="actionSummary")
    result_summary: dict[str, Any] | None = Field(default=None, alias="resultSummary")
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    step_id: str | None = Field(default=None, alias="stepId")
    error: AuditError | None = Field(default=None)
    result_status: AuditResultLiteral = Field(alias="result")
    error_code: str | None = Field(default=None, alias="errorCode")
    evidence_refs: list[str] | None = Field(default=None, alias="evidenceRefs")

    model_config = {"populate_by_name": True}

    @field_validator(
        "event_type",
        "request_id",
        "tenant_id",
        "project_id",
        "session_id",
        "user_id",
        "role",
        "resource",
        "correlation_id",
        "supersedes_event_id",
        "tool_call_id",
        "step_id",
        "error_code",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v

    @model_validator(mode="after")
    def _validate_error_mapping(self) -> "AuditLogEvent":
        if self.error is not None:
            if self.error_code is None:
                self.error_code = self.error.code
            elif self.error_code != self.error.code:
                raise ValueError("errorCode must match error.code when both provided")
        return self


def _engine_from_settings():
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def insert_audit_log_event(event: AuditLogEvent, *, ctx) -> None:
    """Insert audit event into Postgres audit_log (append-only).

    ctx must provide request_id/tenant_id/project_id; using ctx keeps requestId consistent.
    """

    action_summary = event.action_summary
    if action_summary is not None and not isinstance(action_summary, dict):
        action_summary = {"value": action_summary}

    merged_summary: dict[str, Any] | None
    if action_summary is None and event.result_summary is None and event.error is None:
        merged_summary = None
    else:
        merged_summary = {} if action_summary is None else dict(action_summary)
        if event.result_summary is not None and "resultSummary" not in merged_summary:
            merged_summary["resultSummary"] = event.result_summary
        if event.tool_call_id is not None and "toolCallId" not in merged_summary:
            merged_summary["toolCallId"] = event.tool_call_id
        if event.step_id is not None and "stepId" not in merged_summary:
            merged_summary["stepId"] = event.step_id
        if event.error is not None:
            merged_summary["error"] = event.error.model_dump()

    try:
        from gangqing.common.masking import apply_role_based_masking, load_masking_policy

        try:
            policy = load_masking_policy()
        except Exception:
            policy = None

        role_raw = (getattr(ctx, "role", None) or getattr(event, "role", None) or "").strip() or None
        masked_action_summary, masking_meta = apply_role_based_masking(
            merged_summary,
            role=role_raw,
            can_unmask=False,
            policy=policy,
        )
        if masking_meta is not None:
            masked_action_summary = {} if masked_action_summary is None else dict(masked_action_summary)
            masked_action_summary["masking"] = masking_meta
        merged_summary = masked_action_summary
    except Exception as e:
        merged_summary = {
            "masking": {
                "status": "failed",
                "reason": str(e)[:200],
            }
        }

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
                        correlation_id,
                        supersedes_event_id,
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
                        :correlation_id,
                        :supersedes_event_id,
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
                    "correlation_id": event.correlation_id,
                    "supersedes_event_id": event.supersedes_event_id,
                    "action_summary": None
                    if merged_summary is None
                    else json.dumps(
                        redact_sensitive(merged_summary),
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
