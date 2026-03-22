"""Migration rollback verification smoke test.

This script verifies the upgrade -> downgrade -> upgrade cycle on a real Postgres.
It asserts:
1. Version table changes correctly
2. All tables/indexes exist after upgrade
3. Tables/indexes are dropped after downgrade
4. Audit log append-only constraint works

Usage:
    export GANGQING_DATABASE_URL="postgresql+psycopg://user:pass@host:5432/db"
    python backend/scripts/postgres_migration_rollback_smoke_test.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

# Add backend to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing_db.errors import (
    ConfigMissingError,
    MigrationFailedError,
    RollbackVerificationError,
    UpstreamUnavailableError,
    map_db_error,
)
from gangqing_db.settings import load_settings

VERSION_TABLE = "gangqing_alembic_version"
EXPECTED_HEAD = "0004_fact_enums"

EXPECTED_TABLES = {
    "dim_equipment",
    "dim_material",
    "metric_lineage",
    "metric_lineage_scenario_mapping",
    "fact_production_daily",
    "fact_energy_daily",
    "fact_cost_daily",
    "fact_alarm_event",
    "fact_maintenance_workorder",
    "audit_log",
}

EXPECTED_INDEXES = {
    "idx_dim_equipment_scope_unified_id",
    "idx_dim_material_scope_unified_id",
    "idx_fact_production_daily_scope_date_equipment",
    "idx_fact_energy_daily_scope_date_equipment_type",
    "idx_fact_cost_daily_scope_date_equipment_lineage",
    "idx_fact_cost_daily_scope_date_cost_item",
    "idx_fact_alarm_event_scope_time",
    "idx_fact_alarm_event_scope_equipment_time",
    "idx_fact_maintenance_workorder_scope_workorder_no",
    "idx_fact_maintenance_workorder_scope_equipment_created",
    "idx_audit_log_scope_request_time",
    "idx_audit_log_scope_time",
    "idx_audit_log_scope_event_type_time",
    "idx_fact_alarm_event_p0_id_unique",
    "idx_audit_log_p0_id_unique",
    "uq_metric_lineage_scope_metric_active_unique",
    "idx_metric_lineage_scenario_mapping_scope_metric_scenario",
    "uq_ml_scn_map_scope_metric_scn_active_u",
}


def _require_database_url() -> str:
    """Get database URL from environment, fail if missing."""
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise ConfigMissingError("GANGQING_DATABASE_URL") from e
        raise UpstreamUnavailableError("Postgres", cause=str(e))
    return settings.database_url


def _build_alembic_config() -> Config:
    """Build Alembic config from repository structure."""
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    if not alembic_ini_path.exists():
        raise ConfigMissingError("backend/alembic.ini")

    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


def _get_current_version(engine: Any) -> str | None:
    """Get current migration version from version table."""
    with engine.connect() as conn:
        # Check if version table exists
        result = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = :table_name
                )
                """
            ),
            {"table_name": VERSION_TABLE},
        )
        if not result.scalar_one():
            return None

        # Get version
        result = conn.execute(
            text(f"SELECT version_num FROM {VERSION_TABLE} LIMIT 1")
        )
        row = result.fetchone()
        return row[0] if row else None


def _get_tables(engine: Any) -> set[str]:
    """Get all tables in public schema."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
        )
        return {row[0] for row in result.fetchall()}


def _get_indexes(engine: Any) -> set[str]:
    """Get all indexes in public schema."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                """
            )
        )
        return {row[0] for row in result.fetchall()}


def _assert_schema_objects(engine: Any) -> None:
    """Assert all expected tables and indexes exist."""
    tables = _get_tables(engine)
    missing_tables = EXPECTED_TABLES - tables
    if missing_tables:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing tables: {sorted(missing_tables)}",
        )

    indexes = _get_indexes(engine)
    missing_indexes = EXPECTED_INDEXES - indexes
    if missing_indexes:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing indexes: {sorted(missing_indexes)}",
        )


def _assert_audit_log_append_only(engine: Any) -> None:
    """Assert audit_log is append-only (UPDATE/DELETE blocked)."""
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', 't1', true)"))
        conn.execute(text("SELECT set_config('app.current_project', 'p1', true)"))
        conn.commit()

        insert_id = conn.execute(
            text(
                """
                INSERT INTO audit_log(
                    event_type, request_id, tenant_id, project_id, result_status
                ) VALUES (
                    'query', 'req-rollback-test', 't1', 'p1', 'success'
                )
                RETURNING id
                """
            )
        ).scalar_one()

        nested = conn.begin_nested()
        try:
            conn.execute(
                text("UPDATE audit_log SET result_status='failure' WHERE id = :id"),
                {"id": insert_id},
            )
            nested.commit()
            raise MigrationFailedError(
                "validation",
                cause="audit_log UPDATE should be blocked but it succeeded",
            )
        except MigrationFailedError:
            raise
        except Exception:
            nested.rollback()

        nested = conn.begin_nested()
        try:
            conn.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": insert_id})
            nested.commit()
            raise MigrationFailedError(
                "validation",
                cause="audit_log DELETE should be blocked but it succeeded",
            )
        except MigrationFailedError:
            raise
        except Exception:
            nested.rollback()
        finally:
            conn.rollback()


