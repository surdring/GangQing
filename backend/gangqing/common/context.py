from __future__ import annotations

import uuid

from fastapi import Header
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from gangqing.common.errors import AppError, ErrorCode


class RequestContext(BaseModel):
    request_id: str = Field(alias="requestId")
    tenant_id: str = Field(alias="tenantId")
    project_id: str = Field(alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    user_id: str | None = Field(default=None, alias="userId")
    role: str | None = Field(default=None)
    task_id: str | None = Field(default=None, alias="taskId")
    step_id: str | None = Field(default=None, alias="stepId")

    model_config = {"populate_by_name": True}


def build_request_context(
    request: Request,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_role: str | None = Header(default=None, alias="X-Role"),
    x_task_id: str | None = Header(default=None, alias="X-Task-Id"),
    x_step_id: str | None = Header(default=None, alias="X-Step-Id"),
) -> RequestContext:
    """Build RequestContext from request.state and HTTP headers.

    Required headers:
    - X-Tenant-Id
    - X-Project-Id

    Optional headers:
    - X-Request-Id
    - X-Session-Id / X-User-Id / X-Role
    - X-Task-Id / X-Step-Id

    Raises:
    - AppError(AUTH_ERROR) when required scope headers are missing.
    """
    request_id_from_state = getattr(getattr(request, "state", None), "request_id", None)
    request_id = (
        (request_id_from_state or "").strip()
        or (x_request_id or "").strip()
        or uuid.uuid4().hex
    )

    tenant_id_from_state = getattr(getattr(request, "state", None), "tenant_id", None)
    tenant_id = ((tenant_id_from_state or "").strip() or (x_tenant_id or "").strip())
    if not tenant_id:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Missing required header: X-Tenant-Id",
            request_id=request_id,
            details={"header": "X-Tenant-Id"},
            retryable=False,
        )

    project_id_from_state = getattr(getattr(request, "state", None), "project_id", None)
    project_id = ((project_id_from_state or "").strip() or (x_project_id or "").strip())
    if not project_id:
        raise AppError(
            ErrorCode.AUTH_ERROR,
            "Missing required header: X-Project-Id",
            request_id=request_id,
            details={"header": "X-Project-Id"},
            retryable=False,
        )

    session_id_from_state = getattr(getattr(request, "state", None), "session_id", None)
    session_id = ((session_id_from_state or "").strip() or (x_session_id or "").strip()) or None

    user_id_from_state = getattr(getattr(request, "state", None), "user_id", None)
    user_id = ((user_id_from_state or "").strip() or (x_user_id or "").strip()) or None

    role_from_state = getattr(getattr(request, "state", None), "role", None)
    role = ((role_from_state or "").strip() or (x_role or "").strip()) or None

    task_id_from_state = getattr(getattr(request, "state", None), "task_id", None)
    task_id = ((task_id_from_state or "").strip() or (x_task_id or "").strip()) or None

    step_id_from_state = getattr(getattr(request, "state", None), "step_id", None)
    step_id = ((step_id_from_state or "").strip() or (x_step_id or "").strip()) or None

    return RequestContext(
        request_id=request_id,
        tenant_id=tenant_id,
        project_id=project_id,
        session_id=session_id,
        user_id=user_id,
        role=role,
        task_id=task_id,
        step_id=step_id,
    )
