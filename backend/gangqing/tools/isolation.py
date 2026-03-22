from __future__ import annotations

from typing import Any
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.metrics import METRICS


SCOPE_POLICY_VERSION = "v1"


def build_scope_filter_summary(
    *,
    tenant_id: str | None,
    project_id: str | None,
    mode: str,
    policy_version: str = SCOPE_POLICY_VERSION,
) -> dict[str, Any]:
    return {
        "tenantId": tenant_id,
        "projectId": project_id,
        "mode": mode,
        "policyVersion": policy_version,
    }


def resolve_scope(
    *,
    ctx: Any,
    tenant_id: str | None,
    project_id: str | None,
) -> tuple[str, str, str]:
    """Resolve effective scope for data access.

    Rules:
    - If caller provides any scope param, it must provide both and must match ctx (no escapes).
    - Otherwise, inject ctx scope (default filtering).
    """

    if tenant_id is not None or project_id is not None:
        if not tenant_id or not project_id:
            METRICS.inc_isolation_failure(reason="partial_scope_params")
            raise AppError(
                ErrorCode.AUTH_ERROR,
                "Authentication context missing tenantId/projectId",
                request_id=getattr(ctx, "request_id", None),
                details={"reason": "partial_scope_params"},
                retryable=False,
            )
        if tenant_id != getattr(ctx, "tenant_id", None) or project_id != getattr(ctx, "project_id", None):
            METRICS.inc_isolation_failure(reason="cross_scope")
            raise AppError(
                ErrorCode.AUTH_ERROR,
                "Cross-scope access is not allowed",
                request_id=getattr(ctx, "request_id", None),
                details={
                    "tenantId": tenant_id,
                    "projectId": project_id,
                },
                retryable=False,
            )
        return tenant_id, project_id, "explicit_validated"

    if not getattr(ctx, "tenant_id", None) or not getattr(ctx, "project_id", None):
        METRICS.inc_isolation_failure(reason="missing_scope")
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Authentication context missing tenantId/projectId",
            request_id=getattr(ctx, "request_id", None),
            details=None,
            retryable=False,
        )
    return getattr(ctx, "tenant_id"), getattr(ctx, "project_id"), "default_injected"


def build_scope_where_sql(
    *,
    tenant_id: str,
    project_id: str,
    tenant_field: str = "tenant_id",
    project_field: str = "project_id",
    tenant_param: str = "tenant_id",
    project_param: str = "project_id",
) -> tuple[str, dict[str, Any]]:
    where_sql = f"{tenant_field} = :{tenant_param} AND {project_field} = :{project_param}"
    return where_sql, {tenant_param: tenant_id, project_param: project_id}


def require_rows_in_scope(
    *,
    ctx: Any,
    rows: list[dict[str, Any]],
    tenant_key: str = "tenant_id",
    project_key: str = "project_id",
) -> None:
    """Detect cross-scope data hit before returning results."""

    for row in rows:
        t = row.get(tenant_key)
        p = row.get(project_key)
        if t is None or p is None:
            continue
        if str(t) != str(getattr(ctx, "tenant_id", "")) or str(p) != str(getattr(ctx, "project_id", "")):
            METRICS.inc_isolation_failure(reason="cross_scope_data_hit")
            raise AppError(
                ErrorCode.AUTH_ERROR,
                "Cross-scope data hit is not allowed",
                request_id=getattr(ctx, "request_id", None),
                details=None,
                retryable=False,
            )


def require_same_scope(
    *,
    ctx: Any,
    tenant_id: str | None,
    project_id: str | None,
) -> None:
    if not tenant_id or not project_id:
        METRICS.inc_isolation_failure(reason="missing_scope")
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Authentication context missing tenantId/projectId",
            request_id=getattr(ctx, "request_id", None),
            details=None,
            retryable=False,
        )

    if tenant_id != getattr(ctx, "tenant_id", None) or project_id != getattr(ctx, "project_id", None):
        METRICS.inc_isolation_failure(reason="cross_scope")
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Cross-scope access is not allowed",
            request_id=getattr(ctx, "request_id", None),
            details={
                "tenantId": tenant_id,
                "projectId": project_id,
            },
            retryable=False,
        )


def require_params_scope(*, ctx: Any, params: Any) -> None:
    tenant_id = getattr(params, "tenant_id", None)
    project_id = getattr(params, "project_id", None)
    require_same_scope(ctx=ctx, tenant_id=tenant_id, project_id=project_id)
