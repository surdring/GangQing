from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from gangqing_db.errors import AuthError, ErrorCode, EvidenceMissingError, EvidenceMismatchError, ForbiddenError
from gangqing_db.metric_lineage import (
    MetricLineageBindingRequest,
    MetricLineageQuery,
    RequestContext,
    bind_metric_lineage_for_computation,
    get_metric_lineage,
)
from gangqing_db.settings import load_settings


def _require_database_url() -> str:
    try:
        settings = load_settings()
    except Exception as e:
        if not os.getenv("GANGQING_DATABASE_URL"):
            raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL") from e
        raise
    return settings.database_url


def _set_rls_context(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})


def _build_alembic_config() -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "backend" / "alembic.ini"
    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", "backend/migrations")
    return cfg


@pytest.fixture(scope="module", autouse=True)
def _prepare_metric_lineage_data() -> None:
    database_url = _require_database_url()
    cfg = _build_alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(database_url, pool_pre_ping=True)

    tenant_id = "t_metric"
    project_id = "p_metric"

    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()

        conn.execute(
            text(
                """
                DELETE FROM metric_lineage_scenario_mapping
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        )
        conn.commit()

        conn.execute(
            text(
                """
                DELETE FROM metric_lineage
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        )
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
                "owner": "test",
                "is_active": True,
            },
        )
        conn.commit()


def _insert_metric_lineage(
    *,
    tenant_id: str,
    project_id: str,
    metric_name: str,
    lineage_version: str,
    status: str,
    is_active: bool,
    owner: str,
) -> None:
    database_url = _require_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
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
                "tenant_id": tenant_id,
                "project_id": project_id,
                "metric_name": metric_name,
                "lineage_version": lineage_version,
                "status": status,
                "formula": "good_time / planned_time",
                "source_systems": "[\"MES\"]",
                "owner": owner,
                "is_active": is_active,
            },
        )
        conn.commit()


def _insert_scenario_mapping(
    *,
    tenant_id: str,
    project_id: str,
    metric_name: str,
    scenario_key: str,
    lineage_version: str,
    status: str,
    is_active: bool,
    owner: str,
) -> None:
    database_url = _require_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()
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
                "metric_name": metric_name,
                "scenario_key": scenario_key,
                "lineage_version": lineage_version,
                "status": status,
                "owner": owner,
                "is_active": is_active,
            },
        )
        conn.commit()


