from __future__ import annotations

from enum import Enum

from fastapi import Depends
from fastapi import Request

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext, build_request_context
from gangqing.common.errors import AppError, ErrorCode


class Role(str, Enum):
    ADMIN = "admin"
    AUDITOR = "auditor"
    PLANT_MANAGER = "plant_manager"
    DISPATCHER = "dispatcher"
    MAINTAINER = "maintainer"
    FINANCE = "finance"


_ROLE_TO_CAPABILITIES: dict[Role, set[str]] = {
    Role.ADMIN: {
        "chat:conversation:stream",
        "audit:event:read",
        "evidence:chain:read",
        "finance:report:read",
        "tool:demo:run",
        "tool:postgres:read",
        "metric:lineage:read",
        "semantic:mapping:read",
        "semantic:mapping:write",
        "semantic:mapping:conflict:read",
    },
    Role.AUDITOR: {
        "audit:event:read",
        "semantic:mapping:read",
        "semantic:mapping:conflict:read",
    },
    Role.PLANT_MANAGER: {
        "chat:conversation:stream",
        "evidence:chain:read",
        "finance:report:read",
        "tool:demo:run",
        "tool:postgres:read",
        "metric:lineage:read",
        "semantic:mapping:read",
    },
    Role.DISPATCHER: {
        "chat:conversation:stream",
        "semantic:mapping:read",
    },
    Role.MAINTAINER: {
        "chat:conversation:stream",
        "semantic:mapping:read",
    },
    Role.FINANCE: {
        "evidence:chain:read",
        "data:unmask:read",
        "finance:report:read",
        "semantic:mapping:read",
    },
}


def _is_valid_capability_name(capability: str) -> bool:
    parts = [p for p in (capability or "").split(":") if p]
    return len(parts) == 3


def assert_has_capability(*, ctx: RequestContext, role_raw: str, capability: str) -> None:
    if not _is_valid_capability_name(capability):
        raise AppError(
            ErrorCode.CONTRACT_VIOLATION,
            "Invalid capability name",
            request_id=ctx.request_id,
            details={"capability": capability},
            retryable=False,
        )

    if not role_raw:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Forbidden",
            request_id=ctx.request_id,
            details={"capability": capability, "reason": "missing_role"},
            retryable=False,
        )

    try:
        role = Role(role_raw)
    except Exception:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Forbidden",
            request_id=ctx.request_id,
            details={"capability": capability, "reason": "invalid_role"},
            retryable=False,
        )

    caps = _ROLE_TO_CAPABILITIES.get(role, set())
    if capability not in caps:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Forbidden",
            request_id=ctx.request_id,
            details={"capability": capability, "role": role.value},
            retryable=False,
        )


def has_capability(*, role_raw: str, capability: str) -> bool:
    if not _is_valid_capability_name(capability):
        return False
    if not role_raw:
        return False
    try:
        role = Role(role_raw)
    except Exception:
        return False
    caps = _ROLE_TO_CAPABILITIES.get(role, set())
    return capability in caps


def require_capability(capability: str):
    def _dep(
        request: Request,
        ctx: RequestContext = Depends(build_request_context),
    ) -> RequestContext:
        role_raw = (getattr(request.state, "role", None) or ctx.role or "").strip()
        try:
            assert_has_capability(ctx=ctx, role_raw=role_raw, capability=capability)
        except AppError as e:
            if e.code == ErrorCode.FORBIDDEN:
                write_audit_event(
                    ctx=ctx,
                    event_type=AuditEventType.RBAC_DENIED.value,
                    resource=str(getattr(getattr(request, "url", None), "path", None) or "http"),
                    action_summary={
                        "capability": capability,
                        "role": role_raw or None,
                        "details": e.details,
                    },
                    result_status="failure",
                    error_code=e.code.value,
                )
            raise

        return ctx

    return _dep
