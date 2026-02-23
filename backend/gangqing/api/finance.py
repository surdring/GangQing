from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gangqing.common.auth import require_authed_request_context
from gangqing.common.context import RequestContext
from gangqing.common.rbac import require_capability


router = APIRouter()


class FinanceReportSummaryResponse(BaseModel):
    currency: str = Field(default="CNY")
    total_cost: float = Field(alias="totalCost")

    model_config = {"populate_by_name": True}


@router.get("/finance/reports/summary", response_model=FinanceReportSummaryResponse)
def get_finance_report_summary(
    ctx: RequestContext = Depends(require_authed_request_context),
    _: RequestContext = Depends(require_capability("finance:report:read")),
) -> FinanceReportSummaryResponse:
    return FinanceReportSummaryResponse(total_cost=0.0)
