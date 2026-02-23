from __future__ import annotations

from gangqing.common.context import RequestContext
from gangqing.common.rbac import assert_has_capability


def require_tool_capability(*, ctx: RequestContext, capability: str) -> None:
    role_raw = (ctx.role or "").strip()
    assert_has_capability(ctx=ctx, role_raw=role_raw, capability=capability)
