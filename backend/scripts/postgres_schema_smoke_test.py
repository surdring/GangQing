"""Smoke test for Postgres schema validation.

This script performs end-to-end validation against a real Postgres database:
- Migration upgrade/downgrade/upgrade cycle
- Table existence
- Column existence
- Primary key constraints
- Unique constraints
- Foreign key constraints
- Check constraints
- Index existence and isolation field coverage
- Partitioned tables
- pgcrypto extension
- Append-only audit_log trigger

All tests run against real Postgres (no mock/skip allowed).
Configuration missing or connection failure must cause explicit error.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import json
from pathlib import Path

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
    UpstreamUnavailableError,
    map_db_error,
)
from gangqing_db.settings import load_settings

VERSION_TABLE = "gangqing_alembic_version"
EXPECTED_HEAD = "0004_fact_enums"

# =============================================================================
# Expected schema objects
# =============================================================================

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

EXPECTED_PRIMARY_KEYS = {
    ("dim_equipment", "pk_dim_equipment"),
    ("dim_material", "pk_dim_material"),
    ("metric_lineage", "pk_metric_lineage"),
    ("metric_lineage_scenario_mapping", "pk_metric_lineage_scenario_mapping"),
    ("fact_production_daily", "pk_fact_production_daily"),
    ("fact_energy_daily", "pk_fact_energy_daily"),
    ("fact_cost_daily", "pk_fact_cost_daily"),
    ("fact_maintenance_workorder", "pk_fact_maintenance_workorder"),
}

EXPECTED_UNIQUE_CONSTRAINTS = {
    ("dim_equipment", "uq_dim_equipment_scope_unified_equipment_id"),
    ("dim_material", "uq_dim_material_scope_unified_material_id"),
    ("metric_lineage", "uq_metric_lineage_scope_metric_version"),
    (
        "metric_lineage_scenario_mapping",
        "uq_ml_scn_map_scope_metric_scn_ver",
    ),
    ("fact_production_daily", "uq_fact_production_daily_scope_date_equipment"),
    ("fact_energy_daily", "uq_fact_energy_daily_scope_date_equipment_type"),
    ("fact_cost_daily", "uq_fact_cost_daily_scope_date_equipment_item_lineage"),
    ("fact_maintenance_workorder", "uq_fact_maintenance_workorder_scope_workorder_no"),
}

EXPECTED_FOREIGN_KEYS = {
    ("fact_production_daily", "fk_fact_production_daily_equipment_id"),
    ("fact_energy_daily", "fk_fact_energy_daily_equipment_id"),
    ("fact_cost_daily", "fk_fact_cost_daily_equipment_id"),
    ("fact_alarm_event", "fk_fact_alarm_event_equipment_id"),
    ("fact_maintenance_workorder", "fk_fact_maintenance_workorder_equipment_id"),
}

EXPECTED_CHECK_CONSTRAINTS = {
    ("metric_lineage", "ck_metric_lineage_lineage_version_semver"),
    ("fact_production_daily", "ck_fact_production_daily_quantity_nonneg"),
    ("fact_production_daily", "ck_fact_production_daily_time_range"),
    ("fact_energy_daily", "ck_fact_energy_daily_consumption_nonneg"),
    ("fact_energy_daily", "ck_fact_energy_daily_time_range"),
    ("fact_cost_daily", "ck_fact_cost_daily_amount_nonneg"),
    ("fact_cost_daily", "ck_fact_cost_daily_time_range"),
    ("fact_maintenance_workorder", "ck_fact_maintenance_workorder_closed_after_created"),
    ("fact_alarm_event", "ck_fact_alarm_event_severity_enum"),
    ("fact_maintenance_workorder", "ck_fact_maintenance_workorder_status_enum"),
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

TABLES_WITH_ISOLATION = EXPECTED_TABLES


# =============================================================================
# Helper functions
# =============================================================================


def _require_database_url() -> str:
    """Require database URL from environment. Fail with clear error if missing."""
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise ConfigMissingError("GANGQING_DATABASE_URL") from e
        raise map_db_error(e)
    return settings.database_url


def _build_alembic_config() -> Config:
    """Build Alembic config. Fail with clear error if config file missing."""
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    if not alembic_ini_path.exists():
        raise ConfigMissingError("backend/alembic.ini")

    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


def _get_current_version(engine) -> str | None:
    """Get current migration version from version table."""
    with engine.connect() as conn:
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

        result = conn.execute(text(f"SELECT version_num FROM {VERSION_TABLE} LIMIT 1"))
        row = result.fetchone()
        return row[0] if row else None


# =============================================================================
# Schema assertion functions
# =============================================================================


def _assert_tables_exist(conn) -> None:
    """Verify all expected tables exist."""
    tables = {
        row[0]
        for row in conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """
            )
        ).all()
    }
    missing = EXPECTED_TABLES - tables
    if missing:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing tables: {sorted(missing)}",
        )


