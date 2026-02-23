from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from gangqing.common.context import RequestContext


TParams = TypeVar("TParams", bound=BaseModel)
TResult = TypeVar("TResult")


class ReadOnlyTool(Protocol[TParams, TResult]):
    name: str

    def run(self, *, ctx: RequestContext, params: TParams) -> TResult: ...
