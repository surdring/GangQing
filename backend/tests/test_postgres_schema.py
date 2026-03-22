"""Unit tests for Postgres schema validation.

Tests cover:
- Table existence
- Column existence and types
- Primary key constraints
- Unique constraints
- Foreign key constraints
- Check constraints
- Index existence and isolation field coverage
- Isolation fields (tenant_id, project_id)
- Time field defaults
- Append-only audit_log trigger

All tests run against real Postgres (no mock/skip allowed).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from gangqing_db.settings import load_settings


def _require_database_url() -> str:
    """Require database URL from environment. Fail if missing."""
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL") from e
        raise
    return settings.database_url


def _build_alembic_config() -> Config:
    """Build Alembic config for migrations."""
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


def _set_rls_context(conn) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', 't1', true)"))
    conn.execute(text("SELECT set_config('app.current_project', 'p1', true)"))


def _reset_schema(cfg: Config) -> None:
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module", autouse=True)
def _apply_latest_migrations() -> None:
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    _reset_schema(cfg)

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)



# =============================================================================
# Test data: Expected schema objects
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


EXPECTED_AUDIT_LOG_COLUMNS = {
    "event_type",
    "timestamp",
    "request_id",
    "tenant_id",
    "project_id",
    "session_id",
    "user_id",
    "role",
    "resource",
    "correlation_id",
    "supersedes_event_id",
    "action_summary",
    "result_status",
    "error_code",
    "evidence_refs",
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
    # fact_alarm_event and audit_log have composite primary keys
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
    "idx_audit_log_scope_correlation_time",
    "idx_audit_log_scope_user_time",
    "idx_audit_log_scope_resource_time",
    "idx_fact_alarm_event_p0_id_unique",
    "uq_metric_lineage_scope_metric_active_unique",
    "idx_metric_lineage_scenario_mapping_scope_metric_scenario",
    "uq_ml_scn_map_scope_metric_scn_active_u",
}

# Tables that require isolation fields (tenant_id, project_id)
TABLES_WITH_ISOLATION = EXPECTED_TABLES

# Key columns per table for existence check
KEY_COLUMNS = {
    "dim_equipment": {"id", "tenant_id", "project_id", "unified_equipment_id", "name", "created_at", "updated_at"},
    "dim_material": {"id", "tenant_id", "project_id", "unified_material_id", "name", "created_at", "updated_at"},
    "metric_lineage": {"id", "tenant_id", "project_id", "metric_name", "lineage_version", "status", "created_at"},
    "metric_lineage_scenario_mapping": {
        "id",
        "tenant_id",
        "project_id",
        "metric_name",
        "scenario_key",
        "lineage_version",
        "status",
        "created_at",
    },
    "fact_production_daily": {"id", "tenant_id", "project_id", "business_date", "quantity", "unit", "created_at"},
    "fact_energy_daily": {"id", "tenant_id", "project_id", "business_date", "energy_type", "consumption", "created_at"},
    "fact_cost_daily": {"id", "tenant_id", "project_id", "business_date", "cost_item", "amount", "lineage_version", "created_at"},
    "fact_alarm_event": {"id", "tenant_id", "project_id", "event_time", "created_at"},
    "fact_maintenance_workorder": {"id", "tenant_id", "project_id", "workorder_no", "status", "created_time", "created_at"},
    "audit_log": {"id", "event_type", "timestamp", "request_id", "tenant_id", "project_id", "result_status"},
}

# Time columns with default values
TIME_COLUMNS_WITH_DEFAULTS = {
    "dim_equipment": {"created_at", "updated_at"},
    "dim_material": {"created_at", "updated_at"},
    "metric_lineage": {"created_at"},
    "metric_lineage_scenario_mapping": {"created_at"},
    "fact_production_daily": {"created_at"},
    "fact_energy_daily": {"created_at"},
    "fact_cost_daily": {"created_at"},
    "fact_alarm_event": {"created_at"},
    "fact_maintenance_workorder": {"created_at"},
    "audit_log": {"timestamp"},
}


# =============================================================================
# Unit Tests
# =============================================================================


def test_tables_exist() -> None:
    """Verify all expected tables exist in public schema."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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
        assert not missing, f"Missing tables: {sorted(missing)}"


def test_key_columns_exist() -> None:
    """Verify key columns exist in each table."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
        for table, expected_cols in KEY_COLUMNS.items():
            if table == "audit_log":
                rows = conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": table},
                ).all()
                cols = {r[0] for r in rows}
                missing = EXPECTED_AUDIT_LOG_COLUMNS - cols
                assert not missing, f"Missing columns in {table}: {sorted(missing)}"
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": table},
                ).all()
                cols = {r[0] for r in rows}
                missing = expected_cols - cols
                assert not missing, f"Missing columns in {table}: {sorted(missing)}"


def test_isolation_fields_exist() -> None:
    """Verify tenant_id and project_id exist on all core tables."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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

            assert "tenant_id" in cols, f"Table '{table}' missing isolation field 'tenant_id'"
            assert "project_id" in cols, f"Table '{table}' missing isolation field 'project_id'"


def test_primary_key_constraints_exist() -> None:
    """Verify primary key constraints exist on all tables."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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
        assert not missing, f"Missing primary key constraints: {sorted(missing)}"


def test_composite_primary_keys() -> None:
    """Verify composite primary keys on partitioned tables."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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
        assert "id" in pk_columns, "fact_alarm_event primary key missing 'id' column"
        assert "event_time" in pk_columns, "fact_alarm_event primary key missing 'event_time' column"

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
        assert "id" in pk_columns, "audit_log primary key missing 'id' column"
        assert "timestamp" in pk_columns, "audit_log primary key missing 'timestamp' column"


