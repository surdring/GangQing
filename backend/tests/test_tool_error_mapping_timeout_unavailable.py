from __future__ import annotations

import os

import pytest
from pydantic import BaseModel, Field

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.tools.base import BaseReadOnlyToolMixin


class _Params(BaseModel):
    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")

    model_config = {"populate_by_name": True}


class _TimeoutTool(BaseReadOnlyToolMixin):
    name = "timeout_tool"
    ParamsModel = _Params
    ResultModel = None
    required_capability = None
    output_contract_source = None

    def run(self, *, ctx: RequestContext, params: BaseModel):
        raise TimeoutError()


class _UnavailableTool(BaseReadOnlyToolMixin):
    name = "unavailable_tool"
    ParamsModel = _Params
    ResultModel = None
    required_capability = None
    output_contract_source = None

    def run(self, *, ctx: RequestContext, params: BaseModel):
        raise ConnectionError("boom")


def test_tool_timeout_is_mapped_to_upstream_timeout_with_allowlisted_details() -> None:
    original = os.environ.get("GANGQING_TOOL_MAX_RETRIES")
    os.environ["GANGQING_TOOL_MAX_RETRIES"] = "0"
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager", stepId="s1")
    tool = _TimeoutTool()

    try:
        with pytest.raises(AppError) as e:
            tool.run_raw(ctx=ctx, raw_params={"timeoutSeconds": 0.2})

        err = e.value
        assert err.code == ErrorCode.UPSTREAM_TIMEOUT
        assert err.retryable is True

        assert isinstance(err.details, dict)
        details = err.details or {}

        assert details.get("toolName") == tool.name
        assert isinstance(details.get("durationMs"), int)
        assert details.get("durationMs") >= 0

        assert details.get("attempt") == 1
        assert details.get("maxAttempts") == 1
        assert details.get("timeoutMs") == 200

        assert set(details.keys()).issubset({"toolName", "durationMs", "attempt", "maxAttempts", "timeoutMs"})
    finally:
        if original is None:
            os.environ.pop("GANGQING_TOOL_MAX_RETRIES", None)
        else:
            os.environ["GANGQING_TOOL_MAX_RETRIES"] = original


def test_tool_unavailable_is_mapped_to_upstream_unavailable_with_retryable_true() -> None:
    original = os.environ.get("GANGQING_TOOL_MAX_RETRIES")
    os.environ["GANGQING_TOOL_MAX_RETRIES"] = "0"
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1", role="plant_manager", stepId="s1")
    tool = _UnavailableTool()

    try:
        with pytest.raises(AppError) as e:
            tool.run_raw(ctx=ctx, raw_params={"timeoutSeconds": 0.2})

        err = e.value
        assert err.code == ErrorCode.UPSTREAM_UNAVAILABLE
        assert err.retryable is True

        assert isinstance(err.details, dict)
        details = err.details or {}

        assert details.get("toolName") == tool.name
        assert details.get("attempt") == 1
        assert details.get("maxAttempts") == 1
        assert details.get("timeoutMs") == 200
        assert set(details.keys()).issubset({"toolName", "durationMs", "attempt", "maxAttempts", "timeoutMs"})
    finally:
        if original is None:
            os.environ.pop("GANGQING_TOOL_MAX_RETRIES", None)
        else:
            os.environ["GANGQING_TOOL_MAX_RETRIES"] = original
