from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, Request

from gangqing.common.context import RequestContext, build_request_context
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.settings import load_settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _hmac_sha256(secret: str, msg: bytes) -> bytes:
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    role: str


def create_access_token(
    *,
    user_id: str,
    role: str,
    tenant_id: str,
    project_id: str,
) -> tuple[str, int]:
    settings = load_settings()
    now = int(time.time())
    exp = now + int(settings.jwt_exp_hours) * 3600

    header = {"alg": settings.jwt_alg, "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "tenantId": tenant_id,
        "projectId": project_id,
        "iat": now,
        "exp": exp,
    }

    header_part = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("utf-8")
    sig = _b64url_encode(_hmac_sha256(settings.jwt_secret, signing_input))
    return f"{header_part}.{payload_part}.{sig}", exp


def _decode_and_verify_token(token: str, *, request_id: str) -> dict[str, Any]:
    settings = load_settings()

    parts = (token or "").split(".")
    if len(parts) != 3:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid token",
            request_id=request_id,
            details={"reason": "invalid_format"},
            retryable=False,
        )

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = _b64url_encode(_hmac_sha256(settings.jwt_secret, signing_input))
    if not hmac.compare_digest(expected_sig, sig_b64):
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid token",
            request_id=request_id,
            details={"reason": "invalid_signature"},
            retryable=False,
        )

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid token",
            request_id=request_id,
            details={"reason": "invalid_encoding"},
            retryable=False,
        )

    if (header.get("alg") or "").upper() != settings.jwt_alg:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid token",
            request_id=request_id,
            details={"reason": "alg_mismatch"},
            retryable=False,
        )

    now = int(time.time())
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid token",
            request_id=request_id,
            details={"reason": "missing_exp"},
            retryable=False,
        )
    if now >= exp:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Token expired",
            request_id=request_id,
            details={"reason": "expired"},
            retryable=False,
        )

    return payload


def require_auth(
    request: Request,
    ctx: RequestContext = Depends(build_request_context),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthContext:
    auth_raw = (authorization or "").strip()
    if not auth_raw:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Missing Authorization header",
            request_id=ctx.request_id,
            details={"header": "Authorization"},
            retryable=False,
        )

    if not auth_raw.lower().startswith("bearer "):
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid Authorization header",
            request_id=ctx.request_id,
            details={"reason": "invalid_scheme"},
            retryable=False,
        )

    token = auth_raw[len("bearer ") :].strip()
    payload = _decode_and_verify_token(token, request_id=ctx.request_id)

    user_id = (payload.get("sub") or "").strip()
    role = (payload.get("role") or "").strip()
    token_tenant_id = (payload.get("tenantId") or "").strip()
    token_project_id = (payload.get("projectId") or "").strip()
    if not user_id or not role:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid token",
            request_id=ctx.request_id,
            details={"reason": "missing_subject"},
            retryable=False,
        )

    if token_tenant_id != ctx.tenant_id or token_project_id != ctx.project_id:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Invalid token scope",
            request_id=ctx.request_id,
            details={"reason": "scope_mismatch"},
            retryable=False,
        )

    request.state.user_id = user_id
    request.state.role = role

    return AuthContext(user_id=user_id, role=role)


def require_authed_request_context(
    request: Request,
    ctx: RequestContext = Depends(build_request_context),
    auth: AuthContext = Depends(require_auth),
) -> RequestContext:
    request.state.user_id = auth.user_id
    request.state.role = auth.role
    return RequestContext(
        requestId=ctx.request_id,
        tenantId=ctx.tenant_id,
        projectId=ctx.project_id,
        sessionId=ctx.session_id,
        userId=auth.user_id,
        role=auth.role,
        taskId=ctx.task_id,
        stepId=ctx.step_id,
    )