def _latest_audit_row(*, tenant_id: str, project_id: str, request_id: str) -> dict | None:
    database_url = _require_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id=tenant_id, project_id=project_id)
        conn.commit()
        row = conn.execute(
            text(
                """
                SELECT request_id, result_status, error_code, action_summary, evidence_refs
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id = :request_id
                  AND resource = 'metric_lineage_binding'
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "request_id": request_id},
        ).mappings().first()
        return dict(row) if row is not None else None


def _ctx(*, tenant_id: str, project_id: str, capabilities: set[str]) -> RequestContext:
    return RequestContext(
        request_id=f"test-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        tenant_id=tenant_id,
        project_id=project_id,
        capabilities=capabilities,
    )


def test_get_metric_lineage_by_version_success() -> None:
    query = MetricLineageQuery(
        metric_name="oee",
        lineageVersion="1.0.0",
    )
    record = get_metric_lineage(query, ctx=_ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"}))
    assert record.metric_name == "oee"
    assert record.lineage_version == "1.0.0"
    assert record.status == "active"

    dumped = record.model_dump(by_alias=True)
    assert dumped.get("lineageVersion") == "1.0.0"


def test_get_metric_lineage_missing_returns_evidence_missing() -> None:
    query = MetricLineageQuery(
        metric_name="missing_metric",
        lineageVersion="1.0.0",
    )

    with pytest.raises(EvidenceMissingError) as exc_info:
        get_metric_lineage(query, ctx=_ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"}))

    err = exc_info.value
    assert err.code.value == ErrorCode.EVIDENCE_MISSING.value
    response = err.to_response()
    assert response.code == ErrorCode.EVIDENCE_MISSING.value
    assert response.message.isascii()
    assert response.retryable is False
    assert response.request_id is not None
    dumped = response.model_dump(by_alias=True)
    assert dumped.get("requestId") is not None



def test_bind_user_specified_success() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    record, decision, evidence = bind_metric_lineage_for_computation(
        MetricLineageBindingRequest(
            metric_name="oee",
            lineageVersion="1.0.0",
            scenarioKey=None,
        ),
        ctx=ctx,
        audit=False,
    )
    assert record.lineage_version == "1.0.0"
    assert decision.lineage_version == "1.0.0"
    assert evidence.lineage_version == "1.0.0"


def test_metric_lineage_query_invalid_semver_rejected() -> None:
    with pytest.raises(ValueError):
        MetricLineageQuery(metric_name="oee", lineageVersion="v1")


def test_metric_lineage_binding_request_invalid_semver_rejected() -> None:
    with pytest.raises(ValueError):
        MetricLineageBindingRequest(metric_name="oee", lineageVersion="1.0")


def test_bind_scenario_mapping_success() -> None:
    _insert_scenario_mapping(
        tenant_id="t_metric",
        project_id="p_metric",
        metric_name="oee",
        scenario_key="finance_month_close",
        lineage_version="1.0.0",
        status="active",
        is_active=True,
        owner="test",
    )
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    record, _, evidence = bind_metric_lineage_for_computation(
        MetricLineageBindingRequest(
            metric_name="oee",
            lineageVersion=None,
            scenarioKey="finance_month_close",
        ),
        ctx=ctx,
        allow_default_active=False,
        audit=False,
    )
    assert record.lineage_version == "1.0.0"
    assert evidence.lineage_version == "1.0.0"


def test_bind_default_active_success() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    record, decision, evidence = bind_metric_lineage_for_computation(
        MetricLineageBindingRequest(
            metric_name="oee",
            lineageVersion=None,
            scenarioKey=None,
        ),
        ctx=ctx,
        allow_default_active=True,
        audit=False,
    )
    assert record.lineage_version == "1.0.0"
    assert decision.method == "default_active"
    assert evidence.lineage_version == "1.0.0"


def test_bind_reject_inactive_when_not_allowed() -> None:
    _insert_metric_lineage(
        tenant_id="t_metric",
        project_id="p_metric",
        metric_name="oee_inactive",
        lineage_version="1.0.0",
        status="active",
        is_active=False,
        owner="test",
    )
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    with pytest.raises(EvidenceMismatchError) as exc_info:
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                metric_name="oee_inactive",
                lineageVersion="1.0.0",
                scenarioKey=None,
            ),
            ctx=ctx,
            allow_inactive=False,
            audit=False,
        )
    resp = exc_info.value.to_response()
    assert resp.code == ErrorCode.EVIDENCE_MISMATCH.value
    assert resp.message.isascii()
    assert resp.details is not None
    assert resp.details.get("reason") == "lineage_version_not_active"


def test_bind_reject_deprecated_when_not_allowed() -> None:
    _insert_metric_lineage(
        tenant_id="t_metric",
        project_id="p_metric",
        metric_name="oee_depr",
        lineage_version="2.0.0",
        status="deprecated",
        is_active=True,
        owner="test",
    )
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    with pytest.raises(EvidenceMismatchError) as exc_info:
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                metric_name="oee_depr",
                lineageVersion="2.0.0",
                scenarioKey=None,
            ),
            ctx=ctx,
            allow_deprecated=False,
            audit=False,
        )
    resp = exc_info.value.to_response()
    assert resp.code == ErrorCode.EVIDENCE_MISMATCH.value
    assert resp.details is not None
    assert resp.details.get("reason") == "lineage_version_deprecated"


def test_bind_reject_missing_version_when_default_not_allowed() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    with pytest.raises(EvidenceMismatchError) as exc_info:
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                metric_name="oee",
                lineageVersion=None,
                scenarioKey=None,
            ),
            ctx=ctx,
            allow_default_active=False,
            audit=False,
        )
    resp = exc_info.value.to_response()
    assert resp.code == ErrorCode.EVIDENCE_MISMATCH.value
    assert resp.details is not None
    assert resp.details.get("reason") == "lineage_version_required"


def test_bind_cross_scope_access_rejected() -> None:
    ctx = _ctx(tenant_id="t_other", project_id="p_other", capabilities={"metric:lineage:read"})
    with pytest.raises(AuthError) as exc_info:
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                tenantId="t_metric",
                projectId="p_metric",
                metric_name="oee",
                lineageVersion="1.0.0",
                scenarioKey=None,
            ),
            ctx=ctx,
            audit=False,
        )
    resp = exc_info.value.to_response()
    assert resp.code == ErrorCode.AUTH_ERROR.value
    assert resp.message.isascii()


def test_bind_partial_scope_params_rejected() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    with pytest.raises(AuthError) as exc_info:
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                tenantId="t_metric",
                projectId=None,
                metric_name="oee",
                lineageVersion="1.0.0",
                scenarioKey=None,
            ),
            ctx=ctx,
            audit=False,
        )
    resp = exc_info.value.to_response()
    assert resp.code == ErrorCode.AUTH_ERROR.value
    assert resp.details is not None
    assert resp.details.get("reason") == "partial_scope_params"


def test_evidence_fields_integrity() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    _, _, evidence = bind_metric_lineage_for_computation(
        MetricLineageBindingRequest(
            metric_name="oee",
            lineageVersion="1.0.0",
            scenarioKey=None,
        ),
        ctx=ctx,
        audit=False,
    )
    dumped = evidence.model_dump(by_alias=True)
    assert dumped.get("lineageVersion") == "1.0.0"
    assert dumped.get("validation") == "verifiable"
    assert dumped.get("timeRange") is not None
    assert dumped["timeRange"]["end"] > dumped["timeRange"]["start"]


def test_bind_audit_event_written_on_success() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    bind_metric_lineage_for_computation(
        MetricLineageBindingRequest(
            metric_name="oee",
            lineageVersion="1.0.0",
            scenarioKey=None,
        ),
        ctx=ctx,
        audit=True,
    )
    row = _latest_audit_row(tenant_id="t_metric", project_id="p_metric", request_id=ctx.request_id)
    assert row is not None
    assert row["result_status"] == "success"
    assert row["error_code"] is None
    assert row["action_summary"] is not None
    assert row["action_summary"].get("scopeFilter") is not None
    assert row["action_summary"]["scopeFilter"].get("policyVersion") == "v1"
    assert row["action_summary"].get("bound_lineage_version") == "1.0.0"


def test_bind_audit_event_written_on_failure() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    with pytest.raises(EvidenceMismatchError):
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                metric_name="oee",
                lineageVersion=None,
                scenarioKey=None,
            ),
            ctx=ctx,
            allow_default_active=False,
            audit=True,
        )
    row = _latest_audit_row(tenant_id="t_metric", project_id="p_metric", request_id=ctx.request_id)
    assert row is not None
    assert row["result_status"] == "failure"
    assert row["error_code"] == ErrorCode.EVIDENCE_MISMATCH.value


def test_scenario_mapping_missing_is_evidence_missing() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    with pytest.raises(EvidenceMissingError) as exc_info:
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                metric_name="oee",
                lineageVersion=None,
                scenarioKey="unknown_scenario",
            ),
            ctx=ctx,
            allow_default_active=False,
            audit=False,
        )
    resp = exc_info.value.to_response()
    assert resp.code == ErrorCode.EVIDENCE_MISSING.value


def test_bind_time_range_uses_data_time_range_when_provided() -> None:
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    _, _, evidence = bind_metric_lineage_for_computation(
        MetricLineageBindingRequest(
            metric_name="oee",
            lineageVersion="1.0.0",
            scenarioKey=None,
        ),
        ctx=ctx,
        data_time_range={"start": start, "end": end},
        audit=False,
    )
    dumped = evidence.model_dump(by_alias=True)
    assert dumped["timeRange"]["start"] == start
    assert dumped["timeRange"]["end"] == end


def test_scenario_mapping_conflict_is_prevented_by_unique_active_constraint() -> None:
    database_url = _require_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id="t_metric", project_id="p_metric")
        conn.commit()
        metric_name = "oee_scn_conflict_unique"
        scenario_key = "scn_conflict_unique"
        conn.execute(
            text(
                """
                DELETE FROM metric_lineage_scenario_mapping
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND metric_name = :metric_name AND scenario_key = :scenario_key
                """
            ),
            {
                "tenant_id": "t_metric",
                "project_id": "p_metric",
                "metric_name": metric_name,
                "scenario_key": scenario_key,
            },
        )
        conn.commit()

        conn.execute(
            text(
                """
                INSERT INTO metric_lineage_scenario_mapping(
                    tenant_id, project_id, metric_name, scenario_key, lineage_version,
                    status, owner, is_active
                ) VALUES (
                    :tenant_id, :project_id, :metric_name, :scenario_key, :lineage_version,
                    'active', 'test', true
                )
                """
            ),
            {
                "tenant_id": "t_metric",
                "project_id": "p_metric",
                "metric_name": metric_name,
                "scenario_key": scenario_key,
                "lineage_version": "1.0.0",
            },
        )
        conn.commit()

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO metric_lineage_scenario_mapping(
                        tenant_id, project_id, metric_name, scenario_key, lineage_version,
                        status, owner, is_active
                    ) VALUES (
                        :tenant_id, :project_id, :metric_name, :scenario_key, :lineage_version,
                        'active', 'test', true
                    )
                    """
                ),
                {
                    "tenant_id": "t_metric",
                    "project_id": "p_metric",
                    "metric_name": metric_name,
                    "scenario_key": scenario_key,
                    "lineage_version": "1.0.1",
                },
            )


