"""Integration tests for seed_data edge/exception dataset.

These tests MUST hit a real Postgres:
- Missing DB config => test fails
- DB unreachable => test fails

Assertions:
- Each edge category generates at least 1 row and can be located by table + primary key.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from unittest import mock

# Add backend and scripts to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
for _p in (str(_BACKEND_DIR), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gangqing_db.errors import ConfigMissingError, MigrationError, map_db_error
from gangqing_db.settings import load_settings

import seed_data


def _build_alembic_config() -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


@pytest.fixture(scope="module", autouse=True)
def _reset_schema_to_head() -> None:
    database_url = _require_database_url()
    _require_db_connection(database_url)
    cfg = _build_alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def _require_database_url() -> str:
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise ConfigMissingError("GANGQING_DATABASE_URL") from e
        raise
    return settings.database_url


def _require_db_connection(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        mapped = map_db_error(e)
        raise MigrationError(
            code=mapped.code,
            message="Postgres connection failed",
            details=mapped.details,
            retryable=True,
        ) from e


def _build_edge_case_params() -> seed_data.SeedConfig:
    return seed_data.SeedConfig(
        seed=2026,
        tenant_id=os.getenv("GANGQING_TENANT_ID") or "t1",
        project_id=os.getenv("GANGQING_PROJECT_ID") or "p1",
        start_date=date(2026, 2, 1),
        days=4,
        equipment_count=3,
        materials_count=2,
        events_per_day=2,
        workorders_count=2,
        edge_cases=seed_data.SeedEdgeCasesConfig(
            dataset_version="pytest-edge",
            missing_enabled=True,
            delay_enabled=True,
            duplicate_enabled=True,
            extreme_enabled=True,
            missing_count=1,
            delay_count=1,
            duplicate_count=2,
            extreme_count=1,
        ),
    )


def test_seed_edge_cases_evidence_must_exist_and_be_queryable() -> None:
    database_url = _require_database_url()
    _require_db_connection(database_url)

    params = _build_edge_case_params()

    result = seed_data.seed_database(database_url=database_url, params=params)
    assert "inserted" in result
    assert "edge_evidence" in result

    evidence = result["edge_evidence"]
    assert isinstance(evidence, list)

    # At least one evidence item per edge type.
    edge_types = {e["edge_type"] for e in evidence}
    assert "missing" in edge_types
    assert "delay" in edge_types
    assert "duplicate" in edge_types
    assert "extreme" in edge_types

    # Evidence-first: table + primary_key must resolve.
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
        conn.commit()

        for item in evidence:
            table = item["table"]
            pk = item["primary_key"]
            exists = conn.execute(
                text(f"SELECT 1 FROM {table} WHERE id::text = :id LIMIT 1"),
                {"id": pk},
            ).scalar()
            assert exists == 1


def test_seed_edge_case_missing_production_must_have_null_equipment_id() -> None:
    database_url = _require_database_url()
    _require_db_connection(database_url)

    params = _build_edge_case_params()
    seed_data.seed_database(database_url=database_url, params=params)

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
        conn.commit()

        missing_count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fact_production_daily
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND source_record_id LIKE :prefix
                  AND equipment_id IS NULL
                """
            ),
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "prefix": f"{params.edge_cases.dataset_version}:edge:missing:%",
            },
        ).scalar_one()

    assert missing_count >= 1


def test_seed_edge_case_delay_production_must_have_extracted_at_gt_time_end() -> None:
    database_url = _require_database_url()
    _require_db_connection(database_url)

    params = _build_edge_case_params()
    seed_data.seed_database(database_url=database_url, params=params)

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
        conn.commit()

        delayed_rows = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fact_production_daily
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND source_record_id LIKE :prefix
                  AND extracted_at > time_end
                """
            ),
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "prefix": f"{params.edge_cases.dataset_version}:edge:delay:%",
            },
        ).scalar_one()

    assert delayed_rows >= 1


def test_seed_edge_case_delay_alarm_must_have_created_at_gt_event_time() -> None:
    database_url = _require_database_url()
    _require_db_connection(database_url)

    params = _build_edge_case_params()
    seed_data.seed_database(database_url=database_url, params=params)

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
        conn.commit()

        delayed_rows = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fact_alarm_event
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND source_record_id LIKE :prefix
                  AND created_at > event_time
                """
            ),
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "prefix": f"{params.edge_cases.dataset_version}:edge:delay:alarm:%",
            },
        ).scalar_one()

    assert delayed_rows >= 1


def test_seed_edge_case_extreme_samples_must_exist() -> None:
    database_url = _require_database_url()
    _require_db_connection(database_url)

    params = _build_edge_case_params()
    seed_data.seed_database(database_url=database_url, params=params)

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
        conn.commit()

        extreme_prod = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fact_production_daily
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND source_record_id LIKE :prefix
                """
            ),
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "prefix": f"{params.edge_cases.dataset_version}:edge:extreme:prod:%",
            },
        ).scalar_one()

        extreme_energy = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fact_energy_daily
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND source_record_id LIKE :prefix
                """
            ),
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "prefix": f"{params.edge_cases.dataset_version}:edge:extreme:energy:%",
            },
        ).scalar_one()

    assert extreme_prod >= 1
    assert extreme_energy >= 1


def test_seed_edge_case_duplicate_alarm_samples_must_have_at_least_two_rows() -> None:
    database_url = _require_database_url()
    _require_db_connection(database_url)

    params = _build_edge_case_params()
    seed_data.seed_database(database_url=database_url, params=params)

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
        conn.commit()

        dup_alarm = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fact_alarm_event
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND source_record_id LIKE :prefix
                """
            ),
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "prefix": f"{params.edge_cases.dataset_version}:edge:duplicate:alarm:%",
            },
        ).scalar_one()

    assert dup_alarm >= 1


def test_seed_edge_cases_missing_config_must_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("gangqing_db.settings._load_dotenv_file", return_value=None):
            with pytest.raises(ConfigMissingError) as exc_info:
                _require_database_url()

    assert exc_info.value.code.value == "CONFIG_MISSING"
    assert "GANGQING_DATABASE_URL" in exc_info.value.message