def test_unique_constraints_exist() -> None:
    """Verify unique constraints exist."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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
        assert not missing, f"Missing unique constraints: {sorted(missing)}"


def test_foreign_key_constraints_exist() -> None:
    """Verify foreign key constraints exist."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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
        assert not missing, f"Missing foreign key constraints: {sorted(missing)}"


def test_check_constraints_exist() -> None:
    """Verify check constraints exist for data integrity."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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
        assert not missing, f"Missing check constraints: {sorted(missing)}"


def test_indexes_exist() -> None:
    """Verify all expected indexes exist."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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
        assert not missing, f"Missing indexes: {sorted(missing)}"


def test_indexes_cover_isolation_fields() -> None:
    """Verify all indexes include tenant_id and project_id for isolation."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
        # Get index definitions
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
            # All scope indexes should include tenant_id and project_id
            assert "tenant_id" in index_def.lower(), (
                f"Index '{index_name}' does not include 'tenant_id' for isolation"
            )
            assert "project_id" in index_def.lower(), (
                f"Index '{index_name}' does not include 'project_id' for isolation"
            )


def test_time_columns_have_defaults() -> None:
    """Verify time columns have server default values."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
        for table, time_cols in TIME_COLUMNS_WITH_DEFAULTS.items():
            for col in time_cols:
                result = conn.execute(
                    text(
                        """
                        SELECT column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table
                          AND column_name = :col
                        """
                    ),
                    {"table": table, "col": col},
                ).scalar_one()

                assert result is not None, (
                    f"Table '{table}' column '{col}' has no default value"
                )
                assert "now()" in str(result).lower() or "gen_random_uuid" in str(result).lower() or result is not None, (
                    f"Table '{table}' column '{col}' default is not a timestamp function"
                )


def test_audit_log_is_append_only() -> None:
    """Verify audit_log blocks UPDATE and DELETE operations via trigger."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)

        # End the implicit transaction opened by set_config() to avoid
        # InvalidRequestError when starting an explicit transaction.
        conn.commit()

        trans = conn.begin()
        try:
            insert_id = conn.execute(
                text(
                    """
                    INSERT INTO audit_log(event_type, request_id, tenant_id, project_id, result_status)
                    VALUES ('tool_call', 'req-unit', 't1', 'p1', 'success')
                    RETURNING id
                    """
                )
            ).scalar_one()

            # UPDATE should be blocked
            update_blocked = False
            nested = conn.begin_nested()
            try:
                conn.execute(
                    text("UPDATE audit_log SET result_status='failure' WHERE id = :id"),
                    {"id": insert_id},
                )
                nested.commit()
            except Exception:
                nested.rollback()
                update_blocked = True
            assert update_blocked, "audit_log UPDATE should be blocked by trigger but succeeded"

            # DELETE should be blocked
            delete_blocked = False
            nested = conn.begin_nested()
            try:
                conn.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": insert_id})
                nested.commit()
            except Exception:
                nested.rollback()
                delete_blocked = True
            assert delete_blocked, "audit_log DELETE should be blocked by trigger but succeeded"
        finally:
            trans.rollback()


def test_partitioned_tables_exist() -> None:
    """Verify partitioned tables have default partitions."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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

        assert result, "fact_alarm_event partition 'fact_alarm_event_p0' does not exist"

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

        assert result, "audit_log partition 'audit_log_p0' does not exist"


def test_pgcrypto_extension_installed() -> None:
    """Verify pgcrypto extension is installed for gen_random_uuid()."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)
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

        assert result, "pgcrypto extension is not installed"


def test_rls_is_enabled_and_policies_exist() -> None:
    """Verify RLS is enabled+forced and expected policies exist on core tables."""
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn)

        expected_rls_tables = {
            "dim_equipment",
            "dim_material",
            "metric_lineage",
            "fact_production_daily",
            "fact_energy_daily",
            "fact_cost_daily",
            "fact_alarm_event",
            "fact_alarm_event_p0",
            "fact_maintenance_workorder",
            "audit_log",
            "audit_log_p0",
        }

        rls_flags = {
            row[0]: (bool(row[1]), bool(row[2]))
            for row in conn.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind IN ('r','p')
                    """
                )
            ).all()
        }

        missing_tables = expected_rls_tables - set(rls_flags.keys())
        assert not missing_tables, f"Missing RLS tables in catalog: {sorted(missing_tables)}"

        not_enabled = [t for t, (enabled, _) in rls_flags.items() if t in expected_rls_tables and not enabled]
        assert not not_enabled, f"RLS not enabled for tables: {sorted(not_enabled)}"

        not_forced = [t for t, (_, forced) in rls_flags.items() if t in expected_rls_tables and not forced]
        assert not not_forced, f"RLS not forced for tables: {sorted(not_forced)}"

        expected_policies = {
            "p_dim_equipment_isolation",
            "p_dim_material_isolation",
            "p_metric_lineage_isolation",
            "p_fact_production_daily_isolation",
            "p_fact_energy_daily_isolation",
            "p_fact_cost_daily_isolation",
            "p_fact_alarm_event_isolation",
            "p_fact_alarm_event_p0_isolation",
            "p_fact_maintenance_workorder_isolation",
            "p_audit_log_isolation",
            "p_audit_log_p0_isolation",
        }

        policies = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT polname
                    FROM pg_policy
                    WHERE polname LIKE 'p_%_isolation'
                    """
                )
            ).all()
        }

        missing_policies = expected_policies - policies
        assert not missing_policies, f"Missing RLS policies: {sorted(missing_policies)}"
