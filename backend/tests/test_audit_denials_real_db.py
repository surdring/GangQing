from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from gangqing.app.main import create_app
from gangqing.common.auth import create_access_token
from gangqing_db.settings import load_settings


def _require_database_url() -> str:
    settings = load_settings()
    if not settings.database_url.strip():
        raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL")
    return settings.database_url


def _set_rls_context(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})


def _list_events_by_request_id(
    *,
    database_url: str,
    tenant_id: str,
    project_id: str,
    request_id: str,
) -> list[dict]:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()
        rows = conn.execute(
            text(
                """
                SELECT event_type, request_id, tenant_id, project_id, action_summary
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id = :request_id
                ORDER BY timestamp DESC
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "request_id": request_id,
            },
        ).mappings().all()
        return [dict(r) for r in rows]


def _assert_no_secrets(events: list[dict]) -> None:
    raw = str(events).lower()
    assert "bearer" not in raw
    assert "password" not in raw
    assert "jwt" not in raw
    assert "secret" not in raw
    assert "token" not in raw


def _assert_error_response(obj: dict) -> None:
    keys = sorted(obj.keys())
    if keys != ["code", "details", "message", "requestId", "retryable"]:
        raise AssertionError(f"Unexpected error response keys: {keys}")


def _assert_audit_events_response(obj: dict) -> None:
    keys = sorted(obj.keys())
    if keys != ["items", "total"]:
        raise AssertionError(f"Unexpected audit events response keys: {keys}")


def test_denials_write_audit_events_and_no_secrets() -> None:
    os.environ.setdefault("GANGQING_JWT_SECRET", "0123456789abcdef0123456789abcdef")
    database_url = _require_database_url()

    app = create_app()
    client = TestClient(app)

    tenant_id = "t1"
    project_id = "p1"

    # 1) AUTH_ERROR: missing token when querying audit endpoint
    rid_auth = "rid_unit_audit_auth_1"
    resp = client.get(
        "/api/v1/audit/events",
        headers={
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": rid_auth,
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    _assert_error_response(body)
    assert body["code"] == "AUTH_ERROR"

    auth_events = _list_events_by_request_id(
        database_url=database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        request_id=rid_auth,
    )
    assert any(e.get("event_type") == "auth.denied" for e in auth_events)
    _assert_no_secrets(auth_events)

    # 2) FORBIDDEN: finance token denied to chat
    token, _ = create_access_token(
        user_id="fin_u",
        role="finance",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    rid_forbid = "rid_unit_audit_forbid_1"
    resp2 = client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": rid_forbid,
            "Authorization": f"Bearer {token}",
        },
    )
    assert resp2.status_code == 403
    body2 = resp2.json()
    assert body2["code"] == "FORBIDDEN"

    forbid_events = _list_events_by_request_id(
        database_url=database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        request_id=rid_forbid,
    )
    assert any(e.get("event_type") == "rbac.denied" for e in forbid_events)
    _assert_no_secrets(forbid_events)

    # 3) tool_call: plant_manager can run tool demo and writes tool_call audit
    admin_token, _ = create_access_token(
        user_id="admin_u",
        role="plant_manager",
        tenant_id=tenant_id,
        project_id=project_id,
    )
    rid_tool = "rid_unit_audit_tool_1"
    resp3 = client.post(
        "/api/v1/tools/demo",
        json={"query": "q1"},
        headers={
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": rid_tool,
            "Authorization": f"Bearer {admin_token}",
        },
    )
    assert resp3.status_code == 200
    body3 = resp3.json()
    assert body3.get("result") == "echo:q1"

    tool_events = _list_events_by_request_id(
        database_url=database_url,
        tenant_id=tenant_id,
        project_id=project_id,
        request_id=rid_tool,
    )
    assert any(e.get("event_type") == "tool_call" for e in tool_events)
    _assert_no_secrets(tool_events)
