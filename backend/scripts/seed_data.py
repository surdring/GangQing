"""Seed minimal GangQing dataset into a real Postgres database.

This script is designed for reproducible data generation:
- Same seed + same parameters => identical generated payload
- Writes into real Postgres (no mock)
- Fail-fast on missing configuration

Usage:
    export GANGQING_DATABASE_URL='postgresql+psycopg://user:pass@host:5432/db'
    python backend/scripts/seed_data.py --seed 42 --days 14 --equipment-count 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from random import Random
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

# Add backend to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from gangqing_db.errors import (
    ConfigMissingError,
    ContractViolationError,
    MigrationError,
    UpstreamUnavailableError,
    ValidationError,
    map_db_error,
)
from gangqing_db.settings import load_settings


_EXTREME_PRODUCTION_QTY = Decimal("1000000")
_EXTREME_ENERGY_CONSUMPTION = Decimal("999999")
_DELAY_PRODUCTION_EXTRACTED_AT_HOURS = 36
_DELAY_ALARM_CREATED_AT_HOURS = 48
_PROGRESS_LOG_EVERY_ROWS = 100


class SeedEdgeCasesConfig(BaseModel):
    dataset_version: str = Field(min_length=1, max_length=64)
    missing_enabled: bool = True
    delay_enabled: bool = True
    duplicate_enabled: bool = True
    extreme_enabled: bool = True
    missing_count: int = Field(default=1, ge=1, le=50)
    delay_count: int = Field(default=1, ge=1, le=50)
    duplicate_count: int = Field(default=2, ge=2, le=50)
    extreme_count: int = Field(default=1, ge=1, le=50)


class SeedConfig(BaseModel):
    seed: int
    tenant_id: str
    project_id: str
    start_date: date
    days: int = Field(ge=1)
    equipment_count: int = Field(ge=1)
    materials_count: int = Field(ge=1)
    events_per_day: int = Field(ge=0)
    workorders_count: int = Field(ge=0)
    edge_cases: SeedEdgeCasesConfig


@dataclass(frozen=True)
class EdgeEvidenceRef:
    edge_type: str
    table: str
    primary_key: str
    time_range: dict[str, str | None]
    business_date: str | None = None


def _require_database_url() -> str:
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise ConfigMissingError("GANGQING_DATABASE_URL") from e
        raise ValidationError(
            "Invalid configuration: GANGQING_DATABASE_URL",
            details={"cause": str(e)},
        ) from e
    return settings.database_url


def _env_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except Exception as e:  # pragma: no cover
        raise ValidationError(f"Invalid integer for {name}", details={"value": value}) from e


def _env_str(name: str, *, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value.strip() else default


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    v = value.strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValidationError("Invalid boolean for env var", details={"env_var": name, "value": value})


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except Exception as e:
        raise ValidationError("Invalid date format, expected YYYY-MM-DD", details={"value": value}) from e


def _build_params(args: argparse.Namespace) -> SeedConfig:
    seed = args.seed if args.seed is not None else _env_int("GANGQING_SEED", default=42)

    tenant_id = args.tenant_id or _env_str("GANGQING_TENANT_ID", default="t1")
    project_id = args.project_id or _env_str("GANGQING_PROJECT_ID", default="p1")

    start_date = (
        _parse_date(args.start_date)
        if args.start_date
        else _parse_date(_env_str("GANGQING_SEED_START_DATE", default="2026-02-01"))
    )

    days = args.days if args.days is not None else _env_int("GANGQING_SEED_DAYS", default=14)
    equipment_count = (
        args.equipment_count
        if args.equipment_count is not None
        else _env_int("GANGQING_SEED_EQUIPMENT_COUNT", default=3)
    )
    materials_count = (
        args.materials_count
        if args.materials_count is not None
        else _env_int("GANGQING_SEED_MATERIALS_COUNT", default=3)
    )
    events_per_day = (
        args.events_per_day
        if args.events_per_day is not None
        else _env_int("GANGQING_SEED_EVENTS_PER_DAY", default=2)
    )
    workorders_count = (
        args.workorders_count
        if args.workorders_count is not None
        else _env_int("GANGQING_SEED_WORKORDERS_COUNT", default=5)
    )

    dataset_version = args.dataset_version or _env_str(
        "GANGQING_SEED_DATASET_VERSION", default="v1"
    )

    edge_cases = SeedEdgeCasesConfig(
        dataset_version=dataset_version,
        missing_enabled=(
            args.edge_missing_enabled
            if args.edge_missing_enabled is not None
            else _env_bool("GANGQING_SEED_EDGE_MISSING_ENABLED", default=True)
        ),
        delay_enabled=(
            args.edge_delay_enabled
            if args.edge_delay_enabled is not None
            else _env_bool("GANGQING_SEED_EDGE_DELAY_ENABLED", default=True)
        ),
        duplicate_enabled=(
            args.edge_duplicate_enabled
            if args.edge_duplicate_enabled is not None
            else _env_bool("GANGQING_SEED_EDGE_DUPLICATE_ENABLED", default=True)
        ),
        extreme_enabled=(
            args.edge_extreme_enabled
            if args.edge_extreme_enabled is not None
            else _env_bool("GANGQING_SEED_EDGE_EXTREME_ENABLED", default=True)
        ),
        missing_count=(
            args.edge_missing_count
            if args.edge_missing_count is not None
            else _env_int("GANGQING_SEED_EDGE_MISSING_COUNT", default=1)
        ),
        delay_count=(
            args.edge_delay_count
            if args.edge_delay_count is not None
            else _env_int("GANGQING_SEED_EDGE_DELAY_COUNT", default=1)
        ),
        duplicate_count=(
            args.edge_duplicate_count
            if args.edge_duplicate_count is not None
            else _env_int("GANGQING_SEED_EDGE_DUPLICATE_COUNT", default=2)
        ),
        extreme_count=(
            args.edge_extreme_count
            if args.edge_extreme_count is not None
            else _env_int("GANGQING_SEED_EDGE_EXTREME_COUNT", default=1)
        ),
    )

    try:
        return SeedConfig(
            seed=seed,
            tenant_id=tenant_id,
            project_id=project_id,
            start_date=start_date,
            days=days,
            equipment_count=equipment_count,
            materials_count=materials_count,
            events_per_day=events_per_day,
            workorders_count=workorders_count,
            edge_cases=edge_cases,
        )
    except Exception as e:
        cause = str(e)
        if len(cause) > 500:
            cause = cause[:500] + "..."
        raise ValidationError(
            "Seed config validation failed",
            details={"cause": cause},
        ) from e


def generate_seed_payload(params: SeedConfig) -> dict[str, list[dict[str, Any]]]:
    """Generate deterministic payload for seed insertion.

    This function is pure (no DB access) and intended for unit tests to assert reproducibility.
    """

    rng = Random(params.seed)
    dataset_version = params.edge_cases.dataset_version

    idx_extreme_day = 0
    idx_missing_day = 0 if params.days == 1 else 1
    idx_delay_day = 0 if params.days == 1 else min(2, params.days - 1)
    idx_duplicate_day = 0 if params.days == 1 else min(3, params.days - 1)

    missing_eq_indices = (
        set(range(min(params.edge_cases.missing_count, params.equipment_count)))
        if params.edge_cases.missing_enabled
        else set()
    )
    delay_eq_indices = (
        set(range(min(params.edge_cases.delay_count, params.equipment_count)))
        if params.edge_cases.delay_enabled
        else set()
    )
    extreme_eq_indices = (
        set(range(min(params.edge_cases.extreme_count, params.equipment_count)))
        if params.edge_cases.extreme_enabled
        else set()
    )
    duplicate_alarm_extra = (
        max(params.edge_cases.duplicate_count - 1, 0) if params.edge_cases.duplicate_enabled else 0
    )

    equipment_rows: list[dict[str, Any]] = []
    for i in range(params.equipment_count):
        equipment_rows.append(
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "unified_equipment_id": f"EQ-{i+1:03d}",
                "name": f"Equipment {i+1}",
                "line_id": f"L{(i % 2) + 1}",
                "area": f"A{(i % 3) + 1}",
                "source_system": "seed",
                "source_record_id": f"{dataset_version}:seed-eq-{i+1}",
            }
        )

    material_rows: list[dict[str, Any]] = []
    for i in range(params.materials_count):
        material_rows.append(
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "unified_material_id": f"MAT-{i+1:03d}",
                "name": f"Material {i+1}",
                "category": "seed",
                "source_system": "seed",
                "source_record_id": f"{dataset_version}:seed-mat-{i+1}",
            }
        )

    lineage_versions = ["1.0.0", "2.0.0"]
    metric_lineage_rows = [
        {
            "tenant_id": params.tenant_id,
            "project_id": params.project_id,
            "metric_name": "oee",
            "lineage_version": "1.0.0",
            "formula": "(good_time / planned_time)",
            "source_systems": ["MES"],
            "owner": "seed",
            "source_record_id": f"{dataset_version}:seed-metric-oee-v1",
        },
        {
            "tenant_id": params.tenant_id,
            "project_id": params.project_id,
            "metric_name": "energy_kwh",
            "lineage_version": "1.0.0",
            "formula": "sum(kwh)",
            "source_systems": ["DCS"],
            "owner": "seed",
            "source_record_id": f"{dataset_version}:seed-metric-energy_kwh-v1",
        },
        {
            "tenant_id": params.tenant_id,
            "project_id": params.project_id,
            "metric_name": "unit_cost",
            "lineage_version": "2.0.0",
            "formula": "cost / quantity",
            "source_systems": ["ERP"],
            "owner": "seed",
            "source_record_id": f"{dataset_version}:seed-metric-unit_cost-v2",
        },
    ]

    production_rows: list[dict[str, Any]] = []
    energy_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    alarm_rows: list[dict[str, Any]] = []
    workorder_rows: list[dict[str, Any]] = []

    for day_offset in range(params.days):
        business_date = params.start_date + timedelta(days=day_offset)
        day_start = datetime.combine(business_date, datetime.min.time(), tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        for eq_index in range(params.equipment_count):
            unified_equipment_id = f"EQ-{eq_index+1:03d}"

            # Production: include extreme fluctuation sample
            base_qty = Decimal("100") + Decimal(str(rng.randint(0, 20)))
            if day_offset == idx_extreme_day and eq_index in extreme_eq_indices:
                quantity = _EXTREME_PRODUCTION_QTY
            else:
                quantity = base_qty

            # Missing sample: equipment_id will be NULL (represented via unified_equipment_id=None)
            missing_equipment = day_offset == idx_missing_day and eq_index in missing_eq_indices

            # Delay sample: extracted_at later than time_end
            extracted_at = (
                day_end + timedelta(hours=_DELAY_PRODUCTION_EXTRACTED_AT_HOURS)
                if (day_offset == idx_delay_day and eq_index in delay_eq_indices)
                else day_end
            )

            prod_src_id = f"{dataset_version}:seed-prod-{business_date.isoformat()}-{unified_equipment_id}"
            if missing_equipment:
                prod_src_id = f"{dataset_version}:edge:missing:prod:{business_date.isoformat()}:{eq_index}"
            if extracted_at != day_end:
                prod_src_id = f"{dataset_version}:edge:delay:prod:{business_date.isoformat()}:{eq_index}"
            if quantity == _EXTREME_PRODUCTION_QTY:
                prod_src_id = f"{dataset_version}:edge:extreme:prod:{business_date.isoformat()}:{eq_index}"

            production_rows.append(
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "business_date": business_date.isoformat(),
                    "unified_equipment_id": None if missing_equipment else unified_equipment_id,
                    "quantity": str(quantity),
                    "unit": "kg",
                    "source_system": "seed",
                    "source_record_id": prod_src_id,
                    "time_start": day_start.isoformat(),
                    "time_end": day_end.isoformat(),
                    "extracted_at": extracted_at.isoformat(),
                }
            )

            # Energy: include duplicate sample via source_record_id (not DB-unique)
            for energy_type in ("electricity", "steam"):
                consumption = Decimal("50") + Decimal(str(rng.randint(0, 15)))
                if day_offset == idx_extreme_day and eq_index in extreme_eq_indices and energy_type == "electricity":
                    consumption = _EXTREME_ENERGY_CONSUMPTION

                src_id = f"{dataset_version}:seed-energy-{business_date.isoformat()}-{unified_equipment_id}-{energy_type}"
                if consumption == _EXTREME_ENERGY_CONSUMPTION:
                    src_id = f"{dataset_version}:edge:extreme:energy:{business_date.isoformat()}:{eq_index}:{energy_type}"

                energy_rows.append(
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "business_date": business_date.isoformat(),
                        "unified_equipment_id": unified_equipment_id,
                        "energy_type": energy_type,
                        "consumption": str(consumption),
                        "unit": "kwh" if energy_type == "electricity" else "kg",
                        "source_system": "seed",
                        "source_record_id": src_id,
                        "time_start": day_start.isoformat(),
                        "time_end": day_end.isoformat(),
                        "extracted_at": day_end.isoformat(),
                    }
                )

            # Cost: bind to lineage versions
            for cost_item in ("material", "energy"):
                lineage_version = lineage_versions[(day_offset + eq_index) % len(lineage_versions)]
                amount = Decimal("1000") + Decimal(str(rng.randint(0, 200)))
                cost_rows.append(
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "business_date": business_date.isoformat(),
                        "unified_equipment_id": unified_equipment_id,
                        "cost_item": cost_item,
                        "amount": str(amount),
                        "currency": "CNY",
                        "lineage_version": lineage_version,
                        "source_system": "seed",
                        "source_record_id": f"{dataset_version}:seed-cost-{business_date.isoformat()}-{unified_equipment_id}-{cost_item}-{lineage_version}",
                        "time_start": day_start.isoformat(),
                        "time_end": day_end.isoformat(),
                        "extracted_at": day_end.isoformat(),
                    }
                )

            # Alarm events: include out-of-order (delayed ingestion) via created_at
            for j in range(params.events_per_day):
                event_time = day_start + timedelta(hours=2 * j + rng.randint(0, 1))
                created_at = (
                    event_time + timedelta(hours=_DELAY_ALARM_CREATED_AT_HOURS)
                    if (day_offset == idx_delay_day and j == 0 and eq_index in delay_eq_indices)
                    else event_time
                )

                alarm_src_id = f"{dataset_version}:seed-alarm-{business_date.isoformat()}-{unified_equipment_id}-{j}"
                if created_at != event_time:
                    alarm_src_id = f"{dataset_version}:edge:delay:alarm:{business_date.isoformat()}:{eq_index}:{j}"
                alarm_rows.append(
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "event_time": event_time.isoformat(),
                        "unified_equipment_id": unified_equipment_id,
                        "alarm_code": f"AL-{rng.randint(1, 5):03d}",
                        "severity": rng.choice(["low", "medium", "high"]),
                        "message": "seed alarm",
                        "source_system": "seed",
                        "source_record_id": alarm_src_id,
                        "created_at": created_at.isoformat(),
                    }
                )

                if day_offset == idx_duplicate_day and j == 0 and eq_index == 0 and duplicate_alarm_extra > 0:
                    for k in range(duplicate_alarm_extra):
                        alarm_rows.append(
                            {
                                "tenant_id": params.tenant_id,
                                "project_id": params.project_id,
                                "event_time": event_time.isoformat(),
                                "unified_equipment_id": unified_equipment_id,
                                "alarm_code": f"AL-{rng.randint(1, 5):03d}",
                                "severity": rng.choice(["low", "medium", "high"]),
                                "message": "seed alarm duplicate",
                                "source_system": "seed",
                                "source_record_id": f"{dataset_version}:edge:duplicate:alarm:{business_date.isoformat()}:{eq_index}:{j}:{k}",
                                "created_at": event_time.isoformat(),
                            }
                        )

    # Workorders (some closed, some open)
    base_time = datetime.combine(params.start_date, datetime.min.time(), tzinfo=timezone.utc)
    for i in range(params.workorders_count):
        created_time = base_time + timedelta(days=rng.randint(0, max(params.days - 1, 0)), hours=rng.randint(0, 23))
        closed = rng.choice([True, False])
        closed_time = created_time + timedelta(hours=rng.randint(1, 72)) if closed else None
        eq_index = rng.randint(0, params.equipment_count - 1)
        unified_equipment_id = f"EQ-{eq_index+1:03d}"
        workorder_rows.append(
            {
                "tenant_id": params.tenant_id,
                "project_id": params.project_id,
                "workorder_no": f"WO-{i+1:05d}",
                "unified_equipment_id": unified_equipment_id,
                "status": "closed" if closed else "open",
                "created_time": created_time.isoformat(),
                "closed_time": closed_time.isoformat() if closed_time else None,
                "fault_code": f"F-{rng.randint(1, 10):03d}",
                "fault_desc": "seed fault",
                "source_system": "seed",
                "source_record_id": f"{dataset_version}:seed-wo-{i+1}",
            }
        )

    return {
        "dim_equipment": equipment_rows,
        "dim_material": material_rows,
        "metric_lineage": metric_lineage_rows,
        "fact_production_daily": production_rows,
        "fact_energy_daily": energy_rows,
        "fact_cost_daily": cost_rows,
        "fact_alarm_event": alarm_rows,
        "fact_maintenance_workorder": workorder_rows,
    }


def _fetch_equipment_id_map(conn, tenant_id: str, project_id: str) -> dict[str, str]:
    result = conn.execute(
        text(
            """
            SELECT unified_equipment_id, id::text
            FROM dim_equipment
            WHERE tenant_id = :tenant_id AND project_id = :project_id
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id},
    ).all()
    return {row[0]: row[1] for row in result}


