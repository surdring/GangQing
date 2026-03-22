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
                "source_record_id": f"smoke:evidence:{tenant_id}:{project_id}:{now_dt}",
            },
        )
        conn.commit()


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
        raise RuntimeError(f"chat.stream failed: status={e.code}, body={raw}") from e


def _run_chat_scenario(
    *,
    repo_root: Path,
    host: str,
    port: int,
    tenant_id: str,
    project_id: str,
    request_id: str,
    bootstrap_admin_user_id: str,
    bootstrap_admin_password: str,
    force_evidence_validation: str | None,
) -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    if force_evidence_validation is not None:
        env["GANGQING_FORCE_POSTGRES_EVIDENCE_VALIDATION"] = force_evidence_validation
    else:
        env.pop("GANGQING_FORCE_POSTGRES_EVIDENCE_VALIDATION", None)

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

        base_headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id,
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

        chat_url = f"http://{host}:{port}/api/v1/chat/stream"
        chat_headers = {
            **base_headers,
            "Authorization": f"Bearer {access_token}",
        }

        events = _read_sse_events(
            url=chat_url,
            headers=chat_headers,
            message="查询 今日 产量 数据 多少",
            timeout_seconds=20.0,
        )
        if not events:
            raise RuntimeError("Expected non-empty SSE events")

        if str(events[0].get("type")) != "meta":
            raise RuntimeError(f"Expected first SSE event type=meta, got: {events[0].get('type')}")

        for evt in events:
            if str(evt.get("requestId") or "") != request_id:
                raise RuntimeError("All SSE envelopes must carry the same requestId")

        tool_results = [e for e in events if str(e.get("type")) == "tool.result"]
        if not tool_results:
            types = [str(e.get("type") or "") for e in events]
            raise RuntimeError(f"Expected at least one tool.result event. Received types={types}")

        warnings = [e for e in events if str(e.get("type")) == "warning"]
        evidence_updates = [e for e in events if str(e.get("type")) == "evidence.update"]

        last_tool_result = tool_results[-1]
        payload = last_tool_result.get("payload")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected tool.result.payload to be object, got: {payload}")

        if not evidence_updates:
            types = [str(e.get("type") or "") for e in events]
            raise RuntimeError(f"Expected at least one evidence.update event. Received types={types}")

        evidence_refs = payload.get("evidenceRefs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise RuntimeError(
                "Evidence refs missing in tool.result. "
                f"evidenceRefs={evidence_refs}, requestId={request_id}"
            )

        first_update_idx = next(i for i, e in enumerate(events) if str(e.get("type")) == "evidence.update")
        first_result_idx = next(i for i, e in enumerate(events) if str(e.get("type")) == "tool.result")
        if not (first_update_idx < first_result_idx):
            raise RuntimeError(
                f"Expected evidence.update before tool.result, got updateIdx={first_update_idx}, resultIdx={first_result_idx}"
            )

        updated_ids: set[str] = set()
        for evt in evidence_updates:
            p = evt.get("payload")
            if not isinstance(p, dict):
                continue
            mode = p.get("mode")
            if mode not in ("append", "update", "reference"):
                raise RuntimeError(f"Expected evidence.update.payload.mode to be append|update|reference, got: {mode}")

            if mode in ("append", "update"):
                evs = p.get("evidences")
                if not isinstance(evs, list) or not evs:
                    raise RuntimeError(
                        f"Expected evidence.update.payload.evidences to be non-empty list for mode={mode}, got: {evs}"
                    )
            else:
                ids = p.get("evidenceIds")
                if not isinstance(ids, list) or not ids:
                    raise RuntimeError(
                        f"Expected evidence.update.payload.evidenceIds to be non-empty list for mode=reference, got: {ids}"
                    )

            evs = p.get("evidences")
            if not isinstance(evs, list):
                continue
            for item in evs:
                if isinstance(item, dict) and isinstance(item.get("evidenceId"), str):
                    updated_ids.add(str(item.get("evidenceId")))

        missing_from_updates = [eid for eid in evidence_refs if eid not in updated_ids]
        if missing_from_updates:
            raise RuntimeError(
                f"tool.result evidenceRefs must reference evidence.update evidences. missing={missing_from_updates}"
            )

        if force_evidence_validation is not None:
            if not warnings:
                types = [str(e.get("type") or "") for e in events]
                raise RuntimeError(f"Expected warning event in degradation scenario. Received types={types}")

            first_warning = warnings[0]
            w_payload = first_warning.get("payload")
            if not isinstance(w_payload, dict):
                raise RuntimeError(f"Expected warning.payload object, got: {w_payload}")

            expected_code = {
                "not_verifiable": "EVIDENCE_MISSING",
                "mismatch": "EVIDENCE_MISMATCH",
                "out_of_bounds": "GUARDRAIL_BLOCKED",
            }.get(force_evidence_validation)
            if expected_code is None:
                raise RuntimeError(
                    f"Unsupported force_evidence_validation value: {force_evidence_validation}"
                )
            if str(w_payload.get("code") or "") != expected_code:
                raise RuntimeError(
                    f"Expected warning code={expected_code}, got: {w_payload.get('code')}"
                )

            msg = w_payload.get("message")
            if not isinstance(msg, str) or not msg.strip():
                raise RuntimeError(f"Expected non-empty warning.message, got: {msg}")

        if str(events[-1].get("type")) != "final":
            raise RuntimeError(f"Expected last SSE event type=final, got: {events[-1].get('type')}")

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


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    database_url = (os.environ.get("GANGQING_DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL")

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

    _run_chat_scenario(
        repo_root=repo_root,
        host=host,
        port=port,
        tenant_id=tenant_id,
        project_id=project_id,
        request_id="rid_evidence_smoke_success",
        bootstrap_admin_user_id=bootstrap_admin_user_id,
        bootstrap_admin_password=bootstrap_admin_password,
        force_evidence_validation=None,
    )

    _run_chat_scenario(
        repo_root=repo_root,
        host=host,
        port=port,
        tenant_id=tenant_id,
        project_id=project_id,
        request_id="rid_evidence_smoke_degraded",
        bootstrap_admin_user_id=bootstrap_admin_user_id,
        bootstrap_admin_password=bootstrap_admin_password,
        force_evidence_validation="not_verifiable",
    )

    _run_chat_scenario(
        repo_root=repo_root,
        host=host,
        port=port,
        tenant_id=tenant_id,
        project_id=project_id,
        request_id="rid_evidence_smoke_mismatch",
        bootstrap_admin_user_id=bootstrap_admin_user_id,
        bootstrap_admin_password=bootstrap_admin_password,
        force_evidence_validation="mismatch",
    )

    print(
        "evidence_smoke_ok",
        {
            "successRequestId": "rid_evidence_smoke_success",
            "degradedRequestId": "rid_evidence_smoke_degraded",
            "mismatchRequestId": "rid_evidence_smoke_mismatch",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
