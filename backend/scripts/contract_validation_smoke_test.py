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
from sqlalchemy import create_engine, text

# Add backend to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.tools.postgres_readonly import PostgresReadOnlyQueryParams, PostgresReadOnlyQueryTool
from gangqing_db.errors import ConfigMissingError, MigrationFailedError, map_db_error
from gangqing_db.settings import load_settings


EXPECTED_HEAD = "0003_ml_scn_map"


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


def main() -> int:
    request_id = f"contract-validation-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    try:
        database_url = _require_database_url()
        _require_any_env({"GANGQING_LLAMACPP_BASE_URL", "GANGQING_PROVIDER_HEALTHCHECK_URL"})
        cfg = _build_alembic_config()

        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect():
                pass
        except Exception as e:
            raise map_db_error(e, request_id=request_id)

        command.upgrade(cfg, "head")
        version = _get_current_version(engine)
        if version != EXPECTED_HEAD:
            raise MigrationFailedError(
                "upgrade",
                version=version,
                cause=f"Expected version {EXPECTED_HEAD}, got {version}",
                request_id=request_id,
            )

        tenant_id = "t_smoke"
        project_id = "p_smoke"

        host = (os.environ.get("GANGQING_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"
        port_raw = (os.environ.get("GANGQING_API_PORT") or "8000").strip()
        try:
            port = int(port_raw)
        except ValueError:
            port = 8000

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
            health_url = f"http://{host}:{port}/api/v1/health"
            status, body = _http_get_json(
                url=health_url,
                headers={
                    "X-Tenant-Id": tenant_id,
                    "X-Project-Id": project_id,
                    "X-Request-Id": request_id,
                },
                timeout_seconds=15.0,
            )
            if status != 200:
                raise RuntimeError(f"Healthcheck failed: status={status}, body={body}")
            if body.get("requestId") != request_id:
                raise RuntimeError(
                    f"Healthcheck requestId mismatch: expected={request_id}, got={body.get('requestId')}"
                )
            deps = body.get("dependencies")
            if not isinstance(deps, list):
                raise RuntimeError("Healthcheck dependencies must be a list")
            dep_by_name = {
                str(d.get("name")): d
                for d in deps
                if isinstance(d, dict) and str(d.get("name") or "").strip()
            }
            for required in {"config", "postgres", "llama_cpp", "provider", "model"}:
                if required not in dep_by_name:
                    raise RuntimeError(f"Healthcheck missing dependency item: {required}")
            if str(dep_by_name["postgres"].get("status")) != "ok":
                raise RuntimeError(f"Healthcheck expected postgres ok, got: {dep_by_name['postgres']}")
            if str(dep_by_name["model"].get("status")) != "ok":
                raise RuntimeError(f"Healthcheck expected model ok, got: {dep_by_name['model']}")

            fail_status, fail_body = _http_get_json(
                url=health_url,
                headers={
                    "X-Project-Id": project_id,
                    "X-Request-Id": request_id,
                },
                timeout_seconds=10.0,
            )
            if fail_status != 401:
                raise RuntimeError(f"Smoke expected 401 for missing X-Tenant-Id, got: {fail_status}, body={fail_body}")
            for key in ["code", "message", "details", "retryable", "requestId"]:
                if key not in fail_body:
                    raise RuntimeError(f"401 ErrorResponse missing key: {key}")
        finally:
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
            tool.run(
                ctx=ctx,
                params=PostgresReadOnlyQueryParams(
                    templateId="production_daily",
                    timeRange={
                        "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                        "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                    },
                    limit=10,
                    offset=0,
                ),
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
                        error_code
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

        print(
            "contract_validation_smoke_ok",
            {
                "requestId": request_id,
                "auditEvents": len(audit_rows) + len(audit_rows_contract),
            },
        )
        return 0

    except ConfigMissingError as e:
        print("contract_validation_smoke_failed", {"code": e.code.value, "message": e.message})
        return 2
    except AppError as e:
        payload = e.to_response().model_dump(by_alias=True)
        print("contract_validation_smoke_failed", payload)
        return 3
    except Exception as e:
        mapped = map_db_error(e, request_id=request_id)
        payload = mapped.to_response().model_dump(by_alias=True)
        print("contract_validation_smoke_failed", payload)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
