from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.auth import create_access_token
from gangqing.common.context import RequestContext, build_request_context
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.settings import load_settings


router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="Bearer", alias="tokenType")
    expires_at: int = Field(alias="expiresAt")

    model_config = {"populate_by_name": True}


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    ctx: RequestContext = Depends(build_request_context),
) -> LoginResponse:
    settings = load_settings()
    username = payload.username.strip()

    candidates: list[tuple[str, str, str]] = []
    if settings.bootstrap_admin_user_id and settings.bootstrap_admin_password:
        candidates.append(
            (
                settings.bootstrap_admin_user_id,
                settings.bootstrap_admin_password,
                "admin",
            )
        )
    if settings.bootstrap_finance_user_id and settings.bootstrap_finance_password:
        candidates.append(
            (
                settings.bootstrap_finance_user_id,
                settings.bootstrap_finance_password,
                "finance",
            )
        )

    matched_role: str | None = None
    for user_id, password, role in candidates:
        if username == user_id and payload.password == password:
            matched_role = role
            break

    if not matched_role:
        write_audit_event(
            ctx=ctx,
            event_type=AuditEventType.LOGIN_FAILURE.value,
            resource="auth.login",
            action_summary={"username": username},
            result_status="failure",
            error_code=ErrorCode.AUTH_ERROR.value,
        )
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid credentials",
            request_id=ctx.request_id,
            details={"reason": "invalid_credentials"},
            retryable=False,
        )

    token, exp = create_access_token(
        user_id=username,
        role=matched_role,
        tenant_id=ctx.tenant_id,
        project_id=ctx.project_id,
    )

    write_audit_event(
        ctx=ctx,
        event_type=AuditEventType.LOGIN_SUCCESS.value,
        resource="auth.login",
        action_summary={"userId": username, "role": matched_role},
        result_status="success",
        error_code=None,
    )

    return LoginResponse(access_token=token, expires_at=exp)
