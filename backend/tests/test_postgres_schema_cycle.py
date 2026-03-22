"""Integration unit test for Postgres schema migration cycle.

This test connects to a real Postgres and verifies:
- Alembic upgrade -> downgrade -> upgrade completes
- Head version matches expected
- Core tables exist after upgrade

Configuration is required. Missing config must fail (no skip).
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing_db.errors import ConfigMissingError, MigrationFailedError
from gangqing_db.settings import load_settings

_VERSION_TABLE = "gangqing_alembic_version"
_EXPECTED_HEAD = "0008_audit_idx"
_EXPECTED_TABLES = {
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
    "draft",
    "evidence_store",
}


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
        exists = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": _VERSION_TABLE},
        ).scalar_one()
        if not exists:
            return None
        row = conn.execute(text(f"SELECT version_num FROM {_VERSION_TABLE} LIMIT 1")).fetchone()
        return row[0] if row else None


def _get_tables(engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """
            )
        ).all()
        return {r[0] for r in rows}


def test_alembic_schema_upgrade_downgrade_upgrade_cycle() -> None:
    try:
        settings = load_settings()
    except Exception as e:
        raise ConfigMissingError("GANGQING_DATABASE_URL") from e

    cfg = _build_alembic_config()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    command.upgrade(cfg, "head")
    version = _get_current_version(engine)
    if version != _EXPECTED_HEAD:
        raise MigrationFailedError(
            "upgrade",
            version=version,
            cause=f"Expected version {_EXPECTED_HEAD}, got {version}",
        )

    tables = _get_tables(engine)
    missing = _EXPECTED_TABLES - tables
    if missing:
        raise MigrationFailedError("upgrade", cause=f"Missing tables: {sorted(missing)}")

    command.downgrade(cfg, "base")
    version = _get_current_version(engine)
    if version is not None:
        raise MigrationFailedError(
            "downgrade",
            version=version,
            cause=f"Expected no version (base), got {version}",
        )

    command.upgrade(cfg, "head")
    version = _get_current_version(engine)
    if version != _EXPECTED_HEAD:
        raise MigrationFailedError(
            "upgrade",
            version=version,
            cause=f"Expected version {_EXPECTED_HEAD}, got {version}",
        )
