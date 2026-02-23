from __future__ import annotations

import time
import uuid

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from gangqing.api.router import create_api_router
from gangqing.common.audit import write_audit_event
from gangqing.common.audit_event_types import AuditEventType
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode, ErrorResponse
from gangqing.common.logging import configure_logging
from gangqing.common.metrics import METRICS
from gangqing.common.settings import load_settings


logger = structlog.get_logger(__name__)


ERROR_CODE_TO_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.AUTH_ERROR: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UPSTREAM_TIMEOUT: 504,
    ErrorCode.UPSTREAM_UNAVAILABLE: 503,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
}


def _build_audit_ctx_from_request_state(request: Request) -> RequestContext:
    request_id = (getattr(request.state, "request_id", None) or "").strip() or uuid.uuid4().hex
    tenant_id = (getattr(request.state, "tenant_id", None) or "").strip() or "unknown"
    project_id = (getattr(request.state, "project_id", None) or "").strip() or "unknown"
    session_id = (getattr(request.state, "session_id", None) or "").strip() or None
    user_id = (getattr(request.state, "user_id", None) or "").strip() or None
    role = (getattr(request.state, "role", None) or "").strip() or None
    task_id = (getattr(request.state, "task_id", None) or "").strip() or None
    step_id = (getattr(request.state, "step_id", None) or "").strip() or None
    return RequestContext(
        requestId=request_id,
        tenantId=tenant_id,
        projectId=project_id,
        sessionId=session_id,
        userId=user_id,
        role=role,
        taskId=task_id,
        stepId=step_id,
    )


def create_app() -> FastAPI:
    settings = load_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    app = FastAPI(title="GangQing API")

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        started = time.perf_counter()
        request_id = (request.headers.get("X-Request-Id") or "").strip() or uuid.uuid4().hex
        request.state.request_id = request_id

        tenant_id = (request.headers.get("X-Tenant-Id") or "").strip() or None
        project_id = (request.headers.get("X-Project-Id") or "").strip() or None
        session_id = (request.headers.get("X-Session-Id") or "").strip() or None
        user_id = (request.headers.get("X-User-Id") or "").strip() or None
        role = (request.headers.get("X-Role") or "").strip() or None
        task_id = (request.headers.get("X-Task-Id") or "").strip() or None
        step_id = (request.headers.get("X-Step-Id") or "").strip() or None
        request.state.tenant_id = tenant_id
        request.state.project_id = project_id
        request.state.session_id = session_id
        request.state.user_id = user_id
        request.state.role = role
        request.state.task_id = task_id
        request.state.step_id = step_id
        bind_contextvars(
            requestId=request_id,
            tenantId=tenant_id,
            projectId=project_id,
            sessionId=session_id,
            userId=user_id,
            role=role,
            taskId=task_id,
            stepId=step_id,
        )

        response = None
        err: Exception | None = None
        try:
            response = await call_next(request)
        except Exception as e:
            err = e
            raise
        finally:
            if response is not None:
                ctx = _build_audit_ctx_from_request_state(request)
                error_code = getattr(request.state, "error_code", None)
                write_audit_event(
                    ctx=ctx,
                    event_type=AuditEventType.API_RESPONSE.value,
                    resource=str(getattr(getattr(request, "url", None), "path", None) or "http"),
                    action_summary={
                        "method": request.method,
                        "path": request.url.path,
                        "statusCode": getattr(response, "status_code", None),
                        "durationMs": round((time.perf_counter() - started) * 1000.0, 3),
                    },
                    result_status="success" if int(getattr(response, "status_code", 500) or 500) < 400 else "failure",
                    error_code=str(error_code) if error_code else None,
                )

            METRICS.observe_http_request(
                method=request.method,
                path=request.url.path,
                status_code=getattr(response, "status_code", None),
                duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
            )
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=getattr(response, "status_code", None),
                duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
                error=err.__class__.__name__ if err is not None else None,
            )
            clear_contextvars()

        if response is not None:
            response.headers.setdefault("X-Request-Id", request_id)
        return response

    app.include_router(create_api_router())

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request.state.error_code = exc.code.value
        ctx = _build_audit_ctx_from_request_state(request)
        if exc.code == ErrorCode.AUTH_ERROR:
            write_audit_event(
                ctx=ctx,
                event_type=AuditEventType.AUTH_DENIED.value,
                resource=str(getattr(getattr(request, "url", None), "path", None) or "http"),
                action_summary={
                    "method": request.method,
                    "path": request.url.path,
                    "details": exc.details,
                },
                result_status="failure",
                error_code=exc.code.value,
            )

        write_audit_event(
            ctx=ctx,
            event_type=AuditEventType.API_RESPONSE.value,
            resource=str(getattr(getattr(request, "url", None), "path", None) or "http"),
            action_summary={
                "method": request.method,
                "path": request.url.path,
                "statusCode": _map_status_code(exc.code),
            },
            result_status="failure",
            error_code=exc.code.value,
        )
        resp_obj = exc.to_response()
        resp = resp_obj.model_dump(by_alias=True)
        return JSONResponse(
            status_code=_map_status_code(exc.code),
            content=resp,
            headers={"X-Request-Id": getattr(request.state, "request_id", exc.request_id)},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        request.state.error_code = ErrorCode.VALIDATION_ERROR.value
        ctx = _build_audit_ctx_from_request_state(request)
        write_audit_event(
            ctx=ctx,
            event_type=AuditEventType.API_RESPONSE.value,
            resource=str(getattr(getattr(request, "url", None), "path", None) or "http"),
            action_summary={
                "method": request.method,
                "path": request.url.path,
                "statusCode": 422,
            },
            result_status="failure",
            error_code=ErrorCode.VALIDATION_ERROR.value,
        )
        err = ErrorResponse(
            code=ErrorCode.VALIDATION_ERROR.value,
            message="Validation error",
            details={
                "errors": exc.errors(),
            },
            retryable=False,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=422,
            content=err.model_dump(by_alias=True),
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        request.state.error_code = ErrorCode.INTERNAL_ERROR.value
        ctx = _build_audit_ctx_from_request_state(request)
        write_audit_event(
            ctx=ctx,
            event_type=AuditEventType.API_RESPONSE.value,
            resource=str(getattr(getattr(request, "url", None), "path", None) or "http"),
            action_summary={
                "method": request.method,
                "path": request.url.path,
                "statusCode": 500,
            },
            result_status="failure",
            error_code=ErrorCode.INTERNAL_ERROR.value,
        )
        err = ErrorResponse(
            code=ErrorCode.INTERNAL_ERROR.value,
            message="Internal error",
            details=None,
            retryable=False,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content=err.model_dump(by_alias=True),
            headers={"X-Request-Id": request_id},
        )

    return app


def _map_status_code(code: ErrorCode) -> int:
    return ERROR_CODE_TO_STATUS.get(code, 500)
