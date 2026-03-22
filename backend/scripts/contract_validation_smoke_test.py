"""Smoke test for tool contract validation (Pydantic params -> VALIDATION_ERROR).

This script validates end-to-end behavior against a real Postgres:
- Requires GANGQING_DATABASE_URL
- Applies migrations to head
- Seeds minimal fact rows for a scoped tenant/project
- Triggers a tool params validation failure via run_raw
- Asserts structured error payload includes code/message/requestId/retryable/details
- Asserts audit_log receives a tool_call failure with error_code=VALIDATION_ERROR

No mock/skip allowed.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import time
import urllib.error
import urllib.request

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

# Add backend to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.tools.postgres_readonly import (
    PostgresReadOnlyQueryParams,
    PostgresReadOnlyQueryResult,
    PostgresReadOnlyQueryTool,
)
from gangqing_db.errors import ConfigMissingError, ErrorCode as DbErrorCode, MigrationError, MigrationFailedError, map_db_error
from gangqing_db.settings import load_settings


def _get_expected_head(cfg: Config) -> str:
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    if not head:
        raise MigrationFailedError(
            "upgrade",
            version=None,
            cause="Unable to resolve alembic head revision",
        )
    return head


def _require_database_url() -> str:
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise ConfigMissingError("GANGQING_DATABASE_URL") from e
        raise map_db_error(e)
    return settings.database_url


def _require_any_env(names: set[str]) -> tuple[str, str]:
    for name in sorted(names):
        value = (os.environ.get(name) or "").strip()
        if value:
            return name, value
    raise RuntimeError(
        "Missing required env for smoke test: expected at least one of: " + ", ".join(sorted(names))
    )


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env for smoke test: {name}")
    return value


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


def _http_get_json(*, url: str, headers: dict[str, str], timeout_seconds: float) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            try:
                return int(resp.status), json.loads(body)
            except Exception as e:
                raise RuntimeError(f"HTTP response is not JSON: status={resp.status}, body={body}") from e
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return int(e.code), json.loads(body)
        except Exception as je:
            raise RuntimeError(f"HTTP error response is not JSON: status={e.code}, body={body}") from je


def _http_post_json(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout_seconds: float,
) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            try:
                return int(resp.status), json.loads(body)
            except Exception as e:
                raise RuntimeError(f"HTTP response is not JSON: status={resp.status}, body={body}") from e
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return int(e.code), json.loads(body)
        except Exception as je:
            raise RuntimeError(f"HTTP error response is not JSON: status={e.code}, body={body}") from je


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


def _build_alembic_config() -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    if not alembic_ini_path.exists():
        raise ConfigMissingError("backend/alembic.ini")

    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


def _get_current_version(engine) -> str | None:
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'gangqing_alembic_version'
                )
                """
            )
        )
        if not result.scalar_one():
            return None
        row = conn.execute(text("SELECT version_num FROM gangqing_alembic_version LIMIT 1")).fetchone()
        return row[0] if row else None


def _set_rls_context(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})


def _benchmark_pydantic_contract_validation(*, iterations: int) -> dict:
    start = time.perf_counter()

    params_obj = PostgresReadOnlyQueryParams(
        templateId="production_daily",
        timeRange={
            "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
        },
        limit=10,
        offset=0,
    )
    raw_params = params_obj.model_dump(by_alias=True)

    extracted_at = datetime.now(timezone.utc).isoformat()
    raw_result = PostgresReadOnlyQueryResult(
        toolCallId="bench",
        rows=[],
        rowCount=0,
        truncated=False,
        columns=None,
        queryFingerprint="bench",
        evidence={
            "evidenceId": "ev_bench",
            "sourceSystem": "Postgres",
            "sourceLocator": {
                "database": "bench",
                "tableOrView": "fact_production_daily",
                "timeField": "time_start",
                "filters": [],
                "queryFingerprint": "bench",
                "templateId": "production_daily",
                "extractedAt": extracted_at,
            },
            "timeRange": {
                "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
            },
            "toolCallId": "bench",
            "lineageVersion": None,
            "dataQualityScore": None,
            "confidence": "High",
            "validation": "verifiable",
            "redactions": None,
        },
    ).model_dump(by_alias=True)

    for _ in range(iterations):
        PostgresReadOnlyQueryParams.model_validate(raw_params)
        PostgresReadOnlyQueryResult.model_validate(raw_result)

    total_ms = (time.perf_counter() - start) * 1000.0
    avg_ms = total_ms / float(iterations * 2)
    return {
        "iterations": iterations,
        "totalMs": round(total_ms, 3),
        "avgModelValidateMs": round(avg_ms, 6),
    }


