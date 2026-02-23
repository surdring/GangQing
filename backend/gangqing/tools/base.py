from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import ValidationError
from pydantic import BaseModel

from gangqing.common.audit import write_tool_call_event
from gangqing.common.context import RequestContext
from gangqing.common.errors import build_validation_error


TParams = TypeVar("TParams", bound=BaseModel)
TResult = TypeVar("TResult")


class ReadOnlyTool(Protocol[TParams, TResult]):
    name: str

    def run(self, *, ctx: RequestContext, params: TParams) -> TResult: ...


class BaseReadOnlyToolMixin:
    name: str
    ParamsModel: type[BaseModel]

    def run(self, *, ctx: RequestContext, params: BaseModel):
        raise NotImplementedError("Tool must implement run")

    def run_raw(self, *, ctx: RequestContext, raw_params: dict[str, Any]):
        try:
            params = self.ParamsModel.model_validate(raw_params)
        except ValidationError as e:
            err = build_validation_error(request_id=ctx.request_id, error=e)

            audit_fn = getattr(self, "_audit_fn", None) or write_tool_call_event
            audit_fn(
                ctx=ctx,
                tool_name=self.name,
                args_summary={"stage": "tool.params.validate"},
                result_status="failure",
                error_code=err.code.value,
            )
            raise err

        return self.run(ctx=ctx, params=params)
