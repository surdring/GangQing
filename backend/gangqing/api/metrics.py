from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gangqing.common.context import RequestContext, build_request_context
from gangqing.common.metrics import METRICS


router = APIRouter()


class MetricsResponse(BaseModel):
    http: dict


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(_: RequestContext = Depends(build_request_context)) -> MetricsResponse:
    return MetricsResponse(**METRICS.snapshot())