def test_default_active_conflict_is_prevented_by_unique_active_constraint() -> None:
    database_url = _require_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id="t_metric", project_id="p_metric")
        conn.commit()
        metric_name = "oee_multi_active_unique"
        conn.execute(
            text(
                """
                DELETE FROM metric_lineage
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND metric_name = :metric_name
                """
            ),
            {"tenant_id": "t_metric", "project_id": "p_metric", "metric_name": metric_name},
        )
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
                """
            ),
            {
                "tenant_id": "t_metric",
                "project_id": "p_metric",
                "metric_name": metric_name,
                "lineage_version": "1.0.0",
                "status": "active",
                "formula": "x",
                "source_systems": "[\"MES\"]",
                "owner": "test",
                "is_active": True,
            },
        )
        conn.commit()

        with pytest.raises(IntegrityError):
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
                    "tenant_id": "t_metric",
                    "project_id": "p_metric",
                    "metric_name": metric_name,
                    "lineage_version": "1.0.1",
                    "status": "active",
                    "formula": "x",
                    "source_systems": "[\"MES\"]",
                    "owner": "test",
                    "is_active": True,
                },
            )


def test_default_active_no_active_versions_is_evidence_missing() -> None:
    _insert_metric_lineage(
        tenant_id="t_metric",
        project_id="p_metric",
        metric_name="oee_no_active",
        lineage_version="1.0.0",
        status="active",
        is_active=False,
        owner="test",
    )
    ctx = _ctx(tenant_id="t_metric", project_id="p_metric", capabilities={"metric:lineage:read"})
    with pytest.raises(EvidenceMissingError) as exc_info:
        bind_metric_lineage_for_computation(
            MetricLineageBindingRequest(
                tenantId="t_metric",
                projectId="p_metric",
                metric_name="oee_no_active",
                lineageVersion=None,
                scenarioKey=None,
            ),
            ctx=ctx,
            allow_default_active=True,
            audit=False,
        )
    resp = exc_info.value.to_response()
    assert resp.code == ErrorCode.EVIDENCE_MISSING.value



def test_data_integrity_prevents_multiple_active_versions_for_same_metric() -> None:
    database_url = _require_database_url()
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        _set_rls_context(conn, tenant_id="t_metric", project_id="p_metric")
        conn.commit()
        metric_name = "oee_active_unique_violation"
        conn.execute(
            text(
                """
                DELETE FROM metric_lineage
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND metric_name = :metric_name
                """
            ),
            {"tenant_id": "t_metric", "project_id": "p_metric", "metric_name": metric_name},
        )
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
                """
            ),
            {
                "tenant_id": "t_metric",
                "project_id": "p_metric",
                "metric_name": metric_name,
                "lineage_version": "1.0.0",
                "status": "active",
                "formula": "x",
                "source_systems": "[\"MES\"]",
                "owner": "test",
                "is_active": True,
            },
        )
        conn.commit()

        with pytest.raises(IntegrityError):
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
                    "tenant_id": "t_metric",
                    "project_id": "p_metric",
                    "metric_name": metric_name,
                    "lineage_version": "9.9.9",
                    "status": "active",
                    "formula": "x",
                    "source_systems": "[\"MES\"]",
                    "owner": "test",
                    "is_active": True,
                },
            )


def test_invalid_lineage_version_format_is_validation_error() -> None:
    with pytest.raises(ValueError):
        MetricLineageQuery(
            tenantId="t_metric",
            projectId="p_metric",
            metric_name="oee",
            lineageVersion="v1",
        )


def test_rbac_forbidden() -> None:
    query = MetricLineageQuery(
        tenantId="t_metric",
        projectId="p_metric",
        metric_name="oee",
        lineageVersion="1.0.0",
    )

    with pytest.raises(ForbiddenError) as exc_info:
        get_metric_lineage(query, ctx=_ctx(tenant_id="t_metric", project_id="p_metric", capabilities=set()))

    err = exc_info.value
    assert err.code.value == ErrorCode.FORBIDDEN.value
    response = err.to_response()
    assert response.code == ErrorCode.FORBIDDEN.value
    assert response.message.isascii()
    assert response.retryable is False
    assert response.request_id is not None
    dumped = response.model_dump(by_alias=True)
    assert dumped.get("requestId") is not None