def _assert_isolation_fields_exist(conn) -> None:
    """Verify tenant_id and project_id exist on all core tables."""
    for table in TABLES_WITH_ISOLATION:
        cols = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :table
                    """
                ),
                {"table": table},
            ).all()
        }
        if "tenant_id" not in cols:
            raise MigrationFailedError(
                "upgrade",
                cause=f"Table '{table}' missing isolation field 'tenant_id'",
            )
        if "project_id" not in cols:
            raise MigrationFailedError(
                "upgrade",
                cause=f"Table '{table}' missing isolation field 'project_id'",
            )


def _assert_primary_keys_exist(conn) -> None:
    """Verify primary key constraints exist."""
    pk_constraints = {
        (row[0], row[1])
        for row in conn.execute(
            text(
                """
                SELECT tc.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'PRIMARY KEY'
                """
            )
        ).all()
    }
    missing = EXPECTED_PRIMARY_KEYS - pk_constraints
    if missing:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing primary key constraints: {sorted(missing)}",
        )


def _assert_composite_primary_keys(conn) -> None:
    """Verify composite primary keys on partitioned tables."""
    # fact_alarm_event: primary key is (id, event_time)
    result = conn.execute(
        text(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_schema = 'public'
              AND tc.table_name = 'fact_alarm_event'
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """
        )
    ).all()
    pk_columns = {row[0] for row in result}
    if "id" not in pk_columns or "event_time" not in pk_columns:
        raise MigrationFailedError(
            "upgrade",
            cause="fact_alarm_event primary key should be (id, event_time)",
        )

    # audit_log: primary key is (id, timestamp)
    result = conn.execute(
        text(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_schema = 'public'
              AND tc.table_name = 'audit_log'
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """
        )
    ).all()
    pk_columns = {row[0] for row in result}
    if "id" not in pk_columns or "timestamp" not in pk_columns:
        raise MigrationFailedError(
            "upgrade",
            cause="audit_log primary key should be (id, timestamp)",
        )


def _assert_unique_constraints_exist(conn) -> None:
    """Verify unique constraints exist."""
    unique_constraints = {
        (row[0], row[1])
        for row in conn.execute(
            text(
                """
                SELECT tc.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'UNIQUE'
                """
            )
        ).all()
    }
    missing = EXPECTED_UNIQUE_CONSTRAINTS - unique_constraints
    if missing:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing unique constraints: {sorted(missing)}",
        )


def _assert_foreign_keys_exist(conn) -> None:
    """Verify foreign key constraints exist."""
    fk_constraints = {
        (row[0], row[1])
        for row in conn.execute(
            text(
                """
                SELECT tc.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'FOREIGN KEY'
                """
            )
        ).all()
    }
    missing = EXPECTED_FOREIGN_KEYS - fk_constraints
    if missing:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing foreign key constraints: {sorted(missing)}",
        )


def _assert_check_constraints_exist(conn) -> None:
    """Verify check constraints exist."""
    check_constraints = {
        (row[0], row[1])
        for row in conn.execute(
            text(
                """
                SELECT tc.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type = 'CHECK'
                """
            )
        ).all()
    }
    missing = EXPECTED_CHECK_CONSTRAINTS - check_constraints
    if missing:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing check constraints: {sorted(missing)}",
        )


def _assert_indexes_exist(conn) -> None:
    """Verify all expected indexes exist."""
    indexes = {
        row[0]
        for row in conn.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                """
            )
        ).all()
    }
    missing = EXPECTED_INDEXES - indexes
    if missing:
        raise MigrationFailedError(
            "upgrade",
            cause=f"Missing indexes: {sorted(missing)}",
        )


