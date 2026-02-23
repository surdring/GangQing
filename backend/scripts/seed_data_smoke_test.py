"""Smoke test for seed data generation.

This script writes seed data into a real Postgres database and validates:
- Required config exists
- Connection works
- Rows are inserted and queryable under RLS context

Usage:
    export GANGQING_DATABASE_URL='postgresql+psycopg://user:pass@host:5432/db'
    python backend/scripts/seed_data_smoke_test.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

# Add backend to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from gangqing_db.errors import ErrorCode, ConfigMissingError, MigrationError, map_db_error
from gangqing_db.settings import load_settings

import seed_data


def _env_int(name: str, *, default: int, request_id: str) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except Exception as e:
        raise MigrationError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid integer env var",
            details={"env_var": name, "value": value},
            retryable=False,
            request_id=request_id,
        ) from e


def _env_str(name: str, *, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value is not None and value.strip() else default


def _parse_date(value: str, *, request_id: str) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except Exception as e:
        raise MigrationError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid date format, expected YYYY-MM-DD",
            details={"value": value},
            retryable=False,
            request_id=request_id,
        ) from e


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--run-id", dest="run_id", default=None)
    parser.add_argument("--seed", dest="seed", type=int, default=None)
    parser.add_argument("--dataset-version", dest="dataset_version", default=None)
    parser.add_argument("--tenant-id", dest="tenant_id", default=None)
    parser.add_argument("--project-id", dest="project_id", default=None)
    parser.add_argument("--start-date", dest="start_date", default=None)
    parser.add_argument("--days", dest="days", type=int, default=None)
    parser.add_argument("--equipment-count", dest="equipment_count", type=int, default=None)
    parser.add_argument("--materials-count", dest="materials_count", type=int, default=None)
    parser.add_argument("--events-per-day", dest="events_per_day", type=int, default=None)
    parser.add_argument("--workorders-count", dest="workorders_count", type=int, default=None)
    return parser


def _get_run_id(args: argparse.Namespace) -> str:
    run_id = args.run_id or os.getenv("GANGQING_RUN_ID")
    if run_id and run_id.strip():
        return run_id.strip()
    return f"seed-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"


def _require_database_url(*, request_id: str) -> str:
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise ConfigMissingError("GANGQING_DATABASE_URL", request_id=request_id) from e
        raise MigrationError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid configuration: GANGQING_DATABASE_URL",
            details={"cause": str(e)},
            retryable=False,
            request_id=request_id,
        ) from e
    return settings.database_url


def _log(*, run_id: str, status: str, details: dict | None = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "script": "seed_data_smoke_test",
        "status": status,
        "run_id": run_id,
    }
    if details:
        entry["details"] = details
    print(json.dumps(entry), file=sys.stderr)


def main() -> int:
    try:
        args = _build_parser().parse_args()
        run_id = _get_run_id(args)
        database_url = _require_database_url(request_id=run_id)

        dataset_version = (
            args.dataset_version
            or os.getenv("GANGQING_SEED_DATASET_VERSION")
            or "smoke"
        )
        params = seed_data.SeedConfig(
            seed=(
                args.seed
                if args.seed is not None
                else _env_int("GANGQING_SEED", default=123, request_id=run_id)
            ),
            tenant_id=(args.tenant_id or _env_str("GANGQING_TENANT_ID", default="t1")),
            project_id=(args.project_id or _env_str("GANGQING_PROJECT_ID", default="p1")),
            start_date=(
                _parse_date(args.start_date, request_id=run_id)
                if args.start_date
                else _parse_date(
                    _env_str(
                        "GANGQING_SEED_START_DATE",
                        default=datetime.now(timezone.utc).date().isoformat(),
                    ),
                    request_id=run_id,
                )
            ),
            days=(
                args.days
                if args.days is not None
                else _env_int("GANGQING_SEED_DAYS", default=3, request_id=run_id)
            ),
            equipment_count=(
                args.equipment_count
                if args.equipment_count is not None
                else _env_int("GANGQING_SEED_EQUIPMENT_COUNT", default=2, request_id=run_id)
            ),
            materials_count=(
                args.materials_count
                if args.materials_count is not None
                else _env_int("GANGQING_SEED_MATERIALS_COUNT", default=2, request_id=run_id)
            ),
            events_per_day=(
                args.events_per_day
                if args.events_per_day is not None
                else _env_int("GANGQING_SEED_EVENTS_PER_DAY", default=2, request_id=run_id)
            ),
            workorders_count=(
                args.workorders_count
                if args.workorders_count is not None
                else _env_int("GANGQING_SEED_WORKORDERS_COUNT", default=3, request_id=run_id)
            ),
            edge_cases=seed_data.SeedEdgeCasesConfig(
                dataset_version=dataset_version,
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

        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise map_db_error(e, request_id=run_id)

        _log(
            run_id=run_id,
            status="started",
            details={
                "seed": params.seed,
                "dataset_version": params.edge_cases.dataset_version,
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
            },
        )
        result = seed_data.seed_database(database_url=database_url, params=params)

        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
            conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
            conn.commit()

            equipment_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM dim_equipment
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                    """
                ),
                {"tenant_id": params.tenant_id, "project_id": params.project_id},
            ).scalar_one()

            edge_prefix = f"{params.edge_cases.dataset_version}:edge:%"
            missing_prod = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM fact_production_daily
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND source_record_id LIKE :prefix
                      AND source_record_id LIKE :missing
                    """
                ),
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "prefix": edge_prefix,
                    "missing": f"{params.edge_cases.dataset_version}:edge:missing:%",
                },
            ).scalar_one()
            delay_prod = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM fact_production_daily
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND source_record_id LIKE :delay
                    """
                ),
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "delay": f"{params.edge_cases.dataset_version}:edge:delay:%",
                },
            ).scalar_one()
            extreme_energy = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM fact_energy_daily
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND source_record_id LIKE :extreme
                    """
                ),
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "extreme": f"{params.edge_cases.dataset_version}:edge:extreme:%",
                },
            ).scalar_one()
            dup_alarm = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM fact_alarm_event
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND source_record_id LIKE :dup
                    """
                ),
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "dup": f"{params.edge_cases.dataset_version}:edge:duplicate:%",
                },
            ).scalar_one()

        if equipment_count <= 0:
            raise MigrationError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Seed verification failed",
                details={
                    "equipment_count": equipment_count,
                    "missing_prod": missing_prod,
                    "delay_prod": delay_prod,
                    "extreme_energy": extreme_energy,
                    "dup_alarm": dup_alarm,
                },
                retryable=False,
            )

        if missing_prod <= 0 or delay_prod <= 0 or extreme_energy <= 0 or dup_alarm <= 0:
            raise MigrationError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Seed edge-case verification failed",
                details={
                    "missing_prod": missing_prod,
                    "delay_prod": delay_prod,
                    "extreme_energy": extreme_energy,
                    "dup_alarm": dup_alarm,
                },
                retryable=False,
                request_id=run_id,
            )

        _log(
            run_id=run_id,
            status="completed",
            details={
                "result": result,
                "equipment_count": equipment_count,
                "missing_prod": missing_prod,
                "delay_prod": delay_prod,
                "extreme_energy": extreme_energy,
                "dup_alarm": dup_alarm,
            },
        )
        print("seed_data_smoke_test: PASS")
        return 0

    except (ConfigMissingError, MigrationError) as e:
        error = e.to_response()
        effective_run_id = error.request_id or os.getenv("GANGQING_RUN_ID") or "unknown"
        _log(run_id=effective_run_id, status="failed", details={"error": error.model_dump()})
        print(
            f"Error [{error.code}]: {error.message} request_id={effective_run_id}",
            file=sys.stderr,
        )
        return 1

    except Exception as e:
        effective_run_id = os.getenv("GANGQING_RUN_ID") or "unknown"
        mapped = map_db_error(e, request_id=effective_run_id)
        error = mapped.to_response()
        _log(run_id=effective_run_id, status="failed", details={"error": error.model_dump()})
        print(
            f"Error [{error.code}]: {error.message} request_id={effective_run_id}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
