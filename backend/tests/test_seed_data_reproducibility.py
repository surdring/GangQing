"""Unit tests for seed_data reproducibility and validation.

These tests focus on pure generation determinism:
- Same seed + params => identical payload
- Different seed => payload differs
- Invalid params should fail with structured ValidationError
"""

from __future__ import annotations

import os
import sys
from argparse import Namespace
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

# Add backend and scripts to path for imports
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
for _p in (str(_BACKEND_DIR), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from gangqing_db.errors import ConfigMissingError, ValidationError

import seed_data


def test_generate_seed_payload_reproducible_same_seed() -> None:
    params = seed_data.SeedConfig(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=5,
        equipment_count=2,
        materials_count=2,
        events_per_day=2,
        workorders_count=3,
        edge_cases=seed_data.SeedEdgeCasesConfig(dataset_version="test"),
    )

    payload1 = seed_data.generate_seed_payload(params)
    payload2 = seed_data.generate_seed_payload(params)

    assert payload1 == payload2


def test_generate_seed_payload_diff_seed_should_differ() -> None:
    params1 = seed_data.SeedConfig(
        seed=1,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=3,
        equipment_count=2,
        materials_count=2,
        events_per_day=1,
        workorders_count=2,
        edge_cases=seed_data.SeedEdgeCasesConfig(dataset_version="test"),
    )
    params2 = seed_data.SeedConfig(
        seed=2,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=3,
        equipment_count=2,
        materials_count=2,
        events_per_day=1,
        workorders_count=2,
        edge_cases=seed_data.SeedEdgeCasesConfig(dataset_version="test"),
    )

    payload1 = seed_data.generate_seed_payload(params1)
    payload2 = seed_data.generate_seed_payload(params2)

    assert payload1 != payload2


def test_build_params_days_must_be_positive() -> None:
    args = Namespace(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date="2026-02-01",
        days=0,
        equipment_count=1,
        materials_count=1,
        events_per_day=0,
        workorders_count=0,
        dataset_version="test",
        edge_missing_enabled=None,
        edge_delay_enabled=None,
        edge_duplicate_enabled=None,
        edge_extreme_enabled=None,
        edge_missing_count=None,
        edge_delay_count=None,
        edge_duplicate_count=None,
        edge_extreme_count=None,
    )

    with pytest.raises(ValidationError) as exc_info:
        seed_data._build_params(args)

    assert exc_info.value.code.value == "VALIDATION_ERROR"
    assert exc_info.value.message.isascii()
    assert "days" in str((exc_info.value.details or {}).get("cause", ""))


def test_generate_seed_payload_missing_edge_must_have_null_unified_equipment_id() -> None:
    params = seed_data.SeedConfig(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=4,
        equipment_count=3,
        materials_count=1,
        events_per_day=0,
        workorders_count=0,
        edge_cases=seed_data.SeedEdgeCasesConfig(
            dataset_version="test",
            missing_enabled=True,
            delay_enabled=False,
            duplicate_enabled=False,
            extreme_enabled=False,
            missing_count=1,
        ),
    )

    payload = seed_data.generate_seed_payload(params)
    prod_rows = payload["fact_production_daily"]
    missing_rows = [r for r in prod_rows if r.get("unified_equipment_id") is None]
    assert len(missing_rows) >= 1
    assert any(":edge:missing:" in (r.get("source_record_id") or "") for r in missing_rows)


def test_generate_seed_payload_delay_edge_must_have_extracted_at_gt_time_end() -> None:
    params = seed_data.SeedConfig(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=4,
        equipment_count=3,
        materials_count=1,
        events_per_day=1,
        workorders_count=0,
        edge_cases=seed_data.SeedEdgeCasesConfig(
            dataset_version="test",
            missing_enabled=False,
            delay_enabled=True,
            duplicate_enabled=False,
            extreme_enabled=False,
            delay_count=1,
        ),
    )

    payload = seed_data.generate_seed_payload(params)
    prod_rows = payload["fact_production_daily"]
    delayed_prod = [
        r
        for r in prod_rows
        if ":edge:delay:" in (r.get("source_record_id") or "")
    ]
    assert len(delayed_prod) >= 1

    for r in delayed_prod:
        assert r["extracted_at"] > r["time_end"]

    alarm_rows = payload["fact_alarm_event"]
    delayed_alarm = [
        r
        for r in alarm_rows
        if ":edge:delay:alarm:" in (r.get("source_record_id") or "")
    ]
    assert len(delayed_alarm) >= 1
    for r in delayed_alarm:
        assert r["created_at"] > r["event_time"]


def test_generate_seed_payload_extreme_edge_must_use_expected_values() -> None:
    params = seed_data.SeedConfig(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=4,
        equipment_count=3,
        materials_count=1,
        events_per_day=0,
        workorders_count=0,
        edge_cases=seed_data.SeedEdgeCasesConfig(
            dataset_version="test",
            missing_enabled=False,
            delay_enabled=False,
            duplicate_enabled=False,
            extreme_enabled=True,
            extreme_count=1,
        ),
    )

    payload = seed_data.generate_seed_payload(params)
    prod_rows = payload["fact_production_daily"]
    extreme_prod = [
        r
        for r in prod_rows
        if ":edge:extreme:prod:" in (r.get("source_record_id") or "")
    ]
    assert len(extreme_prod) >= 1
    assert any(r.get("quantity") == str(seed_data._EXTREME_PRODUCTION_QTY) for r in extreme_prod)

    energy_rows = payload["fact_energy_daily"]
    extreme_energy = [
        r
        for r in energy_rows
        if ":edge:extreme:energy:" in (r.get("source_record_id") or "")
    ]
    assert len(extreme_energy) >= 1
    assert any(r.get("consumption") == str(seed_data._EXTREME_ENERGY_CONSUMPTION) for r in extreme_energy)


def test_generate_seed_payload_duplicate_alarm_edge_must_generate_multiple_rows() -> None:
    params = seed_data.SeedConfig(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=4,
        equipment_count=2,
        materials_count=1,
        events_per_day=1,
        workorders_count=0,
        edge_cases=seed_data.SeedEdgeCasesConfig(
            dataset_version="test",
            missing_enabled=False,
            delay_enabled=False,
            duplicate_enabled=True,
            extreme_enabled=False,
            duplicate_count=2,
        ),
    )

    payload = seed_data.generate_seed_payload(params)
    alarm_rows = payload["fact_alarm_event"]
    duplicate_rows = [
        r
        for r in alarm_rows
        if ":edge:duplicate:alarm:" in (r.get("source_record_id") or "")
    ]
    assert len(duplicate_rows) >= 1


def test_generate_seed_payload_boundary_days_1_equipment_1_must_work() -> None:
    params = seed_data.SeedConfig(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date=date(2026, 2, 1),
        days=1,
        equipment_count=1,
        materials_count=1,
        events_per_day=1,
        workorders_count=1,
        edge_cases=seed_data.SeedEdgeCasesConfig(
            dataset_version="test",
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

    payload = seed_data.generate_seed_payload(params)
    assert len(payload["dim_equipment"]) == 1
    assert len(payload["dim_material"]) == 1
    assert len(payload["fact_production_daily"]) >= 1
    assert len(payload["fact_energy_daily"]) >= 1
    assert len(payload["fact_alarm_event"]) >= 1


def test_env_bool_invalid_must_fail_with_english_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GANGQING_SEED_EDGE_MISSING_ENABLED", "not-a-bool")

    args = Namespace(
        seed=42,
        tenant_id="t1",
        project_id="p1",
        start_date="2026-02-01",
        days=1,
        equipment_count=1,
        materials_count=1,
        events_per_day=0,
        workorders_count=0,
        dataset_version="test",
        edge_missing_enabled=None,
        edge_delay_enabled=None,
        edge_duplicate_enabled=None,
        edge_extreme_enabled=None,
        edge_missing_count=None,
        edge_delay_count=None,
        edge_duplicate_count=None,
        edge_extreme_count=None,
    )

    with pytest.raises(ValidationError) as exc_info:
        seed_data._build_params(args)

    assert exc_info.value.code.value == "VALIDATION_ERROR"
    assert exc_info.value.message.isascii()


def test_require_database_url_missing_must_fail() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("gangqing_db.settings._load_dotenv_file", return_value=None):
            with pytest.raises(ConfigMissingError) as exc_info:
                seed_data._require_database_url()

    assert exc_info.value.code.value == "CONFIG_MISSING"
    assert "GANGQING_DATABASE_URL" in exc_info.value.message
