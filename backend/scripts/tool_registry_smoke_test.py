from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy import text

from gangqing.common.auth import create_access_token


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
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: dict | None = None,
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


def _build_alembic_config(*, repo_root: Path) -> Config:
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    if not alembic_ini_path.exists():
        raise RuntimeError("Missing required file: backend/alembic.ini")

    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


def _seed_minimal_production_daily(*, database_url: str, tenant_id: str, project_id: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})
        conn.commit()

        now = time.time()
        now_dt = time.strftime("%Y-%m-%d", time.gmtime(now))
        conn.execute(
            text(
                """
                INSERT INTO fact_production_daily(
                    tenant_id, project_id, business_date, equipment_id,
                    quantity, unit, source_system, source_record_id,
                    time_start, time_end, extracted_at
                ) VALUES (
                    :tenant_id, :project_id, CAST(:business_date AS date), NULL,
                    1.0, 'kg', 'smoke', :source_record_id,
                    NOW() - interval '1 hour', NOW(), NOW()
                )
                ON CONFLICT (tenant_id, project_id, business_date, equipment_id) DO NOTHING
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "business_date": now_dt,
                "source_record_id": f"smoke:tool_registry:{tenant_id}:{project_id}:{now_dt}",
            },
        )
        conn.commit()


def _assert_audit_has_denied(
    *,
    database_url: str,
    tenant_id: str,
    project_id: str,
    request_id: str,
) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})
        conn.commit()

        rows = conn.execute(
            text(
                """
                SELECT event_type, error_code
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id = :request_id
                  AND event_type = 'rbac.denied'
                ORDER BY timestamp DESC
                LIMIT 5
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "request_id": request_id},
        ).mappings().all()

    if not rows:
        raise RuntimeError("Expected audit_log to include rbac.denied for unauthorized tool call")


def _assert_has_error_code(*, events: list[dict], expected_code: str) -> None:
    error_events = [e for e in events if str(e.get("type") or "") == "error"]
    if not error_events:
        raise RuntimeError("Expected at least one error event")
    payload = error_events[-1].get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid error payload: {payload}")
    code = str(payload.get("code") or "")
    if code != expected_code:
        raise RuntimeError(f"Expected error.code={expected_code}, got: {code}")


