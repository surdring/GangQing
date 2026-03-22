from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from gangqing_db.errors import MigrationError, map_db_error
from gangqing_db.evidence_chain import ToolCallTrace
from gangqing_db.settings import load_settings


class AuditLogRecord(BaseModel):
    id: str
    event_type: str = Field(alias="eventType")
    timestamp: datetime
    request_id: str = Field(alias="requestId")
    tenant_id: str = Field(alias="tenantId")
    project_id: str = Field(alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    user_id: str | None = Field(default=None, alias="userId")
    role: str | None = None
    resource: str | None = None
    correlation_id: str | None = Field(default=None, alias="correlationId")
    supersedes_event_id: str | None = Field(default=None, alias="supersedesEventId")
    action_summary: dict[str, Any] | None = Field(default=None, alias="actionSummary")
    result_status: str = Field(alias="result")
    error_code: str | None = Field(default=None, alias="errorCode")
    evidence_refs: list[str] | None = Field(default=None, alias="evidenceRefs")

    model_config = {"populate_by_name": True}


def _engine_from_settings():
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def list_audit_events(
    *,
    ctx,
    limit: int = 50,
    offset: int = 0,
    request_id: str | None = None,
    event_type: str | None = None,
    user_id: str | None = None,
    tool_name: str | None = None,
    time_range_start: datetime | None = None,
    time_range_end: datetime | None = None,
) -> tuple[int, list[AuditLogRecord]]:
    try:
        engine = _engine_from_settings()
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": ctx.tenant_id})
            conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": ctx.project_id})
            conn.commit()

            where_sql = """
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
            """
            params: dict[str, Any] = {
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "limit": limit,
                "offset": offset,
            }
            if request_id is not None:
                where_sql += " AND request_id = :request_id"
                params["request_id"] = request_id

            if event_type is not None:
                where_sql += " AND event_type = :event_type"
                params["event_type"] = event_type

            if user_id is not None:
                where_sql += " AND user_id = :user_id"
                params["user_id"] = user_id

            if tool_name is not None:
                where_sql += " AND resource = :tool_name"
                params["tool_name"] = tool_name

            if time_range_start is not None:
                where_sql += " AND timestamp >= :time_range_start"
                params["time_range_start"] = time_range_start

            if time_range_end is not None:
                where_sql += " AND timestamp < :time_range_end"
                params["time_range_end"] = time_range_end

            total_sql = f"SELECT COUNT(1) AS total FROM audit_log {where_sql}"
            total_row = conn.execute(text(total_sql), params).mappings().one()
            total = int(total_row["total"] or 0)

            items_sql = f"""
                SELECT
                    id::text,
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
                FROM audit_log
                {where_sql}
                ORDER BY timestamp DESC
                LIMIT :limit OFFSET :offset
            """

            rows = conn.execute(text(items_sql), params).mappings().all()
            return total, [AuditLogRecord(**dict(r)) for r in rows]

    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))


def list_tool_call_traces_by_request_id(*, ctx, request_id: str) -> list[ToolCallTrace]:
    try:
        engine = _engine_from_settings()
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": ctx.tenant_id})
            conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": ctx.project_id})
            conn.commit()

            rows = conn.execute(
                text(
                    """
                    SELECT
                        timestamp,
                        resource,
                        result_status,
                        error_code,
                        action_summary,
                        evidence_refs
                    FROM audit_log
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND request_id = :request_id
                      AND event_type = 'tool_call'
                    ORDER BY timestamp ASC
                    """
                ),
                {
                    "tenant_id": ctx.tenant_id,
                    "project_id": ctx.project_id,
                    "request_id": request_id,
                },
            ).mappings().all()

            traces: list[ToolCallTrace] = []
            merged_by_tool_call_id: dict[str, ToolCallTrace] = {}
            ordered_tool_call_ids: list[str] = []

            def _prefer(*, current: Any, incoming: Any) -> Any:
                if incoming is None:
                    return current
                if current is None:
                    return incoming
                if isinstance(incoming, (dict, list)) and not incoming:
                    return current
                if isinstance(current, (dict, list)) and not current:
                    return incoming
                if isinstance(incoming, str) and not incoming.strip():
                    return current
                if isinstance(current, str) and not current.strip():
                    return incoming
                return incoming

            for r in rows:
                tool_name = str(r.get("resource") or "")
                action_summary = r.get("action_summary")
                tool_call_id = None
                duration_ms = None
                args_summary = None
                result_summary = None
                if isinstance(action_summary, dict):
                    raw_tool_call_id = action_summary.get("toolCallId")
                    if raw_tool_call_id is not None:
                        tool_call_id = str(raw_tool_call_id).strip() or None

                    raw_duration = action_summary.get("durationMs")
                    if raw_duration is not None:
                        try:
                            duration_ms = int(raw_duration)
                        except Exception:
                            duration_ms = None

                    raw_args = action_summary.get("argsSummary")
                    args_summary = raw_args if isinstance(raw_args, dict) else None

                    if isinstance(args_summary, dict):
                        raw_result_summary = args_summary.get("resultSummary")
                        result_summary = (
                            raw_result_summary if isinstance(raw_result_summary, dict) else None
                        )

                result_status = str(r.get("result_status") or "success")
                status: str = "success" if result_status == "success" else "failure"

                trace = ToolCallTrace(
                    toolCallId=tool_call_id or "unknown",
                    toolName=tool_name or "unknown",
                    status=status,  # type: ignore[arg-type]
                    durationMs=duration_ms,
                    argsSummary=args_summary,
                    resultSummary=result_summary,
                    error=None if r.get("error_code") is None else {"code": r.get("error_code")},
                    evidenceRefs=r.get("evidence_refs"),
                )

                key = str(trace.tool_call_id)
                if key not in merged_by_tool_call_id:
                    merged_by_tool_call_id[key] = trace
                    ordered_tool_call_ids.append(key)
                    continue

                existing = merged_by_tool_call_id[key]
                merged_by_tool_call_id[key] = ToolCallTrace(
                    toolCallId=key,
                    toolName=str(_prefer(current=existing.tool_name, incoming=trace.tool_name)),
                    status=(
                        "failure"
                        if (existing.status == "failure" or trace.status == "failure")
                        else "success"
                    ),
                    durationMs=_prefer(current=existing.duration_ms, incoming=trace.duration_ms),
                    argsSummary=_prefer(current=existing.args_summary, incoming=trace.args_summary),
                    resultSummary=_prefer(current=existing.result_summary, incoming=trace.result_summary),
                    error=_prefer(current=existing.error, incoming=trace.error),
                    evidenceRefs=_prefer(current=existing.evidence_refs, incoming=trace.evidence_refs),
                )

            for key in ordered_tool_call_ids:
                traces.append(merged_by_tool_call_id[key])
            return traces

    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))
