from __future__ import annotations

import json
import os
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


def test_partial_scope_params_is_auth_error() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")

    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])
    params = PostgresReadOnlyQueryParams(
        tenantId="t1",
        projectId=None,
        templateId="production_daily",
        timeRange=_make_timerange(),
    )

    with pytest.raises(AppError) as e:
        tool.run(ctx=ctx, params=params)
    assert e.value.code == ErrorCode.AUTH_ERROR


def test_slow_template_does_not_expose_sleep_field() -> None:
    def _return_rows(**_):
        return [
            {
                "tenant_id": "t1",
                "project_id": "p1",
                "__sleep": None,
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
    tool = PostgresReadOnlyQueryTool(execute_fn=_return_rows)
    params = PostgresReadOnlyQueryParams(templateId="production_daily_slow", timeRange=_make_timerange())

    result = tool.run(ctx=ctx, params=params)
    assert result.row_count == 1
    assert result.rows
    assert "__sleep" not in result.rows[0]
    assert result.evidence.evidence_id


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


def test_evidence_source_locator_is_masked_by_default() -> None:
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
    tool = PostgresReadOnlyQueryTool(execute_fn=_return_rows)
    params = PostgresReadOnlyQueryParams(templateId="production_daily", timeRange=_make_timerange())

    result = tool.run(ctx=ctx, params=params)
    locator = result.evidence.source_locator
    assert locator.get("filters") is not None
    filters = locator.get("filters")
    assert isinstance(filters, list)
    locator_str = json.dumps(locator, ensure_ascii=False, sort_keys=True)
    assert "unit_cost" not in locator_str
    assert "12.34" not in locator_str
    if result.evidence.redactions is not None:
        assert isinstance(result.evidence.redactions, dict)
        masking = (result.evidence.redactions or {}).get("masking")
        assert isinstance(masking, dict)
        assert masking.get("policyId")
        assert masking.get("version")
        assert isinstance(masking.get("maskedKeys"), list)


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

    with pytest.raises(AppError) as e:
        tool.run_raw(
            ctx=ctx,
            raw_params={
                "templateId": "production_daily",
                "timeRange": {
                    "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                    "end": datetime(2026, 2, 1, tzinfo=timezone.utc),
                },
            },
        )
    assert e.value.code == ErrorCode.VALIDATION_ERROR
    assert e.value.request_id == "r1"
    assert isinstance(e.value.message, str)
    assert e.value.message == "Invalid tool parameters"
    assert e.value.retryable is False
    assert isinstance(e.value.details, dict)
    assert "fieldErrors" in (e.value.details or {})


def test_run_raw_validation_failure_writes_audit_event() -> None:
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

    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")
    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [], audit_fn=_capture_audit)

    with pytest.raises(AppError) as e:
        tool.run_raw(ctx=ctx, raw_params={"templateId": "production_daily"})

    assert e.value.code == ErrorCode.VALIDATION_ERROR

    assert captured
    last = captured[-1]
    assert last["tool_name"] == tool.name
    assert last["result_status"] == "failure"
    assert last["error_code"] == ErrorCode.VALIDATION_ERROR.value
    assert isinstance(last["args_summary"], dict)
    assert last["args_summary"].get("stage") == "tool.params.validate"
    assert e.value.message == "Invalid tool parameters"
    assert isinstance(e.value.details, dict)
    assert "fieldErrors" in (e.value.details or {})


def test_invalid_template_id_is_validation_error() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager")
    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])

    params = PostgresReadOnlyQueryParams(templateId="unknown_template", timeRange=_make_timerange())
    with pytest.raises(AppError) as e:
        tool.run(ctx=ctx, params=params)
    assert e.value.code == ErrorCode.VALIDATION_ERROR
    assert e.value.request_id == "r1"
    assert isinstance(e.value.message, str)


def test_forbidden_when_role_missing() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role=None)
    tool = PostgresReadOnlyQueryTool(execute_fn=lambda **_: [])

    with pytest.raises(AppError) as e:
        tool.run_raw(
            ctx=ctx,
            raw_params={
                "templateId": "production_daily",
                "timeRange": {
                    "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                    "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                },
            },
        )
    assert e.value.code == ErrorCode.FORBIDDEN


def test_run_direct_call_enforces_capability() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="dispatcher")
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


def test_output_contract_violation_is_mapped_to_contract_violation() -> None:
    original = os.environ.get("GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION")
    os.environ["GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION"] = "1"
    try:
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
        tool = PostgresReadOnlyQueryTool(execute_fn=_return_rows)

        with pytest.raises(AppError) as e:
            tool.run_raw(
                ctx=ctx,
                raw_params={
                    "templateId": "production_daily",
                    "timeRange": {
                        "start": datetime(2026, 2, 1, tzinfo=timezone.utc),
                        "end": datetime(2026, 2, 2, tzinfo=timezone.utc),
                    },
                },
            )

        assert e.value.code == ErrorCode.CONTRACT_VIOLATION
        assert e.value.request_id == "r1"
        assert isinstance(e.value.message, str)
        assert e.value.message == "Output contract violation"
        assert e.value.retryable is False
        assert isinstance(e.value.details, dict)
        assert e.value.details.get("source") == "tool.postgres_readonly.result"
        assert e.value.details.get("stage") == "tool.output.validate"
        assert e.value.details.get("toolName") == "postgres_readonly_query"
        assert "fieldErrors" in (e.value.details or {})
        field_errors = (e.value.details or {}).get("fieldErrors")
        assert isinstance(field_errors, list)
        assert field_errors
        assert isinstance(field_errors[0], dict)
        assert isinstance(field_errors[0].get("error_type"), str)
    finally:
        if original is None:
            os.environ.pop("GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION", None)
        else:
            os.environ["GANGQING_FORCE_POSTGRES_TOOL_OUTPUT_CONTRACT_VIOLATION"] = original


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