def _read_sse_events(
    *,
    url: str,
    headers: dict[str, str],
    message: str,
    timeout_seconds: float,
) -> list[dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    events: list[dict] = []
    deadline = time.time() + timeout_seconds
    try:
        with opener.open(req, timeout=10.0) as resp:
            if resp.status != 200:
                raise RuntimeError(f"chat.stream failed: status={resp.status}")

            current_data_lines: list[str] = []
            while time.time() < deadline:
                raw = resp.readline()
                if not raw:
                    break

                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if line.endswith("\r"):
                    line = line[:-1]

                if line.startswith("data: "):
                    current_data_lines.append(line[len("data: ") :])
                    continue

                if line == "":
                    if not current_data_lines:
                        continue

                    data_raw = "\n".join(current_data_lines)
                    current_data_lines = []

                    payload = json.loads(data_raw)
                    events.append(payload)

                    if str(payload.get("type") or "") == "final":
                        return events

            return events

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        raise RuntimeError(f"chat.stream failed: status={e.code}, body={raw}") from e


def _assert_sequence_monotonic(events: list[dict]) -> None:
    seqs: list[int] = []
    for e in events:
        seq = e.get("sequence")
        if not isinstance(seq, int):
            raise RuntimeError(f"Missing/invalid sequence in event: {e}")
        seqs.append(seq)
    if not seqs:
        raise RuntimeError("Expected non-empty events for sequence validation")
    if seqs[0] != 1:
        raise RuntimeError(f"Expected first sequence=1, got {seqs[0]}")
    for i in range(1, len(seqs)):
        if seqs[i] <= seqs[i - 1]:
            raise RuntimeError(f"Expected monotonic increasing sequence, got {seqs}")


def _assert_tool_events_contract_success(events: list[dict]) -> None:
    tool_call_events = [e for e in events if str(e.get("type") or "") == "tool.call"]
    tool_result_events = [e for e in events if str(e.get("type") or "") == "tool.result"]

    if not tool_call_events:
        raise RuntimeError("Expected at least one tool.call event")
    if not tool_result_events:
        raise RuntimeError("Expected at least one tool.result event")

    call_payload = tool_call_events[0].get("payload")
    if not isinstance(call_payload, dict):
        raise RuntimeError(f"Invalid tool.call payload: {call_payload}")

    tool_call_id = str(call_payload.get("toolCallId") or "").strip()
    tool_name = str(call_payload.get("toolName") or "").strip()
    args_summary = call_payload.get("argsSummary")
    if not tool_call_id:
        raise RuntimeError(f"Missing toolCallId in tool.call: {call_payload}")
    if not tool_name:
        raise RuntimeError(f"Missing toolName in tool.call: {call_payload}")
    if not isinstance(args_summary, dict):
        raise RuntimeError(f"Invalid argsSummary in tool.call: {call_payload}")

    result_payload = tool_result_events[-1].get("payload")
    if not isinstance(result_payload, dict):
        raise RuntimeError(f"Invalid tool.result payload: {result_payload}")

    if str(result_payload.get("status") or "") != "success":
        raise RuntimeError(f"Expected tool.result.status=success, got: {result_payload}")

    if str(result_payload.get("toolCallId") or "").strip() != tool_call_id:
        raise RuntimeError(
            f"toolCallId mismatch between tool.call and tool.result: call={tool_call_id}, result={result_payload.get('toolCallId')}"
        )

    rs = result_payload.get("resultSummary")
    if rs is not None and not isinstance(rs, dict):
        raise RuntimeError(f"Invalid resultSummary in tool.result: {result_payload}")

    evidence_refs = result_payload.get("evidenceRefs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise RuntimeError(f"Expected non-empty evidenceRefs in tool.result: {result_payload}")
    if not all(isinstance(x, str) and x.strip() for x in evidence_refs):
        raise RuntimeError(f"Invalid evidenceRefs in tool.result: {result_payload}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    if not (os.environ.get("GANGQING_DATABASE_URL") or "").strip():
        raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL")

    database_url = (os.environ.get("GANGQING_DATABASE_URL") or "").strip()

    host = os.environ.get("GANGQING_API_HOST", "127.0.0.1")
    port = int(os.environ.get("GANGQING_API_PORT", "8000"))

    tenant_id = os.environ.get("GANGQING_TENANT_ID", "t1")
    project_id = os.environ.get("GANGQING_PROJECT_ID", "p1")

    cfg = _build_alembic_config(repo_root=repo_root)
    command.upgrade(cfg, "head")
    _seed_minimal_production_daily(database_url=database_url, tenant_id=tenant_id, project_id=project_id)

    bootstrap_admin_user_id = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_USER_ID") or "").strip()
    bootstrap_admin_password = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if not bootstrap_admin_user_id or not bootstrap_admin_password:
        raise RuntimeError(
            "Missing required env vars: GANGQING_BOOTSTRAP_ADMIN_USER_ID/GANGQING_BOOTSTRAP_ADMIN_PASSWORD"
        )

    request_id_enabled = "rid_tool_registry_enabled_1"
    request_id_disabled = "rid_tool_registry_disabled_1"
    request_id_unauthorized = "rid_tool_registry_unauthorized_1"
    request_id_timeout = "rid_tool_registry_timeout_1"
    request_id_contract_violation = "rid_tool_registry_contract_violation_1"

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    env.setdefault("GANGQING_TOOL_REGISTRY_ENABLED", "true")
    env.setdefault("GANGQING_TOOL_ENABLED_LIST", "")
    env.setdefault("GANGQING_TOOL_DISABLED_LIST", "")

    backend_dir = repo_root / "backend"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(backend_dir) if not existing_pythonpath else f"{backend_dir}{os.pathsep}{existing_pythonpath}"
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

    def _start_server(*, server_env: dict[str, str]) -> subprocess.Popen[str]:
        return subprocess.Popen(
            cmd,
            env=server_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    def _stop_server(proc: subprocess.Popen[str]) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)

        try:
            if proc.stdout is not None:
                selector = selectors.DefaultSelector()
                selector.register(proc.stdout, selectors.EVENT_READ)
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    for key, _ in selector.select(timeout=0.2):
                        _ = key.fileobj.readline()
        except Exception:
            pass

        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass

    base_headers = {
        "X-Tenant-Id": tenant_id,
        "X-Project-Id": project_id,
        "Content-Type": "application/json",
    }

    login_url = f"http://{host}:{port}/api/v1/auth/login"
    chat_url = f"http://{host}:{port}/api/v1/chat/stream"

    enabled_events: list[dict] = []
    disabled_events: list[dict] = []
    unauthorized_events: list[dict] = []
    timeout_events: list[dict] = []
    contract_violation_events: list[dict] = []

    proc = _start_server(server_env=env)
    try:
        _wait_for_port(host, port, timeout_seconds=10.0)

        status, body = _request_json(
            login_url,
            method="POST",
            headers={**base_headers, "X-Request-Id": request_id_enabled},
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed: status={status}, body={body}")

        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in login response: {body}")

        enabled_events = _read_sse_events(
            url=chat_url,
            headers={
                **base_headers,
                "X-Request-Id": request_id_enabled,
                "Authorization": f"Bearer {access_token}",
            },
            message="query production daily",
            timeout_seconds=20.0,
        )
        enabled_types = [str(e.get("type") or "") for e in enabled_events]
        if "tool.call" not in enabled_types:
            raise RuntimeError(f"Expected tool.call when tool enabled, types={enabled_types}")

        _assert_sequence_monotonic(enabled_events)
        _assert_tool_events_contract_success(enabled_events)
    finally:
        _stop_server(proc)

    env_disabled = env.copy()
    env_disabled["GANGQING_TOOL_DISABLED_LIST"] = "postgres_readonly_query"
    proc2 = _start_server(server_env=env_disabled)
    try:
        _wait_for_port(host, port, timeout_seconds=10.0)

        status, body = _request_json(
            login_url,
            method="POST",
            headers={**base_headers, "X-Request-Id": request_id_disabled},
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed: status={status}, body={body}")

        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in login response: {body}")

        disabled_events = _read_sse_events(
            url=chat_url,
            headers={
                **base_headers,
                "X-Request-Id": request_id_disabled,
                "Authorization": f"Bearer {access_token}",
            },
            message="query production daily",
            timeout_seconds=20.0,
        )
        disabled_types = [str(e.get("type") or "") for e in disabled_events]
        if "tool.call" in disabled_types:
            raise RuntimeError(f"Expected no tool.call when tool disabled, types={disabled_types}")

        _assert_sequence_monotonic(disabled_events)
    finally:
        _stop_server(proc2)

    proc3 = _start_server(server_env=env)
    try:
        _wait_for_port(host, port, timeout_seconds=10.0)

        access_token, _ = create_access_token(
            user_id="u_smoke_dispatcher",
            role="dispatcher",
            tenant_id=tenant_id,
            project_id=project_id,
        )

        unauthorized_events = _read_sse_events(
            url=chat_url,
            headers={
                **base_headers,
                "X-Request-Id": request_id_unauthorized,
                "Authorization": f"Bearer {access_token}",
            },
            message="query production daily",
            timeout_seconds=20.0,
        )

        unauthorized_types = [str(e.get("type") or "") for e in unauthorized_events]
        if "error" not in unauthorized_types:
            raise RuntimeError(f"Expected SSE to include error for unauthorized tool call, types={unauthorized_types}")
        if unauthorized_types[-1] != "final":
            raise RuntimeError(f"Expected last SSE event final for unauthorized tool call, got: {unauthorized_types[-1]}")
        final_payload = unauthorized_events[-1].get("payload") or {}
        if final_payload.get("status") != "error":
            raise RuntimeError(f"Expected final.payload.status=error, got: {final_payload}")

        _assert_sequence_monotonic(unauthorized_events)
        _assert_audit_has_denied(
            database_url=database_url,
            tenant_id=tenant_id,
            project_id=project_id,
            request_id=request_id_unauthorized,
        )
    finally:
        _stop_server(proc3)

    proc4 = _start_server(server_env=env)
    try:
        _wait_for_port(host, port, timeout_seconds=10.0)

        status, body = _request_json(
            login_url,
            method="POST",
            headers={**base_headers, "X-Request-Id": request_id_timeout},
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed for timeout smoke: status={status}, body={body}")
        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in timeout login response: {body}")

        timeout_events = _read_sse_events(
            url=chat_url,
            headers={
                **base_headers,
                "X-Request-Id": request_id_timeout,
                "Authorization": f"Bearer {access_token}",
            },
            message="query production daily slow timeout",
            timeout_seconds=20.0,
        )

        timeout_types = [str(e.get("type") or "") for e in timeout_events]
        if "error" not in timeout_types:
            raise RuntimeError(f"Expected SSE to include error for timeout case, types={timeout_types}")
        if timeout_types[-1] != "final":
            raise RuntimeError(f"Expected last SSE event final for timeout case, got: {timeout_types[-1]}")
        final_payload = timeout_events[-1].get("payload") or {}
        if final_payload.get("status") != "error":
            raise RuntimeError(f"Expected final.payload.status=error for timeout case, got: {final_payload}")

        _assert_sequence_monotonic(timeout_events)
        _assert_has_error_code(events=timeout_events, expected_code="UPSTREAM_TIMEOUT")
    finally:
        _stop_server(proc4)

    env_contract = env.copy()
    env_contract["GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION"] = "1"
    proc5 = _start_server(server_env=env_contract)
    try:
        _wait_for_port(host, port, timeout_seconds=10.0)

        status, body = _request_json(
            login_url,
            method="POST",
            headers={**base_headers, "X-Request-Id": request_id_contract_violation},
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed for contract violation smoke: status={status}, body={body}")
        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in contract violation login response: {body}")

        contract_violation_events = _read_sse_events(
            url=chat_url,
            headers={
                **base_headers,
                "X-Request-Id": request_id_contract_violation,
                "Authorization": f"Bearer {access_token}",
            },
            message="query production daily",
            timeout_seconds=20.0,
        )

        cv_types = [str(e.get("type") or "") for e in contract_violation_events]
        if "error" not in cv_types:
            raise RuntimeError(
                f"Expected SSE to include error for contract violation case, types={cv_types}"
            )
        if cv_types[-1] != "final":
            raise RuntimeError(
                f"Expected last SSE event final for contract violation case, got: {cv_types[-1]}"
            )
        final_payload = contract_violation_events[-1].get("payload") or {}
        if final_payload.get("status") != "error":
            raise RuntimeError(
                f"Expected final.payload.status=error for contract violation case, got: {final_payload}"
            )

        _assert_sequence_monotonic(contract_violation_events)
        _assert_has_error_code(events=contract_violation_events, expected_code="CONTRACT_VIOLATION")
    finally:
        _stop_server(proc5)

    print(
        "tool_registry_smoke_ok",
        {
            "enabledEventCount": len(enabled_events),
            "disabledEventCount": len(disabled_events),
            "unauthorizedEventCount": len(unauthorized_events),
            "timeoutEventCount": len(timeout_events),
            "contractViolationEventCount": len(contract_violation_events),
            "requestIdEnabled": request_id_enabled,
            "requestIdDisabled": request_id_disabled,
            "requestIdUnauthorized": request_id_unauthorized,
            "requestIdTimeout": request_id_timeout,
            "requestIdContractViolation": request_id_contract_violation,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
