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
    raise RuntimeError(
        f"Server did not open port in time: {host}:{port}. Last error: {last_err}"
    )


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
                "source_record_id": f"smoke:sse:{tenant_id}:{project_id}:{now_dt}",
            },
        )
        conn.commit()


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


def _disconnect_after_meta(
    *,
    url: str,
    headers: dict[str, str],
    message: str,
    timeout_seconds: float,
) -> tuple[dict, float]:
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
    deadline = time.time() + timeout_seconds
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
                return payload, time.time()

    raise RuntimeError("Did not receive any SSE event before deadline")


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

                    evt_type = str(payload.get("type") or "")
                    if evt_type == "final":
                        return events

            return events

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        raise RuntimeError(
            f"chat.stream failed: status={e.code}, body={raw}"
        ) from e


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
    _seed_minimal_production_daily(
        database_url=database_url,
        tenant_id=tenant_id,
        project_id=project_id,
    )

    bootstrap_admin_user_id = (
        os.environ.get("GANGQING_BOOTSTRAP_ADMIN_USER_ID") or ""
    ).strip()
    bootstrap_admin_password = (
        os.environ.get("GANGQING_BOOTSTRAP_ADMIN_PASSWORD") or ""
    ).strip()
    if not bootstrap_admin_user_id or not bootstrap_admin_password:
        raise RuntimeError(
            "Missing required env vars: GANGQING_BOOTSTRAP_ADMIN_USER_ID/GANGQING_BOOTSTRAP_ADMIN_PASSWORD"
        )

    request_id_success = "rid_sse_smoke_success_1"
    request_id_error = "rid_sse_smoke_error_1"
    request_id_disconnect = "rid_sse_smoke_disconnect_1"

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    env["GANGQING_TOOL_MAX_RETRIES"] = "1"
    env["GANGQING_TOOL_BACKOFF_BASE_MS"] = "0"
    env["GANGQING_TOOL_BACKOFF_MAX_MS"] = "0"
    env["GANGQING_TOOL_BACKOFF_JITTER_RATIO"] = "0"

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

        base_headers_success = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id_success,
            "Content-Type": "application/json",
        }

        login_url = f"http://{host}:{port}/api/v1/auth/login"
        status, body = _request_json(
            login_url,
            method="POST",
            headers=base_headers_success,
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed: status={status}, body={body}")

        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in login response: {body}")

        chat_url = f"http://{host}:{port}/api/v1/chat/stream"
        chat_headers_success = {
            **base_headers_success,
            "Authorization": f"Bearer {access_token}",
        }

        ok_events = _read_sse_events(
            url=chat_url,
            headers=chat_headers_success,
            message="query",
            timeout_seconds=20.0,
        )
        if not ok_events:
            raise RuntimeError("Expected non-empty SSE events in success path")
        if str(ok_events[0].get("type")) != "meta":
            raise RuntimeError(
                f"Expected first SSE event type=meta, got: {ok_events[0].get('type')}"
            )
        if str(ok_events[-1].get("type")) != "final":
            raise RuntimeError(
                f"Expected last SSE event type=final, got: {ok_events[-1].get('type')}"
            )
        if (ok_events[-1].get("payload") or {}).get("status") != "success":
            raise RuntimeError(
                f"Expected final.payload.status=success, got: {ok_events[-1].get('payload')}"
            )

        ok_request_ids = {str(e.get("requestId") or "") for e in ok_events}
        if ok_request_ids != {request_id_success}:
            raise RuntimeError(
                f"Expected all success SSE events to have requestId={request_id_success}, got: {sorted(ok_request_ids)}"
            )
        ok_sequences: list[int] = []
        for e in ok_events:
            seq = e.get("sequence")
            if not isinstance(seq, int):
                raise RuntimeError(f"Expected sequence to be int, got: {type(seq)}")
            ok_sequences.append(seq)
        for prev, cur in zip(ok_sequences, ok_sequences[1:]):
            if cur <= prev:
                raise RuntimeError(f"Expected strictly increasing sequence, got {prev} -> {cur}")

        if not any(str(e.get("type") or "") == "message.delta" for e in ok_events):
            raise RuntimeError(
                f"Expected success SSE events to include type=message.delta, types={[str(e.get('type') or '') for e in ok_events]}"
            )

        evidence_update_events = [
            e for e in ok_events if str(e.get("type") or "") == "evidence.update"
        ]
        if evidence_update_events:
            for e in evidence_update_events:
                payload = e.get("payload")
                if not isinstance(payload, dict):
                    raise RuntimeError(
                        f"Expected evidence.update.payload to be object, got: {type(payload)}"
                    )

                mode = str(payload.get("mode") or "")
                if mode not in {"append", "update", "reference"}:
                    raise RuntimeError(
                        f"Invalid evidence.update.payload.mode. expected append|update|reference, got: {mode}"
                    )

                if mode in {"append", "update"}:
                    evidences = payload.get("evidences")
                    if not isinstance(evidences, list) or len(evidences) < 1:
                        raise RuntimeError(
                            "evidence.update payload.evidences is required for mode append|update"
                        )

                if mode == "reference":
                    evidence_ids = payload.get("evidenceIds")
                    if not isinstance(evidence_ids, list) or len(evidence_ids) < 1:
                        raise RuntimeError(
                            "evidence.update payload.evidenceIds is required for mode reference"
                        )

        base_headers_error = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id_error,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

        err_events = _read_sse_events(
            url=chat_url,
            headers=base_headers_error,
            message="timeout slow",
            timeout_seconds=20.0,
        )
        if not err_events:
            raise RuntimeError("Expected non-empty SSE events in error path")

        types = [str(e.get("type") or "") for e in err_events]
        if types[0] != "meta":
            raise RuntimeError(f"Expected first SSE event type=meta, got: {types[0]}")
        if types[-1] != "final":
            raise RuntimeError(f"Expected last SSE event type=final, got: {types[-1]}")
        if "error" not in types:
            raise RuntimeError(f"Expected SSE error path to include type=error, types={types}")

        error_positions = [idx for idx, t in enumerate(types) if t == "error"]
        if not error_positions:
            raise RuntimeError("Expected at least one error event")
        last_error_pos = error_positions[-1]
        if last_error_pos != len(types) - 2:
            raise RuntimeError(
                f"Expected error event to be immediately before final, got error_pos={last_error_pos}, total={len(types)}"
            )

        error_payload = err_events[last_error_pos].get("payload")
        if not isinstance(error_payload, dict):
            raise RuntimeError(f"Expected error.payload to be object, got: {type(error_payload)}")
        for required_key in ["code", "message", "retryable", "requestId"]:
            if required_key not in error_payload:
                raise RuntimeError(f"Missing required key in error.payload: {required_key}")
        msg = str(error_payload.get("message") or "")
        if any("\u4e00" <= ch <= "\u9fff" for ch in msg):
            raise RuntimeError(f"Expected ErrorResponse.message to be English, got: {msg}")

        final_payload = err_events[-1].get("payload") or {}
        if final_payload.get("status") != "error":
            raise RuntimeError(
                f"Expected final.payload.status=error, got: {final_payload}"
            )

        err_request_ids = {str(e.get("requestId") or "") for e in err_events}
        if err_request_ids != {request_id_error}:
            raise RuntimeError(
                f"Expected all error SSE events to have requestId={request_id_error}, got: {sorted(err_request_ids)}"
            )
        err_sequences: list[int] = []
        for e in err_events:
            seq = e.get("sequence")
            if not isinstance(seq, int):
                raise RuntimeError(f"Expected sequence to be int, got: {type(seq)}")
            err_sequences.append(seq)
        for prev, cur in zip(err_sequences, err_sequences[1:]):
            if cur <= prev:
                raise RuntimeError(f"Expected strictly increasing sequence, got {prev} -> {cur}")

        disconnect_headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id_disconnect,
            "Authorization": f"Bearer {access_token}",
        }
        first_evt, disconnect_ts = _disconnect_after_meta(
            url=chat_url,
            headers=disconnect_headers,
            message="query",
            timeout_seconds=10.0,
        )
        if str(first_evt.get("type") or "") != "meta":
            raise RuntimeError(f"Expected first event before disconnect to be meta, got: {first_evt}")

        deadline = time.time() + 1.5
        while time.time() < deadline:
            if _count_tool_calls_since(
                database_url=database_url,
                tenant_id=tenant_id,
                project_id=project_id,
                request_id=request_id_disconnect,
                since_ts_epoch_seconds=disconnect_ts,
            ) != 0:
                raise RuntimeError("Expected no tool_call audit events after disconnect")
            time.sleep(0.1)

        print(
            "sse_smoke_ok",
            {
                "successEventCount": len(ok_events),
                "errorEventCount": len(err_events),
                "requestIdSuccess": request_id_success,
                "requestIdError": request_id_error,
                "requestIdDisconnect": request_id_disconnect,
            },
        )
        return 0

    finally:
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


if __name__ == "__main__":
    raise SystemExit(main())
