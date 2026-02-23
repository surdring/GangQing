from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from gangqing_db.errors import MigrationError, map_db_error
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
