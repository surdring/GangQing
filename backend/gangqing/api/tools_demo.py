from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gangqing.common.audit import write_tool_call_event
from gangqing.common.auth import require_authed_request_context
from gangqing.common.context import RequestContext
from gangqing.common.rbac import require_capability
from gangqing.tools import require_tool_capability


router = APIRouter()


class DemoToolRequest(BaseModel):
    query: str = Field(min_length=1)


class DemoToolResponse(BaseModel):
    result: str


@router.post("/tools/demo", response_model=DemoToolResponse)
def run_demo_tool(
    payload: DemoToolRequest,
    ctx: RequestContext = Depends(require_authed_request_context),
    _: RequestContext = Depends(require_capability("tool:demo:run")),
) -> DemoToolResponse:
    require_tool_capability(ctx=ctx, capability="tool:demo:run", tool_name="demo_tool")

    write_tool_call_event(
        ctx=ctx,
        tool_name="demo_tool",
        tool_call_id=None,
        duration_ms=None,
        args_summary={"query": payload.query},
        result_status="success",
        error_code=None,
    )

    return DemoToolResponse(result=f"echo:{payload.query}")