def _log_result(status: str, details: dict[str, Any] | None = None) -> None:
    """Log structured result as JSON."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "postgres_migration_rollback_smoke_test",
        "status": status,
    }
    if details:
        log_entry["details"] = details
    print(json.dumps(log_entry), file=sys.stderr)


def main() -> int:
    """Run rollback verification: upgrade -> downgrade -> upgrade."""
    request_id = f"rollback-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    try:
        database_url = _require_database_url()
        cfg = _build_alembic_config()
        engine = create_engine(database_url, pool_pre_ping=True)

        # Test connection
        try:
            with engine.connect():
                pass
        except Exception as e:
            raise UpstreamUnavailableError(
                "Postgres",
                cause=str(e),
                request_id=request_id,
            )

        _log_result("started", {"request_id": request_id})

        # Step 1: Upgrade to head
        _log_result("step", {"step": "upgrade_to_head", "phase": "start"})
        command.upgrade(cfg, "head")
        version_after_upgrade = _get_current_version(engine)
        if version_after_upgrade != EXPECTED_HEAD:
            raise RollbackVerificationError(
                expected_version=EXPECTED_HEAD,
                actual_version=version_after_upgrade,
                request_id=request_id,
            )
        _log_result("step", {
            "step": "upgrade_to_head",
            "phase": "complete",
            "version": version_after_upgrade,
        })

        # Verify schema after first upgrade
        _assert_schema_objects(engine)
        _assert_audit_log_append_only(engine)
        _log_result("step", {"step": "schema_verification", "phase": "passed"})

        # Step 2: Downgrade to base
        _log_result("step", {"step": "downgrade_to_base", "phase": "start"})
        command.downgrade(cfg, "base")
        version_after_downgrade = _get_current_version(engine)
        if version_after_downgrade is not None:
            raise RollbackVerificationError(
                expected_version="None (base)",
                actual_version=version_after_downgrade,
                request_id=request_id,
            )
        _log_result("step", {
            "step": "downgrade_to_base",
            "phase": "complete",
            "version": version_after_downgrade,
        })

        # Verify tables are dropped
        tables_after_downgrade = _get_tables(engine)
        remaining_tables = EXPECTED_TABLES & tables_after_downgrade
        if remaining_tables:
            raise MigrationFailedError(
                "downgrade",
                cause=f"Tables not dropped: {sorted(remaining_tables)}",
                request_id=request_id,
            )
        _log_result("step", {"step": "tables_dropped_verification", "phase": "passed"})

        # Step 3: Upgrade again (re-run)
        _log_result("step", {"step": "upgrade_again", "phase": "start"})
        command.upgrade(cfg, "head")
        version_after_rerun = _get_current_version(engine)
        if version_after_rerun != EXPECTED_HEAD:
            raise RollbackVerificationError(
                expected_version=EXPECTED_HEAD,
                actual_version=version_after_rerun,
                request_id=request_id,
            )
        _log_result("step", {
            "step": "upgrade_again",
            "phase": "complete",
            "version": version_after_rerun,
        })

        # Verify schema after second upgrade
        _assert_schema_objects(engine)
        _assert_audit_log_append_only(engine)

        _log_result("completed", {
            "request_id": request_id,
            "result": "PASS",
            "cycle": "upgrade -> downgrade -> upgrade",
        })
        print("postgres_migration_rollback_smoke_test: PASS")
        return 0

    except ConfigMissingError as e:
        error_response = e.to_response()
        _log_result("failed", {"error": error_response.model_dump()})
        print(f"Error: {error_response.message}", file=sys.stderr)
        return 1

    except UpstreamUnavailableError as e:
        error_response = e.to_response()
        _log_result("failed", {"error": error_response.model_dump()})
        print(f"Error: {error_response.message}", file=sys.stderr)
        return 1

    except (MigrationFailedError, RollbackVerificationError) as e:
        error_response = e.to_response()
        _log_result("failed", {"error": error_response.model_dump()})
        print(f"Error: {error_response.message}", file=sys.stderr)
        return 1

    except Exception as e:
        mapped = map_db_error(e, request_id=request_id)
        error_response = mapped.to_response()
        _log_result("failed", {"error": error_response.model_dump()})
        print(f"Error: {error_response.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
