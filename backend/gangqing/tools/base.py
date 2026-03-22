from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from gangqing.common.context import RequestContext
from gangqing.tools.runner import RetryEvent, run_readonly_tool


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

    def run_raw(
        self,
        *,
        ctx: RequestContext,
        raw_params: dict[str, Any],
        retry_observer=None,
        should_cancel=None,
    ):
        return run_readonly_tool(
            tool=self,
            ctx=ctx,
            raw_params=raw_params,
            retry_observer=retry_observer,
            should_cancel=should_cancel,
        )
