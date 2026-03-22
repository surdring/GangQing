from __future__ import annotations

import json
import os
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from gangqing.app.main import create_app
from gangqing.common.auth import create_access_token


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise AssertionError(f"Missing required env for tests: {name}")
    return value


def _count_tool_calls(*, database_url: str, tenant_id: str, project_id: str, request_id: str) -> int:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})
        conn.commit()

        row = conn.execute(
            text(
                """
                SELECT COUNT(1) AS cnt
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id = :request_id
                  AND event_type = 'tool_call'
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "request_id": request_id,
            },
        ).mappings().one()
        return int(row["cnt"] or 0)


def _count_tool_calls_since(
    *,
    database_url: str,
    tenant_id: str,
    project_id: str,
    request_id: str,
    since_ts_epoch_seconds: float,
) -> int:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})
        conn.commit()

        row = conn.execute(
            text(
                """
                SELECT COUNT(1) AS cnt
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id = :request_id
                  AND event_type = 'tool_call'
                  AND timestamp >= to_timestamp(:since_ts)
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "request_id": request_id,
                "since_ts": float(since_ts_epoch_seconds),
            },
        ).mappings().one()
        return int(row["cnt"] or 0)


def test_sse_disconnect_cancels_and_prevents_tool_call_audit_real_db() -> None:
    database_url = _require_env("GANGQING_DATABASE_URL")

    tenant_id = "t1"
    project_id = "p1"
    request_id = "rid_sse_cancel_disconnect_1"

    app = create_app()
    client = TestClient(app)

    token, _ = create_access_token(
        user_id="u1",
        role="plant_manager",
        tenant_id=tenant_id,
        project_id=project_id,
    )

    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "query"},
        headers={
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id,
            "Authorization": f"Bearer {token}",
        },
    ) as resp:
        assert resp.status_code == 200

        meta_seen = False
        disconnect_ts = None
        for line in resp.iter_lines():
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            evt = json.loads(line[len("data: ") :])
            if str(evt.get("type") or "") == "meta":
                meta_seen = True
                disconnect_ts = time.time()
                break

        assert meta_seen, "Expected to receive meta event before disconnect"
        assert disconnect_ts is not None

    deadline = time.time() + 1.5
    while time.time() < deadline:
        tool_calls = _count_tool_calls_since(
            database_url=database_url,
            tenant_id=tenant_id,
            project_id=project_id,
            request_id=request_id,
            since_ts_epoch_seconds=float(disconnect_ts),
        )
        assert tool_calls == 0, "Expected no tool_call audit events after client disconnect"
        time.sleep(0.1)
