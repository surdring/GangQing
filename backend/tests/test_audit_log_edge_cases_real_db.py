from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, text

from gangqing.common.context import RequestContext
from gangqing_db.audit_log import AuditLogEvent, insert_audit_log_event
from gangqing_db.settings import load_settings


def _require_database_url() -> str:
    settings = load_settings()
    if not settings.database_url.strip():
        raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL")
    return settings.database_url


def _set_rls_context(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})


def test_insert_audit_log_event_accepts_large_action_summary_real_db() -> None:
    os.environ.setdefault("GANGQING_JWT_SECRET", "0123456789abcdef0123456789abcdef")
    database_url = _require_database_url()

    tenant_id = "t1"
    project_id = "p1"
    rid = "rid_unit_audit_large_summary_1"

    big_text = "x" * 200_000

    ctx = RequestContext(
        requestId=rid,
        tenantId=tenant_id,
        projectId=project_id,
        userId="u_large",
        role="admin",
    )

    insert_audit_log_event(
        AuditLogEvent(
            eventType="query",
            requestId=rid,
            tenantId=tenant_id,
            projectId=project_id,
            sessionId=None,
            userId="u_large",
            role="admin",
            resource="unit_test",
            actionSummary={"blob": big_text},
            result="success",
            errorCode=None,
            evidenceRefs=None,
        ),
        ctx=ctx,
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()
        row = conn.execute(
            text(
                """
                SELECT action_summary::text AS action_summary_text
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id = :request_id
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "request_id": rid},
        ).mappings().one_or_none()
        assert row is not None
        assert "blob" in (row.get("action_summary_text") or "")


def test_insert_audit_log_event_concurrent_writes_real_db() -> None:
    database_url = _require_database_url()

    tenant_id = "t1"
    project_id = "p1"

    def _write_one(i: int) -> None:
        rid = f"rid_unit_audit_concurrency_{i}"
        ctx = RequestContext(
            requestId=rid,
            tenantId=tenant_id,
            projectId=project_id,
            userId="u_conc",
            role="admin",
        )
        insert_audit_log_event(
            AuditLogEvent(
                eventType="query",
                requestId=rid,
                tenantId=tenant_id,
                projectId=project_id,
                sessionId=None,
                userId="u_conc",
                role="admin",
                resource="unit_test",
                actionSummary={"i": i},
                result="success",
                errorCode=None,
                evidenceRefs=None,
            ),
            ctx=ctx,
        )

    n = 20
    with ThreadPoolExecutor(max_workers=10) as ex:
        for _ in ex.map(_write_one, range(n)):
            pass

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()
        row = conn.execute(
            text(
                """
                SELECT COUNT(1) AS c
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id LIKE 'rid_unit_audit_concurrency_%'
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().one()
        assert int(row.get("c") or 0) >= n
