from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from gangqing_db.metric_lineage import MetricLineageBindingRequest, RequestContext, bind_metric_lineage_for_computation
from gangqing_db.settings import load_settings


def _require_database_url() -> str:
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL") from e
        raise
    return settings.database_url


def _build_alembic_config() -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


def _ctx(*, tenant_id: str, project_id: str) -> RequestContext:
    return RequestContext(
        request_id=f"test-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        tenant_id=tenant_id,
        project_id=project_id,
        capabilities={"metric_lineage:read"},
    )


@pytest.fixture(scope="module", autouse=True)
def _apply_migrations_to_head() -> None:
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', 't_metric', true)"))
        conn.execute(text("SELECT set_config('app.current_project', 'p_metric', true)"))
        conn.commit()

        conn.execute(
            text(
                """
                INSERT INTO metric_lineage(
                    tenant_id, project_id, metric_name, lineage_version,
                    status, formula, source_systems, owner, is_active
                ) VALUES (
                    :tenant_id, :project_id, :metric_name, :lineage_version,
                    :status, :formula, CAST(:source_systems AS jsonb), :owner, :is_active
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "tenant_id": "t_metric",
                "project_id": "p_metric",
                "metric_name": "oee",
                "lineage_version": "1.0.0",
                "status": "active",
                "formula": "good_time / planned_time",
                "source_systems": "[\"MES\"]",
                "owner": "perf",
                "is_active": True,
            },
        )
        conn.commit()


def test_metric_lineage_binding_latency_p95_under_2s() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric")
    req = MetricLineageBindingRequest(
        metric_name="oee",
        lineageVersion="1.0.0",
        scenarioKey=None,
    )

    durations: list[float] = []
    for _ in range(30):
        start = time.perf_counter()
        bind_metric_lineage_for_computation(req, ctx=ctx, allow_default_active=False, audit=False)
        durations.append(time.perf_counter() - start)

    durations_sorted = sorted(durations)
    p95_index = int(0.95 * (len(durations_sorted) - 1))
    p95 = durations_sorted[p95_index]
    assert p95 < 2.0


def test_metric_lineage_binding_concurrency_safe() -> None:
    def _call() -> str:
        ctx = _ctx(tenant_id="t_metric", project_id="p_metric")
        req = MetricLineageBindingRequest(
            metric_name="oee",
            lineageVersion="1.0.0",
            scenarioKey=None,
        )
        _, _, evidence = bind_metric_lineage_for_computation(req, ctx=ctx, allow_default_active=False, audit=False)
        return evidence.evidence_id

    futures = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for _ in range(20):
            futures.append(executor.submit(_call))

        results: list[str] = []
        for f in as_completed(futures):
            results.append(f.result())

    assert len(results) == 20
