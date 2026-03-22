"""Smoke test for tool timeout & retryable mapping.

This script validates end-to-end behavior against a real Postgres:
- Requires GANGQING_DATABASE_URL
- Applies migrations to head
- Seeds minimal fact rows for a scoped tenant/project
- Runs postgres_readonly_query tool with a forced-slow template and a very small timeout
- Expects structured AppError mapping to UPSTREAM_TIMEOUT with retryable=true

No mock/skip allowed.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

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

EXPECTED_HEAD = "0004_fact_enums"


def _require_database_url() -> str:
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise ConfigMissingError("GANGQING_DATABASE_URL") from e
        raise map_db_error(e)
    return settings.database_url


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


def _seed(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(
        text(
            """
            DELETE FROM fact_production_daily
            WHERE tenant_id = :tenant_id AND project_id = :project_id
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id},
    )

    conn.execute(
        text(
            """
            INSERT INTO fact_production_daily(
                tenant_id, project_id, business_date, equipment_id, quantity, unit,
                source_system, source_record_id, time_start, time_end, extracted_at
            ) VALUES (
                :tenant_id, :project_id, :business_date, NULL, :quantity, :unit,
                :source_system, :source_record_id, :time_start, :time_end, :extracted_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "business_date": datetime(2026, 2, 1).date(),
            "quantity": 123.456,
            "unit": "kg",
            "source_system": "smoke",
            "source_record_id": "r1",
            "time_start": datetime(2026, 2, 1, tzinfo=timezone.utc),
            "time_end": datetime(2026, 2, 2, tzinfo=timezone.utc),
            "extracted_at": datetime.now(timezone.utc),
        },
    )


def main() -> int:
    request_id = f"tool-timeout-retry-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    try:
        database_url = _require_database_url()
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

        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()
            _seed(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()

        ctx = RequestContext(
            requestId=request_id,
            tenantId=tenant_id,
            projectId=project_id,
            role="plant_manager",
            stepId="smoke.timeout",
        )

        tool = PostgresReadOnlyQueryTool()

        os.environ["GANGQING_TOOL_MAX_RETRIES"] = "1"
        os.environ["GANGQING_TOOL_BACKOFF_BASE_MS"] = "0"
        os.environ["GANGQING_TOOL_BACKOFF_MAX_MS"] = "0"
        os.environ["GANGQING_TOOL_BACKOFF_JITTER_RATIO"] = "0"

        try:
            tool.run_raw(
                ctx=ctx,
                raw_params={
                    "templateId": "production_daily_slow",
                    "timeRange": {
                        "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                        "end": datetime(2026, 2, 2,  tzinfo=timezone.utc),
                    },
                    "timeoutSeconds": 0.05,
                    "limit": 1,
                    "offset": 0,
                },
            )
        except AppError as e:
            if e.code != ErrorCode.UPSTREAM_TIMEOUT or e.retryable is not True:
                payload = e.to_response().model_dump(by_alias=True)
                print(
                    "tool_timeout_retry_smoke_failed",
                    {
                        "message": "Unexpected tool error mapping",
                        "expectedCode": ErrorCode.UPSTREAM_TIMEOUT.value,
                        "expectedRetryable": True,
                        "actual": payload,
                    },
                )
                return 5
        else:
            print(
                "tool_timeout_retry_smoke_failed",
                {
                    "message": "Expected slow query to timeout",
                    "expectedCode": ErrorCode.UPSTREAM_TIMEOUT.value,
                },
            )
            return 6

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
                        error_code
                    FROM audit_log
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND request_id = :request_id
                      AND event_type = 'tool_call'
                      AND resource = :resource
                    ORDER BY timestamp DESC
                    LIMIT 5
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "request_id": request_id,
                    "resource": tool.name,
                },
            ).mappings().all()

        if not audit_rows:
            raise RuntimeError("Smoke test expected audit_log tool_call event")

        if len(audit_rows) < 2:
            raise RuntimeError("Smoke test expected at least 2 tool_call audit rows for retry")

        last_error_code = str(audit_rows[0].get("error_code") or "")
        if last_error_code != ErrorCode.UPSTREAM_TIMEOUT.value:
            raise RuntimeError(
                f"Smoke test expected audit_log.error_code={ErrorCode.UPSTREAM_TIMEOUT.value}, got {last_error_code}"
            )

        print(
            "tool_timeout_retry_smoke_ok",
            {
                "requestId": request_id,
                "toolName": tool.name,
                "errorCode": ErrorCode.UPSTREAM_TIMEOUT.value,
            },
        )
        return 0

    except ConfigMissingError as e:
        print("tool_timeout_retry_smoke_failed", {"code": e.code.value, "message": e.message})
        return 2
    except AppError as e:
        payload = e.to_response().model_dump(by_alias=True)
        print("tool_timeout_retry_smoke_failed", payload)
        return 3
    except Exception as e:
        mapped = map_db_error(e, request_id=request_id)
        payload = mapped.to_response().model_dump(by_alias=True)
        print("tool_timeout_retry_smoke_failed", payload)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
