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


def _assert_error_response(obj: dict) -> None:
    keys = sorted(obj.keys())
    if keys != ["code", "details", "message", "requestId", "retryable"]:
        raise AssertionError(f"Unexpected error response keys: {keys}")
    if not isinstance(obj.get("code"), str):
        raise AssertionError(f"Unexpected code type: {type(obj.get('code'))}")
    if not isinstance(obj.get("message"), str):
        raise AssertionError(f"Unexpected message type: {type(obj.get('message'))}")


def _assert_audit_events_response(obj: dict) -> None:
    keys = sorted(obj.keys())
    if keys != ["items", "total"]:
        raise AssertionError(f"Unexpected audit events response keys: {keys}")
    if not isinstance(obj.get("total"), int):
        raise AssertionError(f"Unexpected audit events total: {obj.get('total')}")
    if not isinstance(obj.get("items"), list):
        raise AssertionError(f"Unexpected audit events items type: {type(obj.get('items'))}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    if not (os.environ.get("GANGQING_DATABASE_URL") or "").strip():
        raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL")

    host = os.environ.get("GANGQING_API_HOST", "127.0.0.1")
    port = int(os.environ.get("GANGQING_API_PORT", "8000"))

    tenant_id = os.environ.get("GANGQING_TENANT_ID", "t1")
    project_id = os.environ.get("GANGQING_PROJECT_ID", "p1")

    bootstrap_admin_user_id = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_USER_ID") or "").strip()
    bootstrap_admin_password = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if not bootstrap_admin_user_id or not bootstrap_admin_password:
        raise RuntimeError(
            "Missing required env vars: GANGQING_BOOTSTRAP_ADMIN_USER_ID/GANGQING_BOOTSTRAP_ADMIN_PASSWORD"
        )

    finance_user_id = (os.environ.get("GANGQING_BOOTSTRAP_FINANCE_USER_ID") or "").strip()
    finance_password = (os.environ.get("GANGQING_BOOTSTRAP_FINANCE_PASSWORD") or "").strip()
    if not finance_user_id or not finance_password:
        raise RuntimeError(
            "Missing required env vars: GANGQING_BOOTSTRAP_FINANCE_USER_ID/GANGQING_BOOTSTRAP_FINANCE_PASSWORD"
        )

    database_url = (os.environ.get("GANGQING_DATABASE_URL") or "").strip()

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

        # Seed one audit row that contains finance-like sensitive fields in actionSummary.
        # This must not leak to non-finance roles in /audit/events response.
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
            conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})
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
                        'query',
                        now(),
                        :request_id,
                        :tenant_id,
                        :project_id,
                        NULL,
                        :user_id,
                        :role,
                        'masking_smoke_seed',
                        CAST(:action_summary AS jsonb),
                        'success',
                        NULL,
                        NULL
                    )
                    """
                ),
                {
                    "request_id": "rid_rbac_masking_smoke_seed",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "user_id": "seed",
                    "role": "system",
                    "action_summary": json.dumps(
                        {
                            "unit_cost": 12.34,
                            "total_cost": 99.9,
                            "safe": "ok",
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            conn.commit()

        base_headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": "rid_rbac_masking_smoke_1",
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
        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in login response: {body}")

        status, fin_body = _request_json(
            login_url,
            method="POST",
            headers={**base_headers, "X-Request-Id": "rid_rbac_masking_smoke_fin_login"},
            body={"username": finance_user_id, "password": finance_password},
        )
        if status != 200:
            raise RuntimeError(f"Finance login failed: status={status}, body={fin_body}")
        fin_token = (fin_body.get("accessToken") or "").strip()
        if not fin_token:
            raise RuntimeError(f"Missing finance accessToken: {fin_body}")

        status, err = _request_json(
            login_url,
            method="POST",
            headers={
                "X-Project-Id": project_id,
                "X-Request-Id": "rid_rbac_masking_smoke_missing_scope",
                "Content-Type": "application/json",
            },
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 401:
            raise RuntimeError(f"Expected 401 for missing scope header, got {status}: {err}")
        _assert_error_response(err)
        if err.get("code") != "AUTH_ERROR":
            raise RuntimeError(f"Expected AUTH_ERROR, got: {err}")

        chat_url = f"http://{host}:{port}/api/v1/chat/stream"
        status, err = _request_json(
            f"http://{host}:{port}/api/v1/chat/stream",
            method="POST",
            headers={
                **base_headers,
                "X-Tenant-Id": "t_other",
                "X-Request-Id": "rid_rbac_masking_smoke_scope_mismatch",
                "Authorization": f"Bearer {access_token}",
            },
            body={"message": "hello"},
        )
        if status != 401:
            raise RuntimeError(f"Expected 401 for token scope mismatch, got {status}: {err}")
        _assert_error_response(err)
        if err.get("code") != "AUTH_ERROR":
            raise RuntimeError(f"Expected AUTH_ERROR for scope mismatch, got: {err}")

        # Verify audit row exists for auth.denied and does not contain sensitive raw data.
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
            conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})
            conn.commit()
            rows = (
                conn.execute(
                    text(
                        """
                        SELECT event_type, action_summary::text AS action_summary_text
                        FROM audit_log
                        WHERE request_id = :rid
                        ORDER BY timestamp DESC
                        """
                    ),
                    {"rid": "rid_rbac_masking_smoke_scope_mismatch"},
                )
                .mappings()
                .all()
            )
            if not rows:
                raise RuntimeError("Expected audit rows for scope mismatch requestId, found none")
            denied = [r for r in rows if r.get("event_type") == "auth.denied"]
            if not denied:
                raise RuntimeError(f"Expected auth.denied audit event, got: {rows}")
            action_summary_text = (denied[0].get("action_summary_text") or "")
            if "12.34" in action_summary_text or "unit_cost" in action_summary_text:
                raise RuntimeError(
                    "Audit action_summary must not contain sensitive raw data for denied events"
                )

        audit_url = f"http://{host}:{port}/api/v1/audit/events"
        status, audit_resp_pm = _request_json(
            audit_url,
            method="GET",
            headers={
                **base_headers,
                "X-Request-Id": "rid_rbac_masking_smoke_audit",
                "Authorization": f"Bearer {access_token}",
            },
            body=None,
        )
        if status != 200:
            raise RuntimeError(f"audit.events failed: status={status}, body={audit_resp_pm}")
        _assert_audit_events_response(audit_resp_pm)
        for item in audit_resp_pm.get("items") or []:
            if item.get("tenantId") != tenant_id or item.get("projectId") != project_id:
                raise RuntimeError(f"Audit events include cross-scope item: {item}")

        seeded = [i for i in (audit_resp_pm.get("items") or []) if i.get("resource") == "masking_smoke_seed"]
        if not seeded:
            raise RuntimeError("Seeded audit row not found in admin response")
        seeded_action = (seeded[0].get("actionSummary") or {})
        if seeded_action.get("unit_cost") != "[MASKED]":
            raise RuntimeError(f"Expected unit_cost masked for admin, got: {seeded_action}")
        if (seeded_action.get("masking") or {}).get("policyId") != "masking_default":
            raise RuntimeError(f"Expected masking meta for admin, got: {seeded_action}")

        status, audit_resp_fin = _request_json(
            audit_url,
            method="GET",
            headers={
                **base_headers,
                "X-Request-Id": "rid_rbac_masking_smoke_audit_fin",
                "Authorization": f"Bearer {fin_token}",
            },
            body=None,
        )
        if status != 403:
            raise RuntimeError(
                f"Expected 403 for finance audit read, got status={status}, body={audit_resp_fin}"
            )
        _assert_error_response(audit_resp_fin)
        if audit_resp_fin.get("code") != "FORBIDDEN":
            raise RuntimeError(f"Expected FORBIDDEN, got: {audit_resp_fin}")

        # Verify data.masked audit event exists for /audit/events when admin sees masked fields.
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
            conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})
            conn.commit()
            masked_rows = (
                conn.execute(
                    text(
                        """
                        SELECT event_type, action_summary
                        FROM audit_log
                        WHERE request_id = :rid
                          AND event_type = 'data.masked'
                        """
                    ),
                    {"rid": "rid_rbac_masking_smoke_audit"},
                )
                .mappings()
                .all()
            )
            if not masked_rows:
                raise RuntimeError("Expected data.masked audit event for /audit/events request")
            policy_hits = (masked_rows[0].get("action_summary") or {}).get("policyHits")
            if not policy_hits:
                raise RuntimeError(f"Expected policyHits in data.masked action_summary, got: {masked_rows[0]}")

        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