def seed_database(*, database_url: str, params: SeedConfig, cleanup_before_insert: bool = True) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": params.tenant_id})
            conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": params.project_id})
            conn.commit()

            payload = generate_seed_payload(params)

            if cleanup_before_insert:
                prefix = f"{params.edge_cases.dataset_version}:"
                conn.execute(
                    text(
                        """
                        DELETE FROM fact_alarm_event
                        WHERE tenant_id = :tenant_id AND project_id = :project_id
                          AND source_record_id LIKE :prefix
                        """
                    ),
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "prefix": prefix + "%",
                    },
                )
                conn.execute(
                    text(
                        """
                        DELETE FROM fact_cost_daily
                        WHERE tenant_id = :tenant_id AND project_id = :project_id
                          AND source_record_id LIKE :prefix
                        """
                    ),
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "prefix": prefix + "%",
                    },
                )
                conn.execute(
                    text(
                        """
                        DELETE FROM fact_energy_daily
                        WHERE tenant_id = :tenant_id AND project_id = :project_id
                          AND source_record_id LIKE :prefix
                        """
                    ),
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "prefix": prefix + "%",
                    },
                )
                conn.execute(
                    text(
                        """
                        DELETE FROM fact_production_daily
                        WHERE tenant_id = :tenant_id AND project_id = :project_id
                          AND source_record_id LIKE :prefix
                        """
                    ),
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "prefix": prefix + "%",
                    },
                )
                conn.execute(
                    text(
                        """
                        DELETE FROM fact_maintenance_workorder
                        WHERE tenant_id = :tenant_id AND project_id = :project_id
                          AND source_record_id LIKE :prefix
                        """
                    ),
                    {
                        "tenant_id": params.tenant_id,
                        "project_id": params.project_id,
                        "prefix": prefix + "%",
                    },
                )

            # Upsert-like behavior for dimensions: insert if not exists.
            for row in payload["dim_equipment"]:
                conn.execute(
                    text(
                        """
                        INSERT INTO dim_equipment(
                            tenant_id, project_id, unified_equipment_id, name, line_id, area,
                            source_system, source_record_id
                        )
                        VALUES (
                            :tenant_id, :project_id, :unified_equipment_id, :name, :line_id, :area,
                            :source_system, :source_record_id
                        )
                        ON CONFLICT (tenant_id, project_id, unified_equipment_id) DO NOTHING
                        """
                    ),
                    row,
                )
            for row in payload["dim_material"]:
                conn.execute(
                    text(
                        """
                        INSERT INTO dim_material(
                            tenant_id, project_id, unified_material_id, name, category,
                            source_system, source_record_id
                        )
                        VALUES (
                            :tenant_id, :project_id, :unified_material_id, :name, :category,
                            :source_system, :source_record_id
                        )
                        ON CONFLICT (tenant_id, project_id, unified_material_id) DO NOTHING
                        """
                    ),
                    row,
                )

            # metric_lineage is governed by additional constraints (e.g. single active per metric).
            # For seed determinism, clear existing metric_lineage rows in the current scope.
            conn.execute(
                text(
                    """
                    DELETE FROM metric_lineage
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                    """
                ),
                {"tenant_id": params.tenant_id, "project_id": params.project_id},
            )

            # metric_lineage: unique on (tenant_id, project_id, metric_name, lineage_version)
            for row in payload["metric_lineage"]:
                row_for_db = dict(row)
                row_for_db["source_systems"] = json.dumps(
                    row_for_db.get("source_systems") or []
                )
                row_for_db.setdefault("status", "active")
                row_for_db.setdefault("is_active", True)
                conn.execute(
                    text(
                        """
                        INSERT INTO metric_lineage(
                            tenant_id, project_id, metric_name, lineage_version,
                            status, formula, source_systems, owner, is_active
                        )
                        VALUES (
                            :tenant_id, :project_id, :metric_name, :lineage_version,
                            :status, :formula, CAST(:source_systems AS jsonb), :owner, :is_active
                        )
                        ON CONFLICT (tenant_id, project_id, metric_name, lineage_version) DO NOTHING
                        """
                    ),
                    row_for_db,
                )

            conn.commit()

            equipment_id_map = _fetch_equipment_id_map(conn, params.tenant_id, params.project_id)

            inserted: dict[str, int] = {}

            def _log_progress(*, table: str, inserted_rows: int, total_rows: int) -> None:
                if total_rows <= 0:
                    return
                if inserted_rows % _PROGRESS_LOG_EVERY_ROWS == 0 or inserted_rows == total_rows:
                    print(
                        json.dumps(
                            {
                                "script": "seed_data",
                                "status": "progress",
                                "table": table,
                                "inserted_rows": inserted_rows,
                                "total_rows": total_rows,
                                "dataset_version": params.edge_cases.dataset_version,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        file=sys.stderr,
                    )

            def insert_many(table: str, rows: list[dict[str, Any]]) -> int:
                if not rows:
                    inserted[table] = 0
                    return 0

                prepared: list[dict[str, Any]] = []
                for row in rows:
                    r = dict(row)
                    unified_equipment_id = r.pop("unified_equipment_id", None)
                    if unified_equipment_id is None:
                        equipment_id = None
                    else:
                        equipment_id = equipment_id_map.get(unified_equipment_id)
                        if not equipment_id:
                            raise ContractViolationError(
                                "Seed referenced unknown equipment",
                                details={"unified_equipment_id": unified_equipment_id},
                            )
                    r["equipment_id"] = equipment_id
                    prepared.append(r)

                total = len(prepared)
                if table == "fact_production_daily":
                    sql = text(
                        """
                        INSERT INTO fact_production_daily(
                            tenant_id, project_id, business_date, equipment_id,
                            quantity, unit, source_system, source_record_id,
                            time_start, time_end, extracted_at
                        )
                        VALUES (
                            :tenant_id, :project_id, CAST(:business_date AS date), CAST(:equipment_id AS uuid),
                            CAST(:quantity AS numeric), :unit, :source_system, :source_record_id,
                            CAST(:time_start AS timestamptz), CAST(:time_end AS timestamptz), CAST(:extracted_at AS timestamptz)
                        )
                        ON CONFLICT (tenant_id, project_id, business_date, equipment_id) DO NOTHING
                        """
                    )
                elif table == "fact_energy_daily":
                    sql = text(
                        """
                        INSERT INTO fact_energy_daily(
                            tenant_id, project_id, business_date, equipment_id,
                            energy_type, consumption, unit, source_system, source_record_id,
                            time_start, time_end, extracted_at
                        )
                        VALUES (
                            :tenant_id, :project_id, CAST(:business_date AS date), CAST(:equipment_id AS uuid),
                            :energy_type, CAST(:consumption AS numeric), :unit, :source_system, :source_record_id,
                            CAST(:time_start AS timestamptz), CAST(:time_end AS timestamptz), CAST(:extracted_at AS timestamptz)
                        )
                        ON CONFLICT (tenant_id, project_id, business_date, equipment_id, energy_type) DO NOTHING
                        """
                    )
                elif table == "fact_cost_daily":
                    sql = text(
                        """
                        INSERT INTO fact_cost_daily(
                            tenant_id, project_id, business_date, equipment_id,
                            cost_item, amount, currency, lineage_version,
                            source_system, source_record_id,
                            time_start, time_end, extracted_at
                        )
                        VALUES (
                            :tenant_id, :project_id, CAST(:business_date AS date), CAST(:equipment_id AS uuid),
                            :cost_item, CAST(:amount AS numeric), :currency, :lineage_version,
                            :source_system, :source_record_id,
                            CAST(:time_start AS timestamptz), CAST(:time_end AS timestamptz), CAST(:extracted_at AS timestamptz)
                        )
                        ON CONFLICT (tenant_id, project_id, business_date, equipment_id, cost_item, lineage_version) DO NOTHING
                        """
                    )
                elif table == "fact_alarm_event":
                    sql = text(
                        """
                        INSERT INTO fact_alarm_event(
                            tenant_id, project_id, event_time, equipment_id,
                            alarm_code, severity, message, source_system, source_record_id,
                            created_at
                        )
                        VALUES (
                            :tenant_id, :project_id, CAST(:event_time AS timestamptz), CAST(:equipment_id AS uuid),
                            :alarm_code, :severity, :message, :source_system, :source_record_id,
                            CAST(:created_at AS timestamptz)
                        )
                        """
                    )
                elif table == "fact_maintenance_workorder":
                    sql = text(
                        """
                        INSERT INTO fact_maintenance_workorder(
                            tenant_id, project_id, workorder_no, equipment_id,
                            status, created_time, closed_time,
                            fault_code, fault_desc,
                            source_system, source_record_id
                        )
                        VALUES (
                            :tenant_id, :project_id, :workorder_no, CAST(:equipment_id AS uuid),
                            :status, CAST(:created_time AS timestamptz), CAST(:closed_time AS timestamptz),
                            :fault_code, :fault_desc,
                            :source_system, :source_record_id
                        )
                        ON CONFLICT (tenant_id, project_id, workorder_no) DO NOTHING
                        """
                    )
                else:
                    raise ValidationError("Unsupported table for seed", details={"table": table})

                batch_size = _PROGRESS_LOG_EVERY_ROWS
                inserted_rows = 0
                for i in range(0, total, batch_size):
                    batch = prepared[i : i + batch_size]
                    conn.execute(sql, batch)
                    inserted_rows += len(batch)
                    _log_progress(table=table, inserted_rows=inserted_rows, total_rows=total)

                inserted[table] = inserted_rows
                return inserted_rows

            insert_many("fact_production_daily", payload["fact_production_daily"])
            insert_many("fact_energy_daily", payload["fact_energy_daily"])
            insert_many("fact_cost_daily", payload["fact_cost_daily"])
            insert_many("fact_alarm_event", payload["fact_alarm_event"])
            insert_many("fact_maintenance_workorder", payload["fact_maintenance_workorder"])

            conn.commit()

            dataset_prefix = f"{params.edge_cases.dataset_version}:edge:"
            evidence: list[EdgeEvidenceRef] = []

            prod_rows = conn.execute(
                text(
                    """
                    SELECT id::text, source_record_id, business_date::text, time_start::text, time_end::text, extracted_at::text
                    FROM fact_production_daily
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND source_record_id LIKE :prefix
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                ),
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "prefix": dataset_prefix + "%",
                },
            ).all()
            for row in prod_rows:
                src = row[1]
                edge_type = src.split(":edge:", 1)[1].split(":", 1)[0] if ":edge:" in src else "unknown"
                evidence.append(
                    EdgeEvidenceRef(
                        edge_type=edge_type,
                        table="fact_production_daily",
                        primary_key=row[0],
                        business_date=row[2],
                        time_range={"time_start": row[3], "time_end": row[4], "extracted_at": row[5]},
                    )
                )

            alarm_rows = conn.execute(
                text(
                    """
                    SELECT id::text, source_record_id, event_time::text, created_at::text
                    FROM fact_alarm_event
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND source_record_id LIKE :prefix
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                ),
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "prefix": dataset_prefix + "%",
                },
            ).all()
            for row in alarm_rows:
                src = row[1]
                edge_type = src.split(":edge:", 1)[1].split(":", 1)[0] if ":edge:" in src else "unknown"
                evidence.append(
                    EdgeEvidenceRef(
                        edge_type=edge_type,
                        table="fact_alarm_event",
                        primary_key=row[0],
                        time_range={"event_time": row[2], "created_at": row[3]},
                    )
                )

            energy_rows = conn.execute(
                text(
                    """
                    SELECT id::text, source_record_id, business_date::text, time_start::text, time_end::text, extracted_at::text
                    FROM fact_energy_daily
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND source_record_id LIKE :prefix
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                ),
                {
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "prefix": dataset_prefix + "%",
                },
            ).all()
            for row in energy_rows:
                src = row[1]
                edge_type = src.split(":edge:", 1)[1].split(":", 1)[0] if ":edge:" in src else "unknown"
                evidence.append(
                    EdgeEvidenceRef(
                        edge_type=edge_type,
                        table="fact_energy_daily",
                        primary_key=row[0],
                        business_date=row[2],
                        time_range={"time_start": row[3], "time_end": row[4], "extracted_at": row[5]},
                    )
                )

            return {
                "inserted": inserted,
                "edge_evidence": [
                    {
                        "edge_type": e.edge_type,
                        "table": e.table,
                        "primary_key": e.primary_key,
                        "time_range": e.time_range,
                        "business_date": e.business_date,
                    }
                    for e in evidence
                ],
            }

    except Exception as e:
        raise map_db_error(e)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed reproducible GangQing dataset into Postgres")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--tenant-id", type=str, default=None)
    parser.add_argument("--project-id", type=str, default=None)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--equipment-count", type=int, default=None)
    parser.add_argument("--materials-count", type=int, default=None)
    parser.add_argument("--events-per-day", type=int, default=None)
    parser.add_argument("--workorders-count", type=int, default=None)
    parser.add_argument("--dataset-version", type=str, default=None)
    parser.add_argument("--edge-missing-enabled", type=lambda s: s.lower() == "true", default=None)
    parser.add_argument("--edge-delay-enabled", type=lambda s: s.lower() == "true", default=None)
    parser.add_argument("--edge-duplicate-enabled", type=lambda s: s.lower() == "true", default=None)
    parser.add_argument("--edge-extreme-enabled", type=lambda s: s.lower() == "true", default=None)
    parser.add_argument("--edge-missing-count", type=int, default=None)
    parser.add_argument("--edge-delay-count", type=int, default=None)
    parser.add_argument("--edge-duplicate-count", type=int, default=None)
    parser.add_argument("--edge-extreme-count", type=int, default=None)
    return parser


def main() -> int:
    try:
        args = _build_parser().parse_args()
        database_url = _require_database_url()
        params = _build_params(args)

        # Connection check with structured error.
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect():
                pass
        except Exception as e:
            raise UpstreamUnavailableError("Postgres", cause=str(e))

        result = seed_database(database_url=database_url, params=params)
        print(
            json.dumps(
                {
                    "script": "seed_data",
                    "status": "PASS",
                    "seed": params.seed,
                    "tenant_id": params.tenant_id,
                    "project_id": params.project_id,
                    "start_date": params.start_date.isoformat(),
                    "days": params.days,
                    "dataset_version": params.edge_cases.dataset_version,
                    "inserted": result["inserted"],
                    "edge_evidence": result["edge_evidence"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        print("seed_data: PASS")
        return 0

    except (ConfigMissingError, ValidationError, UpstreamUnavailableError) as e:
        error_response = e.to_response()
        details = (
            f" details={json.dumps(error_response.details, ensure_ascii=False, sort_keys=True)}"
            if error_response.details
            else ""
        )
        print(f"Error [{error_response.code}]: {error_response.message}{details}", file=sys.stderr)
        return 1

    except MigrationError as e:
        error_response = e.to_response()
        details = (
            f" details={json.dumps(error_response.details, ensure_ascii=False, sort_keys=True)}"
            if error_response.details
            else ""
        )
        print(f"Error [{error_response.code}]: {error_response.message}{details}", file=sys.stderr)
        return 1

    except Exception as e:
        mapped = map_db_error(e)
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
