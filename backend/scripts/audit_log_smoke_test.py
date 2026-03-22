from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from sqlalchemy import create_engine, text

from gangqing.common.context import RequestContext
from gangqing_db.audit_log import AuditLogEvent, insert_audit_log_event


def _load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _wait_for_port(host: str, port: int, *, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except Exception as e:
            last_err = e
            time.sleep(0.1)
    raise RuntimeError(f"Server did not open port in time: {host}:{port}. Last error: {last_err}")


def _request_json(
    url: str, *, method: str, headers: dict[str, str], body: dict | None = None
) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return e.code, json.loads(raw) if raw else {}


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _set_rls_context(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    database_url = _require_env("GANGQING_DATABASE_URL")
    bootstrap_admin_user_id = _require_env("GANGQING_BOOTSTRAP_ADMIN_USER_ID")
    bootstrap_admin_password = _require_env("GANGQING_BOOTSTRAP_ADMIN_PASSWORD")

    host = (os.environ.get("GANGQING_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = int((os.environ.get("GANGQING_API_PORT") or "8000").strip() or "8000")

    tenant_id = (os.environ.get("GANGQING_TENANT_ID") or "t1").strip() or "t1"
    project_id = (os.environ.get("GANGQING_PROJECT_ID") or "p1").strip() or "p1"

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    backend_dir = repo_root / "backend"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(backend_dir)
        if not existing_pythonpath
        else f"{backend_dir}{os.pathsep}{existing_pythonpath}"
    )

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "uvicorn",
        "gangqing.app.main:create_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        env.get("GANGQING_LOG_LEVEL", "info").lower(),
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        _wait_for_port(host, port, timeout_seconds=10.0)

        # Seed one audit row via append-only write boundary, containing sensitive-like values.
        rid_seed = "rid_audit_log_smoke_seed_1"
        ctx_seed = RequestContext(
            requestId=rid_seed,
            tenantId=tenant_id,
            projectId=project_id,
            userId="seed_u",
            role="system",
        )
        insert_audit_log_event(
            AuditLogEvent(
                eventType="query",
                requestId=rid_seed,
                tenantId=tenant_id,
                projectId=project_id,
                sessionId=None,
                userId="seed_u",
                role="system",
                resource="audit_log_smoke_seed",
                actionSummary={
                    "authorization": "Bearer secret-token",
                    "db": "postgresql://user:pass@localhost:5432/db",
                    "safe": "ok",
                },
                resultSummary={
                    "connection": "psycopg://user:pass@localhost:5432/db",
                },
                result="failure",
                errorCode="UPSTREAM_TIMEOUT",
                error={
                    "code": "UPSTREAM_TIMEOUT",
                    "message": "Upstream timeout",
                },
                evidenceRefs=None,
            ),
            ctx=ctx_seed,
        )

        # Login as admin
        base_headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": "rid_audit_log_smoke_login_1",
            "Content-Type": "application/json",
        }
        login_url = f"http://{host}:{port}/api/v1/auth/login"
        status, body = _request_json(
            login_url,
            method="POST",
            headers=base_headers,
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed: status={status}, body={body}")
        token = (body.get("accessToken") or "").strip()
        if not token:
            raise RuntimeError(f"Missing accessToken in login response: {body}")

        # Query audit events filtered by requestId
        audit_url = f"http://{host}:{port}/api/v1/audit/events?requestId={rid_seed}&limit=10&offset=0"
        status, audit_resp = _request_json(
            audit_url,
            method="GET",
            headers={
                **base_headers,
                "X-Request-Id": "rid_audit_log_smoke_query_1",
                "Authorization": f"Bearer {token}",
            },
            body=None,
        )
        if status != 200:
            raise RuntimeError(f"audit.events failed: status={status}, body={audit_resp}")

        if sorted(audit_resp.keys()) != ["items", "total"]:
            raise RuntimeError(f"Unexpected response keys: {sorted(audit_resp.keys())}")
        items = audit_resp.get("items")
        if not isinstance(items, list) or not items:
            raise RuntimeError(f"Expected non-empty audit items, got: {audit_resp}")
        if not any(isinstance(i, dict) and i.get("requestId") == rid_seed for i in items):
            raise RuntimeError(f"Expected requestId filtered items, got: {items}")

        # Verify sensitive fields are redacted at rest in DB.
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()

            # Verify DB privileges for audit_log roles.
            priv_rows = (
                conn.execute(
                    text(
                        """
                        SELECT
                          has_table_privilege('gangqing_app', 'audit_log', 'INSERT') AS app_insert,
                          has_table_privilege('gangqing_app', 'audit_log', 'UPDATE') AS app_update,
                          has_table_privilege('gangqing_app', 'audit_log', 'DELETE') AS app_delete,
                          has_table_privilege('gangqing_auditor', 'audit_log', 'SELECT') AS auditor_select,
                          has_table_privilege('gangqing_auditor', 'audit_log', 'INSERT') AS auditor_insert,
                          has_table_privilege('gangqing_auditor', 'audit_log', 'UPDATE') AS auditor_update,
                          has_table_privilege('gangqing_auditor', 'audit_log', 'DELETE') AS auditor_delete
                        """
                    )
                )
                .mappings()
                .one()
            )
            if not priv_rows.get("app_insert"):
                raise RuntimeError(f"Expected gangqing_app INSERT on audit_log, got: {priv_rows}")
            if priv_rows.get("app_update") or priv_rows.get("app_delete"):
                raise RuntimeError(f"Expected gangqing_app no UPDATE/DELETE on audit_log, got: {priv_rows}")
            if not priv_rows.get("auditor_select"):
                raise RuntimeError(f"Expected gangqing_auditor SELECT on audit_log, got: {priv_rows}")
            if priv_rows.get("auditor_insert") or priv_rows.get("auditor_update") or priv_rows.get("auditor_delete"):
                raise RuntimeError(
                    f"Expected gangqing_auditor read-only on audit_log, got: {priv_rows}"
                )

            # Query is audited (secondary audit): audit.query must be written for the audit/events request.
            audit_query_rows = (
                conn.execute(
                    text(
                        """
                        SELECT event_type, action_summary
                        FROM audit_log
                        WHERE tenant_id = :tenant_id
                          AND project_id = :project_id
                          AND request_id = :rid
                          AND event_type = 'audit.query'
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "rid": "rid_audit_log_smoke_query_1",
                    },
                )
                .mappings()
                .all()
            )
            if not audit_query_rows:
                raise RuntimeError("Expected audit.query event for audit/events request")
            audit_query_action = audit_query_rows[0].get("action_summary") or {}
            query_obj = (audit_query_action.get("query") or {}) if isinstance(audit_query_action, dict) else {}
            if query_obj.get("requestId") != rid_seed:
                raise RuntimeError(
                    f"Expected audit.query summary to include requestId={rid_seed}, got: {audit_query_action}"
                )
            row = (
                conn.execute(
                    text(
                        """
                        SELECT action_summary::text AS action_summary_text
                        FROM audit_log
                        WHERE tenant_id = :tenant_id
                          AND project_id = :project_id
                          AND request_id = :request_id
                          AND resource = 'audit_log_smoke_seed'
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "request_id": rid_seed,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise RuntimeError("Seeded audit row not found")
            text_summary = (row.get("action_summary_text") or "").lower()
            if "bearer" in text_summary or "postgresql://" in text_summary:
                raise RuntimeError(
                    "Sensitive values must be redacted in action_summary at rest"
                )
            if "[redacted]" not in text_summary:
                raise RuntimeError(f"Expected [REDACTED] marker, got: {row}")

        print("audit_log_smoke_test: PASS")
        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