def _assert_indexes_cover_isolation(conn) -> None:
    """Verify all scope indexes include tenant_id and project_id."""
    result = conn.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname LIKE 'idx_%scope%'
            """
        )
    ).all()

    for index_name, index_def in result:
        if "tenant_id" not in index_def.lower():
            raise MigrationFailedError(
                "upgrade",
                cause=f"Index '{index_name}' does not include 'tenant_id' for isolation",
            )
        if "project_id" not in index_def.lower():
            raise MigrationFailedError(
                "upgrade",
                cause=f"Index '{index_name}' does not include 'project_id' for isolation",
            )


def _assert_partitioned_tables_exist(conn) -> None:
    """Verify partitioned tables have default partitions."""
    # Check fact_alarm_event partition
    result = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM pg_class c
                JOIN pg_inherits i ON c.oid = i.inhrelid
                JOIN pg_class p ON i.inhparent = p.oid
                WHERE p.relname = 'fact_alarm_event'
                  AND c.relname = 'fact_alarm_event_p0'
            )
            """
        )
    ).scalar_one()
    if not result:
        raise MigrationFailedError(
            "upgrade",
            cause="fact_alarm_event partition 'fact_alarm_event_p0' does not exist",
        )

    # Check audit_log partition
    result = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM pg_class c
                JOIN pg_inherits i ON c.oid = i.inhrelid
                JOIN pg_class p ON i.inhparent = p.oid
                WHERE p.relname = 'audit_log'
                  AND c.relname = 'audit_log_p0'
            )
            """
        )
    ).scalar_one()
    if not result:
        raise MigrationFailedError(
            "upgrade",
            cause="audit_log partition 'audit_log_p0' does not exist",
        )


def _assert_pgcrypto_extension(conn) -> None:
    """Verify pgcrypto extension is installed."""
    result = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM pg_extension
                WHERE extname = 'pgcrypto'
            )
            """
        )
    ).scalar_one()
    if not result:
        raise MigrationFailedError(
            "upgrade",
            cause="pgcrypto extension is not installed",
        )


def _assert_audit_log_append_only(conn) -> None:
    """Verify audit_log blocks UPDATE and DELETE operations."""
    try:
        insert_id = conn.execute(
            text(
                """
                INSERT INTO audit_log(
                    event_type, request_id, tenant_id, project_id, result_status
                ) VALUES (
                    'query', 'req-smoke', 't1', 'p1', 'success'
                )
                RETURNING id
                """
            )
        ).scalar_one()

        # UPDATE should be blocked (use SAVEPOINT so failure doesn't abort the transaction)
        nested = conn.begin_nested()
        try:
            conn.execute(
                text("UPDATE audit_log SET result_status='failure' WHERE id = :id"),
                {"id": insert_id},
            )
            nested.commit()
            raise MigrationFailedError(
                "validation",
                cause="audit_log UPDATE should be blocked by trigger or permissions but it succeeded",
            )
        except MigrationFailedError:
            raise
        except Exception:
            nested.rollback()

        # DELETE should be blocked
        nested = conn.begin_nested()
        try:
            conn.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": insert_id})
            nested.commit()
            raise MigrationFailedError(
                "validation",
                cause="audit_log DELETE should be blocked by trigger or permissions but it succeeded",
            )
        except MigrationFailedError:
            raise
        except Exception:
            nested.rollback()
    finally:
        # Rollback to remove inserted test row and end the implicit transaction.
        conn.rollback()