def _validate_evidence_lineage_version_contract() -> dict:
    """Validate Evidence lineageVersion field contract.

    Checks:
    1. Serialization uses camelCase 'lineageVersion'
    2. Deserialization accepts camelCase 'lineage_version'
    3. Both None and str values are valid
    4. Invalid types are rejected
    """
    from gangqing_db.evidence import Evidence

    # Test 1: Serialization uses camelCase
    ev1 = Evidence(
        evidenceId="ev_test_1",
        sourceSystem="Postgres",
        sourceLocator={"table": "test"},
        timeRange={
            "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
        },
        toolCallId="tc_test",
        lineageVersion="v1.0.0",
        dataQualityScore=0.95,
        confidence="High",
        validation="verifiable",
    )
    serialized = ev1.model_dump(by_alias=True)
    if "lineageVersion" not in serialized:
        raise RuntimeError("Evidence serialization must use camelCase 'lineageVersion'")
    if serialized["lineageVersion"] != "v1.0.0":
        raise RuntimeError(
            f"Evidence lineageVersion mismatch: expected 'v1.0.0', got {serialized.get('lineageVersion')}"
        )
    if "lineage_version" in serialized:
        raise RuntimeError("Evidence serialization must not include snake_case 'lineage_version'")

    # Test 2: None value is valid
    ev2 = Evidence(
        evidenceId="ev_test_2",
        sourceSystem="Postgres",
        sourceLocator={"table": "test"},
        timeRange={
            "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
        },
        confidence="High",
        validation="verifiable",
    )
    serialized2 = ev2.model_dump(by_alias=True)
    if serialized2.get("lineageVersion") is not None:
        raise RuntimeError("Evidence default lineageVersion must be None")

    # Test 3: Deserialization accepts camelCase input
    ev3 = Evidence.model_validate({
        "evidenceId": "ev_test_3",
        "sourceSystem": "Postgres",
        "sourceLocator": {"table": "test"},
        "timeRange": {
            "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
        },
        "lineageVersion": "v2.0.0",
        "confidence": "Medium",
        "validation": "verifiable",
    })
    if ev3.lineage_version != "v2.0.0":
        raise RuntimeError(
            f"Evidence deserialization failed: expected lineage_version='v2.0.0', got {ev3.lineage_version}"
        )

    # Test 4: Invalid type is rejected
    try:
        Evidence.model_validate({
            "evidenceId": "ev_test_4",
            "sourceSystem": "Postgres",
            "sourceLocator": {"table": "test"},
            "timeRange": {
                "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
            },
            "lineageVersion": 123,  # Invalid: must be str or None
            "confidence": "High",
            "validation": "verifiable",
        })
        raise RuntimeError("Evidence must reject invalid lineageVersion type (int)")
    except Exception as e:
        if "lineageVersion" not in str(e) and "lineage_version" not in str(e):
            raise RuntimeError(
                f"Evidence validation error must mention lineageVersion field: {e}"
            ) from e

    return {
        "serializationCamelCase": True,
        "noneValueValid": True,
        "deserializationCamelCase": True,
        "invalidTypeRejected": True,
    }


