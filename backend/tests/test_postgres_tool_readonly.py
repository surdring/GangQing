from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.context import RequestContext
from gangqing.tools.postgres_readonly import (
    PostgresReadOnlyQueryParams,
    PostgresReadOnlyQueryTool,
    _assert_select_only_sql,
)
from gangqing_db.errors import UpstreamTimeoutError


def _make_timerange() -> dict:
    return {
        "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
        "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
    }


def test_reject_non_select_sql() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1")
    with pytest.raises(AppError) as e:
        _assert_select_only_sql(sql="UPDATE x SET y=1", ctx=ctx)
    assert e.value.code == ErrorCode.CONTRACT_VIOLATION
    assert "SELECT" in e.value.message


def test_reject_multi_statement_sql() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1")
    with pytest.raises(AppError) as e:
        _assert_select_only_sql(sql="SELECT 1; SELECT 2", ctx=ctx)
    assert e.value.code == ErrorCode.CONTRACT_VIOLATION


def test_missing_scope_in_ctx_raises_auth_error() -> None:
    ctx = RequestContext(requestId="r1", tenantId="", projectId="", role="plant_manager")

    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])
    params = PostgresReadOnlyQueryParams(templateId="production_daily", timeRange=_make_timerange())

    with pytest.raises(AppError) as e:
        tool.run(ctx=ctx, params=params)
    assert e.value.code == ErrorCode.AUTH_ERROR


def test_evidence_has_required_fields_and_no_secret_leakage() -> None:
    captured: list[dict] = []

    def _capture_audit(*, ctx, tool_name, args_summary, result_status, error_code=None, evidence_refs=None):
        captured.append(
            {
                "tool_name": tool_name,
                "args_summary": args_summary,
                "result_status": result_status,
                "error_code": error_code,
                "evidence_refs": evidence_refs,
            }
        )

    def _return_rows(**_):
        return [
            {
                "tenant_id": "t1",
                "project_id": "p1",
                "business_date": datetime(2026, 2, 1, tzinfo=timezone.utc).date(),
                "equipment_id": None,
                "quantity": 1,
                "unit": "kg",
                "source_system": "test",
                "source_record_id": "r1",
                "time_start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "time_end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                "extracted_at": datetime(2026, 2, 2, tzinfo=timezone.utc),
            }
        ]

    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")
    tool = PostgresReadOnlyQueryTool(execute_fn=_return_rows, audit_fn=_capture_audit)
    params = PostgresReadOnlyQueryParams(templateId="production_daily", timeRange=_make_timerange())

    result = tool.run(ctx=ctx, params=params)

    locator = result.evidence.source_locator
    assert locator.get("tableOrView") == "fact_production_daily"
    assert locator.get("queryFingerprint")
    assert locator.get("filters") is not None
    assert locator.get("extractedAt")
    assert result.evidence.time_range.start == params.time_range.start
    assert result.evidence.time_range.end == params.time_range.end
    assert result.evidence.confidence == "High"
    assert result.evidence.validation == "verifiable"

    filters = locator.get("filters")
    assert isinstance(filters, list)
    if filters:
        assert "value" in filters[0]
        assert isinstance(filters[0]["value"], dict)
        assert "type" in filters[0]["value"]

    locator_str = json.dumps(locator, ensure_ascii=False, sort_keys=True)
    assert "postgresql://" not in locator_str
    assert "psycopg://" not in locator_str
    assert "SELECT" not in locator_str

    assert captured
    success_events = [e for e in captured if e["result_status"] == "success"]
    assert success_events
    args_summary = success_events[-1]["args_summary"]
    assert isinstance(args_summary.get("durationMs"), int)
    assert args_summary.get("templateId") == "production_daily"
    assert args_summary.get("queryFingerprint")
    assert isinstance(success_events[-1]["evidence_refs"], list)


def test_params_boundaries_limit_and_offset() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")

    def _return_rows(**_):
        return [
            {
                "tenant_id": "t1",
                "project_id": "p1",
                "business_date": datetime(2026, 2, 1, tzinfo=timezone.utc).date(),
                "equipment_id": None,
                "quantity": 1,
                "unit": "kg",
                "source_system": "test",
                "source_record_id": "r1",
                "time_start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "time_end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                "extracted_at": datetime(2026, 2, 2, tzinfo=timezone.utc),
            }
        ]

    tool = PostgresReadOnlyQueryTool(execute_fn=_return_rows)

    params_min = PostgresReadOnlyQueryParams(
        templateId="production_daily",
        timeRange=_make_timerange(),
        limit=1,
        offset=0,
        filters=[],
        orderBy=[],
    )
    tool.run(ctx=ctx, params=params_min)

    params_max = PostgresReadOnlyQueryParams(
        templateId="production_daily",
        timeRange=_make_timerange(),
        limit=1000,
        offset=100000,
        filters=[],
        orderBy=[],
    )
    tool.run(ctx=ctx, params=params_max)


def test_time_range_start_equals_end_is_validation_error() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")
    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])

    with pytest.raises(Exception):
        PostgresReadOnlyQueryParams(
            templateId="production_daily",
            timeRange={
                "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "end": datetime(2026, 2, 1, tzinfo=timezone.utc),
            },
        )


def test_invalid_template_id_is_validation_error() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")
    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])

    params = PostgresReadOnlyQueryParams(templateId="unknown_template", timeRange=_make_timerange())
    with pytest.raises(Exception):
        tool.run(ctx=ctx, params=params)


def test_forbidden_when_role_missing() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role=None)
    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])
    params = PostgresReadOnlyQueryParams(templateId="production_daily", timeRange=_make_timerange())

    with pytest.raises(AppError) as e:
        tool.run(ctx=ctx, params=params)
    assert e.value.code == ErrorCode.FORBIDDEN


def test_timeout_is_mapped_to_upstream_timeout() -> None:
    def _raise_timeout(**_):
        raise UpstreamTimeoutError("Postgres", cause="timeout", request_id="r1")

    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")
    tool = PostgresReadOnlyQueryTool(execute_fn=_raise_timeout)
    params = PostgresReadOnlyQueryParams(templateId="production_daily", timeRange=_make_timerange())

    with pytest.raises(AppError) as e:
        tool.run(ctx=ctx, params=params)
    assert e.value.code == ErrorCode.UPSTREAM_TIMEOUT
    assert e.value.retryable is True


def test_explicit_scope_mismatch_is_auth_error() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")

    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])
    params = PostgresReadOnlyQueryParams(
        tenantId="t2",
        projectId="p2",
        templateId="production_daily",
        timeRange=_make_timerange(),
    )

    with pytest.raises(AppError) as e:
        tool.run(ctx=ctx, params=params)
    assert e.value.code == ErrorCode.AUTH_ERROR


def test_cross_scope_data_hit_is_auth_error() -> None:
    def _return_cross_scope_rows(**_):
        return [
            {
                "tenant_id": "t_other",
                "project_id": "p_other",
                "business_date": datetime(2026, 2, 1, tzinfo=timezone.utc).date(),
                "equipment_id": None,
                "quantity": 1,
                "unit": "kg",
                "source_system": "test",
                "source_record_id": "r1",
                "time_start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "time_end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                "extracted_at": datetime(2026, 2, 2, tzinfo=timezone.utc),
            }
        ]

    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")
    tool = PostgresReadOnlyQueryTool(execute_fn=_return_cross_scope_rows)
    params = PostgresReadOnlyQueryParams(templateId="production_daily", timeRange=_make_timerange())

    with pytest.raises(AppError) as e:
        tool.run(ctx=ctx, params=params)
    assert e.value.code == ErrorCode.AUTH_ERROR
