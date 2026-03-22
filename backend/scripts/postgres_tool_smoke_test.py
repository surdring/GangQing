"""Smoke test for Postgres read-only query tool.

This script validates end-to-end behavior against a real Postgres:
- Requires GANGQING_DATABASE_URL
- Applies migrations to head
- Seeds minimal fact rows for a scoped tenant/project
- Runs postgres_readonly_query tool and validates Evidence/audit binding

No mock/skip allowed.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

# Add backend to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError
from gangqing.tools.postgres_readonly import PostgresReadOnlyQueryTool
from gangqing_db.errors import ConfigMissingError, MigrationFailedError, map_db_error
from gangqing_db.settings import load_settings



def _get_expected_heads(cfg: Config) -> list[str]:
    script = ScriptDirectory.from_config(cfg)
    return sorted({str(x) for x in script.get_heads() if str(x).strip()})


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


def _verify_read_only_transaction_gate(engine, *, tenant_id: str, project_id: str) -> None:
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()

        try:
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))
                value = conn.execute(text("SHOW transaction_read_only")).scalar_one()
                if str(value).strip().lower() not in {"on", "true"}:
                    raise RuntimeError("Expected transaction_read_only to be on")

                conn.execute(text("CREATE TEMP TABLE __gangqing_ro_probe(x int)"))
        except Exception:
            return

        raise RuntimeError("Expected write/DDL to be rejected in READ ONLY transaction")


def _verify_statement_timeout_gate(engine, *, tenant_id: str, project_id: str) -> None:
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()

        try:
            with conn.begin():
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(text("SELECT set_config('statement_timeout', :v, true)"), {"v": "200ms"})
                conn.execute(text("SELECT pg_sleep(1)"))
        except Exception:
            return

        raise RuntimeError("Expected statement_timeout to cancel slow query")


def _warn_if_db_user_has_write_privileges(engine, *, tenant_id: str, project_id: str) -> None:
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()

        row = conn.execute(
            text(
                """
                SELECT
                    current_user AS user,
                    has_table_privilege(current_user, 'fact_production_daily', 'INSERT') AS can_insert,
                    has_table_privilege(current_user, 'fact_production_daily', 'UPDATE') AS can_update,
                    has_table_privilege(current_user, 'fact_production_daily', 'DELETE') AS can_delete
                """
            )
        ).mappings().one()

        if bool(row.get("can_insert")) or bool(row.get("can_update")) or bool(row.get("can_delete")):
            print(
                "postgres_tool_smoke_warning",
                {
                    "message": "Database user appears to have write privileges. Recommended to use a read-only role.",
                    "user": row.get("user"),
                    "canInsert": bool(row.get("can_insert")),
                    "canUpdate": bool(row.get("can_update")),
                    "canDelete": bool(row.get("can_delete")),
                },
            )


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
    request_id = f"postgres-tool-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

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
        expected_heads = _get_expected_heads(cfg)
        if version is None or version not in expected_heads:
            raise MigrationFailedError(
                "upgrade",
                version=version,
                cause=f"Expected version in {expected_heads}, got {version}",
                request_id=request_id,
            )

        tenant_id = "t_smoke"
        project_id = "p_smoke"

        _verify_read_only_transaction_gate(engine, tenant_id=tenant_id, project_id=project_id)
        _verify_statement_timeout_gate(engine, tenant_id=tenant_id, project_id=project_id)
        _warn_if_db_user_has_write_privileges(engine, tenant_id=tenant_id, project_id=project_id)

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
        )

        tool = PostgresReadOnlyQueryTool()

        try:
            tool.run_raw(
                ctx=ctx,
                raw_params={
                    "templateId": "__unknown__",
                    "timeRange": {
                        "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                        "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                    },
                },
            )
        except AppError as e:
            if e.code.value != "VALIDATION_ERROR":
                raise RuntimeError("Smoke test expected VALIDATION_ERROR for invalid templateId")
        else:
            raise RuntimeError("Smoke test expected invalid templateId to fail")

        result = tool.run_raw(
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

        assert result.evidence.evidence_id
        assert result.evidence.source_system == "Postgres"
        assert result.evidence.source_locator.get("queryFingerprint")
        assert result.evidence.source_locator.get("tableOrView") == "fact_production_daily"
        assert result.evidence.source_locator.get("extractedAt")

        if result.row_count < 1:
            raise RuntimeError("Smoke test expected at least 1 row")

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
                        evidence_refs
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

        evidence_ref_lists = [r.get("evidence_refs") for r in audit_rows]
        flattened: list[str] = []
        for refs in evidence_ref_lists:
            if refs is None:
                continue
            if isinstance(refs, list):
                flattened.extend([str(x) for x in refs])
            else:
                flattened.append(str(refs))

        if result.evidence.evidence_id not in flattened:
            raise RuntimeError("Smoke test expected evidenceId in audit_log evidence_refs")

        print(
            "postgres_tool_smoke_ok",
            {
                "requestId": request_id,
                "rowCount": result.row_count,
                "evidenceId": result.evidence.evidence_id,
            },
        )
        return 0

    except ConfigMissingError as e:
        print("postgres_tool_smoke_failed", {"code": e.code.value, "message": e.message})
        return 2
    except AppError as e:
        payload = e.to_response().model_dump(by_alias=True)
        print("postgres_tool_smoke_failed", payload)
        return 3
    except Exception as e:
        mapped = map_db_error(e, request_id=request_id)
        payload = mapped.to_response().model_dump(by_alias=True)
        print("postgres_tool_smoke_failed", payload)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