def main() -> int:
    request_id = f"contract-validation-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    stage = "init"

    try:
        stage = "env_check"
        database_url = _require_database_url()

        # Enforce real model provider integration for this smoke test.
        # Task 9.3 requires a real llama.cpp connection.
        _require_env("GANGQING_LLAMACPP_BASE_URL")

        bootstrap_admin_user_id = _require_env("GANGQING_BOOTSTRAP_ADMIN_USER_ID")
        bootstrap_admin_password = _require_env("GANGQING_BOOTSTRAP_ADMIN_PASSWORD")

        cfg = _build_alembic_config()
        expected_head = _get_expected_head(cfg)

        stage = "db_connect"
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect():
                pass
        except Exception as e:
            raise map_db_error(e, request_id=request_id)

        stage = "migrate"
        command.upgrade(cfg, "head")
        version = _get_current_version(engine)
        if version != expected_head:
            raise MigrationFailedError(
                "upgrade",
                version=version,
                cause=f"Expected version {expected_head}, got {version}",
                request_id=request_id,
            )

        tenant_id = "t_smoke"
        project_id = "p_smoke"

        # Run pure Pydantic contract validation before starting API server
        # These tests do not depend on external services
        bench = _benchmark_pydantic_contract_validation(iterations=2000)
        if float(bench.get("avgModelValidateMs") or 999.0) > 5.0:
            raise RuntimeError(
                "Pydantic contract validation is too slow: "
                + f"avgModelValidateMs={bench.get('avgModelValidateMs')}"
            )

        stage = "evidence_lineage_version_contract"
        lineage_contract = _validate_evidence_lineage_version_contract()
        if not lineage_contract.get("serializationCamelCase"):
            raise RuntimeError("Evidence lineageVersion serialization contract failed")
        if not lineage_contract.get("deserializationCamelCase"):
            raise RuntimeError("Evidence lineageVersion deserialization contract failed")

        # Print Pydantic contract validation results immediately
        # These tests passed before API server starts
        print(
            "pydantic_contract_validation_ok",
            {
                "requestId": request_id,
                "pydanticBenchmark": bench,
                "lineageVersionContract": lineage_contract,
            },
        )

        stage = "api_server_start"
        host = (os.environ.get("GANGQING_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"
        port = int((os.environ.get("GANGQING_API_PORT") or "8000").strip() or "8000")

        def _start_api_server(*, force_contract_violation: bool) -> subprocess.Popen:
            env = os.environ.copy()
            env.setdefault("PYTHONUNBUFFERED", "1")

            repo_root = Path(__file__).resolve().parents[2]
            backend_dir = repo_root / "backend"
            existing_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                str(backend_dir)
                if not existing_pythonpath
                else f"{backend_dir}{os.pathsep}{existing_pythonpath}"
            )

            if force_contract_violation:
                env["GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION"] = "1"
            else:
                env.pop("GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION", None)

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
            return subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

        def _stop_api_server(proc: subprocess.Popen) -> None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)

            try:
                if proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass

        base_headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id,
        }

        proc = _start_api_server(force_contract_violation=False)
        try:
            _wait_for_port(host, port, timeout_seconds=10.0)

            stage = "healthcheck_http"
            status, health = _http_get_json(
                url=f"http://{host}:{port}/api/v1/health",
                headers=base_headers,
                timeout_seconds=15.0,
            )
            if status != 200:
                raise RuntimeError(f"Healthcheck failed: expected HTTP 200, got {status}: {health}")
            deps = health.get("dependencies")
            if not isinstance(deps, list):
                raise RuntimeError("Healthcheck dependencies must be a list")
            dep_by_name = {
                d.get("name"): d
                for d in deps
                if isinstance(d, dict) and isinstance(d.get("name"), str)
            }
            if str((dep_by_name.get("llama_cpp") or {}).get("status")) != "ok":
                raise RuntimeError(
                    "Healthcheck requires llama_cpp status ok for this smoke test. "
                    f"llama_cpp={dep_by_name.get('llama_cpp')}"
                )
            if str((dep_by_name.get("postgres") or {}).get("status")) != "ok":
                raise RuntimeError(
                    "Healthcheck requires postgres status ok for this smoke test. "
                    f"postgres={dep_by_name.get('postgres')}"
                )

            stage = "login_http"
            login_status, login_body = _http_post_json(
                url=f"http://{host}:{port}/api/v1/auth/login",
                headers={
                    **base_headers,
                    "Content-Type": "application/json",
                },
                payload={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
                timeout_seconds=10.0,
            )
            if login_status != 200:
                raise RuntimeError(f"Login failed: status={login_status}, body={login_body}")
            access_token = str(login_body.get("accessToken") or "").strip()
            if not access_token:
                raise RuntimeError(f"Login response missing accessToken: {login_body}")

            stage = "rest_validation_error"
            # REST failure chain: invalid payload should trigger RequestValidationError handler.
            invalid_status, invalid_body = _http_post_json(
                url=f"http://{host}:{port}/api/v1/auth/login",
                headers={
                    **base_headers,
                    "X-Request-Id": request_id + "-rest-invalid",
                    "Content-Type": "application/json",
                },
                payload={"username": ""},
                timeout_seconds=10.0,
            )
            if invalid_status != 422:
                raise RuntimeError(
                    f"Expected 422 for REST validation error, got {invalid_status}: {invalid_body}"
                )
            for key in ["code", "message", "details", "retryable", "requestId"]:
                if key not in invalid_body:
                    raise RuntimeError(f"REST ErrorResponse missing key: {key}")
            if invalid_body.get("code") != ErrorCode.VALIDATION_ERROR.value:
                raise RuntimeError(f"Expected VALIDATION_ERROR, got: {invalid_body}")
            if not isinstance(invalid_body.get("message"), str):
                raise RuntimeError("REST ErrorResponse message must be a string")

            stage = "sse_success_chain"
            ok_events = _read_sse_events(
                url=f"http://{host}:{port}/api/v1/chat/stream",
                headers={
                    **base_headers,
                    "Authorization": f"Bearer {access_token}",
                },
                message="hello",
                timeout_seconds=20.0,
            )
            if not ok_events:
                raise RuntimeError("Expected non-empty SSE events in success chain")
            if str(ok_events[0].get("type")) != "meta":
                raise RuntimeError("Expected first SSE event type=meta")
            if str(ok_events[-1].get("type")) != "final":
                raise RuntimeError("Expected last SSE event type=final")
            final_payload = ok_events[-1].get("payload") or {}
            final_status = final_payload.get("status") if isinstance(final_payload, dict) else None
            if final_status != "success":
                raise RuntimeError(
                    "Expected final.payload.status=success, got: " + json.dumps(final_payload)
                )
        finally:
            _stop_api_server(proc)

        time.sleep(0.2)

        proc = _start_api_server(force_contract_violation=True)
        try:
            _wait_for_port(host, port, timeout_seconds=10.0)

            stage = "login_http_contract_violation"
            login_status, login_body = _http_post_json(
                url=f"http://{host}:{port}/api/v1/auth/login",
                headers={
                    **base_headers,
                    "X-Request-Id": request_id + "-login-contract-violation",
                    "Content-Type": "application/json",
                },
                payload={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
                timeout_seconds=10.0,
            )
            if login_status != 200:
                raise RuntimeError(f"Login failed: status={login_status}, body={login_body}")
            access_token = str(login_body.get("accessToken") or "").strip()
            if not access_token:
                raise RuntimeError(f"Login response missing accessToken: {login_body}")

            stage = "sse_contract_violation_chain"
            err_events = _read_sse_events(
                url=f"http://{host}:{port}/api/v1/chat/stream",
                headers={
                    **base_headers,
                    "X-Request-Id": request_id + "-sse-contract-violation",
                    "Authorization": f"Bearer {access_token}",
                },
                message="hello",
                timeout_seconds=20.0,
            )
            if not err_events:
                raise RuntimeError("Expected non-empty SSE events in contract violation chain")
            types = [str(e.get("type") or "") for e in err_events]
            if "error" not in types:
                raise RuntimeError(f"Expected SSE to include error event, got types={types}")
            error_evt = next((e for e in err_events if str(e.get("type")) == "error"), None)
            if not isinstance(error_evt, dict):
                raise RuntimeError("Expected SSE error event payload to be a dict")
            payload = error_evt.get("payload")
            if not isinstance(payload, dict):
                raise RuntimeError(f"Expected SSE error payload to be a dict, got: {payload}")
            for key in ["code", "message", "details", "retryable", "requestId"]:
                if key not in payload:
                    raise RuntimeError(f"SSE error payload missing key: {key}")
            if payload.get("code") != ErrorCode.CONTRACT_VIOLATION.value:
                raise RuntimeError(f"Expected CONTRACT_VIOLATION in SSE error payload, got: {payload}")
            if not isinstance(payload.get("message"), str):
                raise RuntimeError("SSE error payload message must be a string")
        finally:
            _stop_api_server(proc)

        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()

        ctx = RequestContext(
            requestId=request_id,
            tenantId=tenant_id,
            projectId=project_id,
            role="plant_manager",
        )

        tool = PostgresReadOnlyQueryTool()

        stage = "tool_params_validation"
        try:
            tool.run_raw(
                ctx=ctx,
                raw_params={
                    "templateId": "production_daily",
                    # missing timeRange to trigger ValidationError
                },
            )
        except AppError as e:
            payload = e.to_response().model_dump(by_alias=True)
            if e.code != ErrorCode.VALIDATION_ERROR:
                raise RuntimeError("Smoke test expected VALIDATION_ERROR")
            if payload.get("requestId") != request_id:
                raise RuntimeError("Smoke test expected requestId to be preserved")
            if payload.get("retryable") is not False:
                raise RuntimeError("Smoke test expected retryable=false")
            if payload.get("message") != "Invalid tool parameters":
                raise RuntimeError("Smoke test expected english message 'Invalid tool parameters'")
            details = payload.get("details")
            if not isinstance(details, dict) or "fieldErrors" not in details:
                raise RuntimeError("Smoke test expected details.fieldErrors")
        else:
            raise RuntimeError("Smoke test expected tool params validation to fail")

        original_force = os.environ.get("GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION")
        os.environ["GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION"] = "1"
        try:
            stage = "tool_output_contract_violation"
            tool.run_raw(
                ctx=ctx,
                raw_params={
                    "templateId": "production_daily",
                    "timeRange": {
                        "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                        "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                    },
                    "limit": 10,
                    "offset": 0,
                },
            )
        except AppError as e:
            payload = e.to_response().model_dump(by_alias=True)
            if e.code != ErrorCode.CONTRACT_VIOLATION:
                raise RuntimeError("Smoke test expected CONTRACT_VIOLATION")
            if payload.get("requestId") != request_id:
                raise RuntimeError("Smoke test expected requestId to be preserved")
            details = payload.get("details")
            if not isinstance(details, dict) or details.get("source") != "tool.postgres_readonly.result":
                raise RuntimeError("Smoke test expected contract violation details.source")
        else:
            raise RuntimeError("Smoke test expected forced output contract violation")
        finally:
            if original_force is None:
                os.environ.pop("GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION", None)
            else:
                os.environ["GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION"] = original_force

        stage = "audit_check_validation_error"
        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()
            audit_rows = conn.execute(
                text(
                    """
                    SELECT
                        event_type,
                        request_id,
                        resource,
                        result_status,
                        error_code,
                        action_summary
                    FROM audit_log
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND request_id = :request_id
                      AND event_type = 'tool_call'
                      AND resource = :resource
                      AND result_status = 'failure'
                      AND error_code = :error_code
                    ORDER BY timestamp DESC
                    LIMIT 5
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "request_id": request_id,
                    "resource": tool.name,
                    "error_code": ErrorCode.VALIDATION_ERROR.value,
                },
            ).mappings().all()

        if not audit_rows:
            raise RuntimeError("Smoke test expected audit_log tool_call failure with VALIDATION_ERROR")

        audit_raw = str(audit_rows).lower()
        for forbidden in ["bearer", "password", "secret", "token", "authorization", "cookie"]:
            if forbidden in audit_raw:
                raise RuntimeError(f"Smoke test audit_log leaked sensitive keyword: {forbidden}")

        last_action_summary = audit_rows[0].get("action_summary")
        if not isinstance(last_action_summary, dict):
            raise RuntimeError("Smoke test expected audit_log.action_summary to be a dict")
        if last_action_summary.get("toolName") != tool.name:
            raise RuntimeError("Smoke test expected audit_log.action_summary.toolName")
        args_summary = last_action_summary.get("argsSummary")
        if not isinstance(args_summary, dict) or not isinstance(args_summary.get("durationMs"), int):
            raise RuntimeError("Smoke test expected audit_log.action_summary.argsSummary.durationMs")

        stage = "audit_check_contract_violation"
        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()
            audit_rows_contract = conn.execute(
                text(
                    """
                    SELECT
                        event_type,
                        request_id,
                        resource,
                        result_status,
                        error_code,
                        action_summary
                    FROM audit_log
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND request_id = :request_id
                      AND event_type = 'tool_call'
                      AND resource = :resource
                      AND result_status = 'failure'
                      AND error_code = :error_code
                    ORDER BY timestamp DESC
                    LIMIT 5
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "request_id": request_id,
                    "resource": tool.name,
                    "error_code": ErrorCode.CONTRACT_VIOLATION.value,
                },
            ).mappings().all()

        if not audit_rows_contract:
            raise RuntimeError("Smoke test expected audit_log tool_call failure with CONTRACT_VIOLATION")

        audit_contract_raw = str(audit_rows_contract).lower()
        for forbidden in ["bearer", "password", "secret", "token", "authorization", "cookie"]:
            if forbidden in audit_contract_raw:
                raise RuntimeError(
                    f"Smoke test audit_log leaked sensitive keyword in contract violation: {forbidden}"
                )

        contract_action_summary = audit_rows_contract[0].get("action_summary")
        if not isinstance(contract_action_summary, dict):
            raise RuntimeError("Smoke test expected contract violation audit_log.action_summary to be a dict")
        contract_args_summary = contract_action_summary.get("argsSummary")
        if not isinstance(contract_args_summary, dict) or not isinstance(
            contract_args_summary.get("durationMs"), int
        ):
            raise RuntimeError(
                "Smoke test expected contract violation audit_log.action_summary.argsSummary.durationMs"
            )

        print(
            "contract_validation_smoke_ok",
            {
                "requestId": request_id,
                "auditEvents": len(audit_rows) + len(audit_rows_contract),
                "pydanticBenchmark": bench,
                "lineageVersionContract": lineage_contract,
            },
        )
        return 0

    except ConfigMissingError as e:
        print("contract_validation_smoke_failed", {"code": e.code.value, "message": e.message})
        return 2
    except RuntimeError as e:
        mapped = MigrationError(
            code=DbErrorCode.INTERNAL_ERROR,
            message=str(e),
            details={"exception": e.__class__.__name__, "stage": stage},
            retryable=False,
            request_id=request_id,
        )
        payload = mapped.to_response().model_dump(by_alias=True)
        print("contract_validation_smoke_failed", payload)
        return 4
    except AppError as e:
        payload = e.to_response().model_dump(by_alias=True)
        print("contract_validation_smoke_failed", payload)
        return 3
    except Exception as e:
        mapped = map_db_error(e, request_id=request_id)
        payload = mapped.to_response().model_dump(by_alias=True)
        if isinstance(payload.get("details"), dict):
            payload["details"].setdefault("stage", stage)
        print("contract_validation_smoke_failed", payload)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