def _assert_schema_objects(database_url: str) -> None:
    """Run all schema assertions."""
    engine = create_engine(database_url, pool_pre_ping=True)

    with engine.connect() as conn:
        # Set RLS context for smoke test.
        conn.execute(text("SELECT set_config('app.current_tenant', 't1', true)"))
        conn.execute(text("SELECT set_config('app.current_project', 'p1', true)"))

        # End the implicit transaction opened by set_config() so that
        # downstream assertions can start explicit transactions safely.
        conn.commit()

        _assert_tables_exist(conn)
        _assert_isolation_fields_exist(conn)
        _assert_primary_keys_exist(conn)
        _assert_composite_primary_keys(conn)
        _assert_unique_constraints_exist(conn)
        _assert_foreign_keys_exist(conn)
        _assert_check_constraints_exist(conn)
        _assert_indexes_exist(conn)
        _assert_indexes_cover_isolation(conn)
        _assert_partitioned_tables_exist(conn)
        _assert_pgcrypto_extension(conn)
        _assert_audit_log_append_only(conn)


def main() -> int:
    try:
        request_id = f"schema-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        database_url = _require_database_url()
        cfg = _build_alembic_config()
        engine = create_engine(database_url, pool_pre_ping=True)

        # Test connection
        try:
            with engine.connect():
                pass
        except Exception as e:
            raise map_db_error(e, request_id=request_id)

        # upgrade -> downgrade -> upgrade
        command.upgrade(cfg, "head")
        version = _get_current_version(engine)
        if version != EXPECTED_HEAD:
            raise MigrationFailedError(
                "upgrade",
                version=version,
                cause=f"Expected version {EXPECTED_HEAD}, got {version}",
                request_id=request_id,
            )
        _assert_schema_objects(database_url)

        command.downgrade(cfg, "base")
        version = _get_current_version(engine)
        if version is not None:
            raise MigrationFailedError(
                "downgrade",
                version=version,
                cause=f"Expected no version (base), got {version}",
                request_id=request_id,
            )

        command.upgrade(cfg, "head")
        version = _get_current_version(engine)
        if version != EXPECTED_HEAD:
            raise MigrationFailedError(
                "upgrade",
                version=version,
                cause=f"Expected version {EXPECTED_HEAD}, got {version}",
                request_id=request_id,
            )
        _assert_schema_objects(database_url)

        print("postgres_schema_smoke_test: PASS")
        return 0

    except ConfigMissingError as e:
        error_response = e.to_response()
        details = (
            f" details={json.dumps(error_response.details, ensure_ascii=False, sort_keys=True)}"
            if error_response.details
            else ""
        )
        print(f"Error [{error_response.code}]: {error_response.message}{details}", file=sys.stderr)
        return 1

    except UpstreamUnavailableError as e:
        error_response = e.to_response()
        details = (
            f" details={json.dumps(error_response.details, ensure_ascii=False, sort_keys=True)}"
            if error_response.details
            else ""
        )
        print(f"Error [{error_response.code}]: {error_response.message}{details}", file=sys.stderr)
        return 1

    except MigrationFailedError as e:
        error_response = e.to_response()
        details = (
            f" details={json.dumps(error_response.details, ensure_ascii=False, sort_keys=True)}"
            if error_response.details
            else ""
        )
        print(f"Error [{error_response.code}]: {error_response.message}{details}", file=sys.stderr)
        return 1

    except Exception as e:
        mapped = map_db_error(e, request_id=request_id if 'request_id' in locals() else None)
        error_response = mapped.to_response()
        details = (
            f" details={json.dumps(error_response.details, ensure_ascii=False, sort_keys=True)}"
            if error_response.details
            else ""
        )
        print(f"Error [{error_response.code}]: {error_response.message}{details}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
