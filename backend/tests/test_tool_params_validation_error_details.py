from __future__ import annotations

import json
import os

import pytest
from pydantic import BaseModel

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.tools.base import BaseReadOnlyToolMixin


class _Params(BaseModel):
    a: int
    b: int
    c: int


class _DummyTool(BaseReadOnlyToolMixin):
    name = "dummy_tool"
    ParamsModel = _Params
    ResultModel = None
    required_capability = None
    output_contract_source = None

    def run(self, *, ctx: RequestContext, params: BaseModel):
        return {"ok": True}


def test_validation_error_details_are_summarized_and_truncated() -> None:
    original_max_errors = os.environ.get("GANGQING_CONTRACT_VALIDATION_MAX_ERRORS")
    os.environ["GANGQING_CONTRACT_VALIDATION_MAX_ERRORS"] = "1"
    try:
        ctx = RequestContext(requestId="r_test", tenantId="t1", projectId="p1", role="plant_manager")
        tool = _DummyTool()

        raw_params = {
            "a": "not-an-int",
            "secretToken": "should-not-leak",
        }

        with pytest.raises(AppError) as e:
            tool.run_raw(ctx=ctx, raw_params=raw_params)

        err = e.value
        assert err.code == ErrorCode.VALIDATION_ERROR
        assert err.request_id == "r_test"
        assert err.message == "Invalid tool parameters"
        assert err.retryable is False

        assert isinstance(err.details, dict)
        details = err.details or {}
        assert details.get("stage") == "tool.params.validate"
        assert details.get("toolName") == tool.name

        field_errors = details.get("fieldErrors")
        assert isinstance(field_errors, list)
        assert len(field_errors) == 1
        first = field_errors[0]
        assert isinstance(first, dict)
        assert isinstance(first.get("path"), str)
        assert isinstance(first.get("reason"), str)
        assert isinstance(first.get("error_type"), str)

        raw_details = json.dumps(details, ensure_ascii=False, sort_keys=True).lower()
        assert "should-not-leak" not in raw_details
        assert "secrettoken" not in raw_details
    finally:
        if original_max_errors is None:
            os.environ.pop("GANGQING_CONTRACT_VALIDATION_MAX_ERRORS", None)
        else:
            os.environ["GANGQING_CONTRACT_VALIDATION_MAX_ERRORS"] = original_max_errors
