"""Smoke test for metric_lineage repository.

This script validates end-to-end metric lineage query behavior against a real Postgres:
- Requires GANGQING_DATABASE_URL
- Applies migrations to head
- Seeds minimal metric_lineage rows
- Queries by explicit lineageVersion and by default active selection

No mock/skip allowed.
"""

from __future__ import annotations

import json
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

from gangqing_db.errors import ConfigMissingError, MigrationFailedError, MigrationError, map_db_error
from gangqing_db.metric_lineage import (
    MetricLineageBindingRequest,
    MetricLineageQuery,
    RequestContext,
    bind_metric_lineage_for_computation,
    get_metric_lineage,
)
from gangqing_db.settings import load_settings


def _get_expected_head(cfg: Config) -> str:
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    if not head:
        raise MigrationFailedError(
            "upgrade",
            version=None,
            cause="Unable to resolve alembic head revision",
        )
    return head


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
        row = conn.execute(
            text("SELECT version_num FROM gangqing_alembic_version LIMIT 1")
        ).fetchone()
        return row[0] if row else None


def _set_rls_context(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})


def _seed(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(
        text(
            """
            DELETE FROM metric_lineage_scenario_mapping
            WHERE tenant_id = :tenant_id AND project_id = :project_id
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id},
    )

    conn.execute(
        text(
            """
            DELETE FROM metric_lineage
            WHERE tenant_id = :tenant_id AND project_id = :project_id
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id},
    )

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
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "metric_name": "oee",
            "lineage_version": "1.0.0",
            "status": "active",
            "formula": "good_time / planned_time",
            "source_systems": "[\"MES\"]",
            "owner": "smoke",
            "is_active": True,
        },
    )

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
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "metric_name": "oee_depr",
            "lineage_version": "2.0.0",
            "status": "deprecated",
            "formula": "good_time / planned_time",
            "source_systems": "[\"MES\"]",
            "owner": "smoke",
            "is_active": True,
        },
    )

    conn.execute(
        text(
            """
            INSERT INTO metric_lineage_scenario_mapping(
                tenant_id, project_id, metric_name, scenario_key, lineage_version,
                status, owner, is_active
            ) VALUES (
                :tenant_id, :project_id, :metric_name, :scenario_key, :lineage_version,
                :status, :owner, :is_active
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "metric_name": "oee",
            "scenario_key": "finance_month_close",
            "lineage_version": "1.0.0",
            "status": "active",
            "owner": "smoke",
            "is_active": True,
        },
    )


def main() -> int:
    request_id = f"metric-lineage-smoke-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    try:
        database_url = _require_database_url()
        cfg = _build_alembic_config()
        expected_head = _get_expected_head(cfg)

        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect():
                pass
        except Exception as e:
            raise map_db_error(e, request_id=request_id)

        command.upgrade(cfg, "head")
        version = _get_current_version(engine)
        if version != expected_head:
            raise MigrationFailedError(
                "upgrade",
                version=version,
                cause=f"Expected version {expected_head}, got {version}",
                request_id=request_id,
            )

        tenant_id = "t_smoke"
        project_id = "p_smoke"

        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()
            _seed(conn, tenant_id=tenant_id, project_id=project_id)
            conn.commit()

        ctx = RequestContext(
            request_id=request_id,
            tenant_id=tenant_id,
            project_id=project_id,
            capabilities={"metric:lineage:read"},
        )

        rec = get_metric_lineage(
            MetricLineageQuery(
                tenantId=tenant_id,
                projectId=project_id,
                metric_name="oee",
                lineageVersion="1.0.0",
            ),
            ctx=ctx,
        )
        if rec.lineage_version != "1.0.0":
            raise RuntimeError("Unexpected lineageVersion")

        rec2 = get_metric_lineage(
            MetricLineageQuery(
                tenantId=tenant_id,
                projectId=project_id,
                metric_name="oee",
                lineageVersion=None,
            ),
            ctx=ctx,
        )
        if rec2.lineage_version != "1.0.0":
            raise RuntimeError("Unexpected default active lineageVersion")

        try:
            bind_metric_lineage_for_computation(
                MetricLineageBindingRequest(
                    tenantId=tenant_id,
                    projectId=project_id,
                    metric_name="oee",
                    lineageVersion=None,
                ),
                ctx=ctx,
                allow_default_active=False,
                audit=True,
            )
            raise RuntimeError("Expected lineage binding to fail when lineageVersion is missing")
        except MigrationError as e:
            er = e.to_response()
            if er.code != "EVIDENCE_MISMATCH":
                raise RuntimeError("Unexpected error code for missing lineageVersion")
            if not isinstance(er.message, str) or not er.message.isascii():
                raise RuntimeError("Expected english error message for missing lineageVersion")
            if er.request_id != request_id:
                raise RuntimeError("Expected requestId to be preserved in error response")
            if er.retryable is not False:
                raise RuntimeError("Expected retryable=false for missing lineageVersion")
            if not isinstance(er.details, dict):
                raise RuntimeError("Expected details to be a dict for missing lineageVersion")
            if er.details.get("reason") != "lineage_version_required":
                raise RuntimeError("Expected details.reason=lineage_version_required")

        rec3, _, evidence3 = bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                tenantId=tenant_id,
                projectId=project_id,
                metric_name="oee",
                lineageVersion=None,
                scenarioKey="finance_month_close",
            ),
            ctx=ctx,
            allow_default_active=False,
            audit=True,
        )
        if rec3.lineage_version != "1.0.0" or evidence3.lineage_version != "1.0.0":
            raise RuntimeError("Unexpected lineageVersion resolved by scenarioKey")
        dumped_evidence3 = evidence3.model_dump(by_alias=True)
        if dumped_evidence3.get("lineageVersion") != "1.0.0":
            raise RuntimeError("Evidence must include lineageVersion")
        if not isinstance(dumped_evidence3.get("sourceLocator"), dict):
            raise RuntimeError("Evidence must include sourceLocator")
        if not isinstance(dumped_evidence3.get("timeRange"), dict):
            raise RuntimeError("Evidence must include timeRange")
        if dumped_evidence3["timeRange"]["end"] <= dumped_evidence3["timeRange"]["start"]:
            raise RuntimeError("Evidence timeRange.end must be greater than timeRange.start")

        try:
            bind_metric_lineage_for_computation(
                MetricLineageBindingRequest(
                    tenantId=tenant_id,
                    projectId=project_id,
                    metric_name="oee_depr",
                    lineageVersion="2.0.0",
                    scenarioKey=None,
                ),
                ctx=ctx,
                allow_default_active=False,
                allow_deprecated=False,
                audit=True,
            )
            raise RuntimeError("Expected deprecated lineageVersion to be rejected")
        except MigrationError as e:
            er = e.to_response()
            if er.code != "EVIDENCE_MISMATCH":
                raise RuntimeError("Unexpected error code for deprecated lineageVersion")
            if not isinstance(er.message, str) or not er.message.isascii():
                raise RuntimeError("Expected english error message for deprecated lineageVersion")
            if er.request_id != request_id:
                raise RuntimeError("Expected requestId to be preserved in deprecated error response")
            if er.retryable is not False:
                raise RuntimeError("Expected retryable=false for deprecated lineageVersion")
            if not isinstance(er.details, dict):
                raise RuntimeError("Expected details to be a dict for deprecated lineageVersion")
            if er.details.get("reason") != "lineage_version_deprecated":
                raise RuntimeError("Expected details.reason=lineage_version_deprecated")

        print("metric_lineage_smoke_test: PASS")
        return 0

    except ConfigMissingError as e:
        er = e.to_response()
        print(
            f"Error [{er.code}]: {er.message}"
            + (
                f" details={json.dumps(er.details, ensure_ascii=False, sort_keys=True)}"
                if er.details
                else ""
            ),
            file=sys.stderr,
        )
        return 1

    except (MigrationError, MigrationFailedError) as e:
        er = e.to_response()
        print(
            f"Error [{er.code}]: {er.message}"
            + (
                f" details={json.dumps(er.details, ensure_ascii=False, sort_keys=True)}"
                if er.details
                else ""
            ),
            file=sys.stderr,
        )
        return 1

    except Exception as e:
        mapped = map_db_error(e, request_id=request_id)
        er = mapped.to_response()
        print(
            f"Error [{er.code}]: {er.message}"
            + (
                f" details={json.dumps(er.details, ensure_ascii=False, sort_keys=True)}"
                if er.details
                else ""
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
