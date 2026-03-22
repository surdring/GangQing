from __future__ import annotations

import time
from typing import Any, Callable, Protocol, TypedDict

from pydantic import BaseModel, ValidationError
from structlog.contextvars import bind_contextvars, clear_contextvars

from gangqing.common.audit import write_tool_call_event
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode, build_contract_violation_error, build_validation_error
from gangqing.common.settings import load_settings
from gangqing.tools.rbac import require_tool_capability
from gangqing_db.errors import MigrationError
from gangqing.tools.retry import RetryPolicy, compute_backoff_ms, should_retry_error


class ReadOnlyRunnableTool(Protocol):
    name: str
    ParamsModel: type[BaseModel]

    ResultModel: type[BaseModel] | None
    required_capability: str | None
    output_contract_source: str | None

    def run(self, *, ctx: RequestContext, params: BaseModel): ...


class RetryEvent(TypedDict, total=False):
    type: str
    toolName: str
    attempt: int
    maxAttempts: int
    backoffMs: int
    willRetry: bool
    errorCode: str
    reasonCode: str
    retryable: bool


def _build_tool_error_details(
    *,
    tool_name: str,
    duration_ms: int,
    attempt: int | None = None,
    max_attempts: int | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "toolName": tool_name,
        "durationMs": int(duration_ms),
    }
    if attempt is not None:
        details["attempt"] = int(attempt)
    if max_attempts is not None:
        details["maxAttempts"] = int(max_attempts)
    if timeout_ms is not None:
        details["timeoutMs"] = int(timeout_ms)
    return details


def _try_extract_timeout_ms(*, params: BaseModel) -> int | None:
    value = getattr(params, "timeout_seconds", None)
    if value is None:
        return None
    try:
        seconds = float(value)
    except Exception:
        return None
    if seconds <= 0:
        return None
    return int(seconds * 1000)


def _apply_default_timeout_seconds(*, settings, params: BaseModel) -> int | None:
    """Apply default timeout to tool params if it supports timeout_seconds.

    Rules:
    - If params has no timeout_seconds attribute: no-op.
    - If timeout_seconds is None: set to settings.tool_default_timeout_seconds.
    - If timeout_seconds is present: validate > 0 and clamp to settings.tool_max_timeout_seconds.
    Returns the effective timeout in milliseconds (int) if applicable.
    """

    if not hasattr(params, "timeout_seconds"):
        return None

    raw = getattr(params, "timeout_seconds", None)
    if raw is None:
        effective_seconds = float(settings.tool_default_timeout_seconds)
    else:
        try:
            raw_seconds = float(raw)
        except Exception:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "timeoutSeconds must be a number",
                request_id=getattr(params, "request_id", "") or "unknown",
                details=None,
                retryable=False,
            )
        if raw_seconds <= 0:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "timeoutSeconds must be greater than 0",
                request_id=getattr(params, "request_id", "") or "unknown",
                details=None,
                retryable=False,
            )
        effective_seconds = raw_seconds

    effective_seconds = min(float(effective_seconds), float(settings.tool_max_timeout_seconds))

    try:
        setattr(params, "timeout_seconds", float(effective_seconds))
    except Exception:
        pass

    return int(float(effective_seconds) * 1000)


def run_readonly_tool(
    *,
    tool: ReadOnlyRunnableTool,
    ctx: RequestContext,
    raw_params: dict[str, Any],
    retry_observer: Callable[[RetryEvent], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
):
    started = time.perf_counter()

    bind_contextvars(
        requestId=ctx.request_id,
        tenantId=ctx.tenant_id,
        projectId=ctx.project_id,
        sessionId=ctx.session_id,
        userId=ctx.user_id,
        role=ctx.role,
        taskId=ctx.task_id,
        stepId=ctx.step_id,
        toolName=getattr(tool, "name", None),
    )

    def _duration_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    def _try_extract_tool_call_id(*, params: BaseModel) -> str | None:
        value = getattr(params, "tool_call_id", None)
        if value is None:
            return None
        s = str(value).strip()
        return s or None

    def _try_extract_tool_call_id_from_raw(*, raw_params: dict[str, Any]) -> str | None:
        for key in ("toolCallId", "tool_call_id"):
            value = raw_params.get(key)
            if value is None:
                continue
            s = str(value).strip()
            if s:
                return s
        return None

    def _call_audit(**kwargs: Any) -> None:
        try:
            audit_fn(**kwargs)
        except TypeError:
            kwargs.pop("tool_call_id", None)
            kwargs.pop("duration_ms", None)
            audit_fn(**kwargs)

    audit_fn = getattr(tool, "_audit_fn", None) or write_tool_call_event

    result_model = getattr(tool, "ResultModel", None)

    settings = load_settings()
    retry_policy = RetryPolicy(
        max_retries=int(settings.tool_max_retries),
        backoff_base_ms=int(settings.tool_backoff_base_ms),
        backoff_multiplier=float(settings.tool_backoff_multiplier),
        backoff_max_ms=int(settings.tool_backoff_max_ms),
        backoff_jitter_ratio=float(settings.tool_backoff_jitter_ratio),
    )

    try:
        try:
            params = tool.ParamsModel.model_validate(raw_params)
        except ValidationError as e:
            err = build_validation_error(
                request_id=ctx.request_id,
                error=e,
                max_field_errors=int(settings.contract_validation_max_errors),
                stage="tool.params.validate",
                tool_name=tool.name,
            )
            _call_audit(
                ctx=ctx,
                tool_name=tool.name,
                tool_call_id=_try_extract_tool_call_id_from_raw(raw_params=raw_params),
                duration_ms=_duration_ms(),
                args_summary={
                    "stage": "tool.params.validate",
                    "durationMs": _duration_ms(),
                    "toolName": tool.name,
                    "requestId": ctx.request_id,
                    "stepId": ctx.step_id,
                    "errorCode": err.code.value,
                    "retryable": err.retryable,
                },
                result_status="failure",
                error_code=err.code.value,
            )
            raise err

        capability = getattr(tool, "required_capability", None)
        if capability:
            try:
                require_tool_capability(ctx=ctx, capability=capability, tool_name=tool.name)
            except AppError as e:
                _call_audit(
                    ctx=ctx,
                    tool_name=tool.name,
                    args_summary={
                        "stage": "tool.rbac",
                        "durationMs": _duration_ms(),
                        "toolName": tool.name,
                        "requestId": ctx.request_id,
                        "stepId": ctx.step_id,
                        "errorCode": e.code.value,
                        "retryable": e.retryable,
                    },
                    result_status="failure",
                    error_code=e.code.value,
                )
                raise

        last_error: AppError | None = None
        result: Any = None

        try:
            effective_timeout_ms = _apply_default_timeout_seconds(settings=settings, params=params)
        except AppError as e:
            _call_audit(
                ctx=ctx,
                tool_name=tool.name,
                tool_call_id=_try_extract_tool_call_id(params=params),
                duration_ms=_duration_ms(),
                args_summary={
                    "stage": "tool.params.timeout",
                    "durationMs": _duration_ms(),
                    "toolName": tool.name,
                    "requestId": ctx.request_id,
                    "stepId": ctx.step_id,
                    "errorCode": e.code.value,
                    "retryable": e.retryable,
                },
                result_status="failure",
                error_code=e.code.value,
            )
            raise

        for attempt in range(1, retry_policy.max_attempts + 1):
            if should_cancel is not None and should_cancel():
                timeout_ms = _try_extract_timeout_ms(params=params) or effective_timeout_ms
                err = AppError(
                    ErrorCode.INTERNAL_ERROR,
                    "Request cancelled",
                    request_id=ctx.request_id,
                    details=_build_tool_error_details(
                        tool_name=tool.name,
                        duration_ms=_duration_ms(),
                        attempt=attempt,
                        max_attempts=retry_policy.max_attempts,
                        timeout_ms=timeout_ms,
                    ),
                    retryable=False,
                )
                if retry_observer is not None:
                    retry_observer(
                        {
                            "type": "cancelled",
                            "toolName": tool.name,
                            "attempt": attempt,
                            "maxAttempts": retry_policy.max_attempts,
                            "errorCode": err.code.value,
                            "retryable": err.retryable,
                        }
                    )
                raise err

            if retry_observer is not None:
                retry_observer(
                    {
                        "type": "attempt_start",
                        "toolName": tool.name,
                        "attempt": attempt,
                        "maxAttempts": retry_policy.max_attempts,
                    }
                )

            try:
                result = tool.run(ctx=ctx, params=params)
                last_error = None
                if retry_observer is not None:
                    retry_observer(
                        {
                            "type": "attempt_success",
                            "toolName": tool.name,
                            "attempt": attempt,
                            "maxAttempts": retry_policy.max_attempts,
                        }
                    )
                break
            except MigrationError as e:
                try:
                    mapped_code = ErrorCode(e.code.value)
                except Exception:
                    mapped_code = ErrorCode.INTERNAL_ERROR

                last_error = AppError(
                    mapped_code,
                    e.message,
                    request_id=ctx.request_id,
                    details=_build_tool_error_details(
                        tool_name=tool.name,
                        duration_ms=_duration_ms(),
                        attempt=attempt,
                        max_attempts=retry_policy.max_attempts,
                        timeout_ms=_try_extract_timeout_ms(params=params) or effective_timeout_ms,
                    ),
                    retryable=bool(e.retryable),
                )
            except TimeoutError:
                last_error = AppError(
                    ErrorCode.UPSTREAM_TIMEOUT,
                    "Upstream request timed out",
                    request_id=ctx.request_id,
                    details=_build_tool_error_details(
                        tool_name=tool.name,
                        duration_ms=_duration_ms(),
                        attempt=attempt,
                        max_attempts=retry_policy.max_attempts,
                        timeout_ms=_try_extract_timeout_ms(params=params) or effective_timeout_ms,
                    ),
                    retryable=True,
                )
            except (ConnectionError, OSError):
                last_error = AppError(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "Upstream service is unavailable",
                    request_id=ctx.request_id,
                    details=_build_tool_error_details(
                        tool_name=tool.name,
                        duration_ms=_duration_ms(),
                        attempt=attempt,
                        max_attempts=retry_policy.max_attempts,
                        timeout_ms=_try_extract_timeout_ms(params=params) or effective_timeout_ms,
                    ),
                    retryable=True,
                )
            except AppError as e:
                timeout_ms = _try_extract_timeout_ms(params=params) or effective_timeout_ms
                duration_ms = _duration_ms()
                base_details = _build_tool_error_details(
                    tool_name=tool.name,
                    duration_ms=duration_ms,
                    attempt=attempt,
                    max_attempts=retry_policy.max_attempts,
                    timeout_ms=timeout_ms,
                )
                last_error = AppError(
                    e.code,
                    e.message,
                    request_id=e.request_id,
                    details=base_details,
                    retryable=bool(e.retryable),
                )
            except Exception:
                last_error = AppError(
                    ErrorCode.INTERNAL_ERROR,
                    "Tool execution failed",
                    request_id=ctx.request_id,
                    details=_build_tool_error_details(
                        tool_name=tool.name,
                        duration_ms=_duration_ms(),
                        attempt=attempt,
                        max_attempts=retry_policy.max_attempts,
                        timeout_ms=_try_extract_timeout_ms(params=params) or effective_timeout_ms,
                    ),
                    retryable=False,
                )

            max_attempts = retry_policy.max_attempts
            should_retry = should_retry_error(error=last_error) and attempt < max_attempts
            backoff_ms = (
                compute_backoff_ms(policy=retry_policy, attempt=attempt) if should_retry else 0
            )

            if retry_observer is not None:
                retry_observer(
                    {
                        "type": "attempt_failure",
                        "toolName": tool.name,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "errorCode": last_error.code.value,
                        "reasonCode": last_error.code.value,
                        "retryable": last_error.retryable,
                        "willRetry": bool(should_retry),
                        "backoffMs": int(backoff_ms),
                    }
                )

            _call_audit(
                ctx=ctx,
                tool_name=tool.name,
                tool_call_id=_try_extract_tool_call_id(params=params),
                duration_ms=_duration_ms(),
                args_summary={
                    "stage": "tool.execution",
                    "durationMs": _duration_ms(),
                    "toolName": tool.name,
                    "requestId": ctx.request_id,
                    "stepId": ctx.step_id,
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "timeoutMs": _try_extract_timeout_ms(params=params) or effective_timeout_ms,
                    "backoffMs": backoff_ms if should_retry else None,
                    "errorCode": last_error.code.value,
                    "retryable": last_error.retryable,
                },
                result_status="failure",
                error_code=last_error.code.value,
            )

            if not should_retry:
                raise last_error

            if retry_observer is not None:
                retry_observer(
                    {
                        "type": "retry_scheduled",
                        "toolName": tool.name,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "backoffMs": int(backoff_ms),
                        "reasonCode": last_error.code.value,
                    }
                )

            time.sleep(float(backoff_ms) / 1000.0)

        if last_error is not None:
            raise last_error

        if result_model is None:
            _call_audit(
                ctx=ctx,
                tool_name=tool.name,
                tool_call_id=_try_extract_tool_call_id(params=params),
                duration_ms=_duration_ms(),
                args_summary={
                    "stage": "tool.execution",
                    "durationMs": _duration_ms(),
                    "toolName": tool.name,
                    "requestId": ctx.request_id,
                    "stepId": ctx.step_id,
                    "attempt": attempt,
                    "maxAttempts": retry_policy.max_attempts,
                    "timeoutMs": _try_extract_timeout_ms(params=params) or effective_timeout_ms,
                    "errorCode": None,
                    "retryable": False,
                },
                result_status="success",
                error_code=None,
            )
            return result

        if isinstance(result, BaseModel):
            payload: Any = result.model_dump(by_alias=True)
        else:
            payload = result

        try:
            validated = result_model.model_validate(payload)
        except ValidationError as e:
            source = getattr(tool, "output_contract_source", None) or f"tool.{tool.name}.result"
            err = build_contract_violation_error(
                request_id=ctx.request_id,
                error=e,
                source=source,
                max_field_errors=int(settings.contract_validation_max_errors),
                stage="tool.output.validate",
                tool_name=tool.name,
            )
            _call_audit(
                ctx=ctx,
                tool_name=tool.name,
                tool_call_id=_try_extract_tool_call_id(params=params),
                duration_ms=_duration_ms(),
                args_summary={
                    "stage": "tool.output.validate",
                    "durationMs": _duration_ms(),
                    "toolName": tool.name,
                    "source": source,
                    "errorCount": int((err.details or {}).get("errorCount") or 0)
                    if isinstance(err.details, dict)
                    else 0,
                    "fieldErrorCount": len((err.details or {}).get("fieldErrors") or [])
                    if isinstance(err.details, dict)
                    else 0,
                    "requestId": ctx.request_id,
                    "stepId": ctx.step_id,
                    "timeoutMs": _try_extract_timeout_ms(params=params) or effective_timeout_ms,
                    "errorCode": err.code.value,
                    "retryable": err.retryable,
                },
                result_status="failure",
                error_code=err.code.value,
            )
            raise err

        _call_audit(
            ctx=ctx,
            tool_name=tool.name,
            tool_call_id=_try_extract_tool_call_id(params=params),
            duration_ms=_duration_ms(),
            args_summary={
                "stage": "tool.execution",
                "durationMs": _duration_ms(),
                "toolName": tool.name,
                "requestId": ctx.request_id,
                "stepId": ctx.step_id,
                "attempt": attempt,
                "maxAttempts": retry_policy.max_attempts,
                "timeoutMs": _try_extract_timeout_ms(params=params) or effective_timeout_ms,
                "errorCode": None,
                "retryable": bool(getattr(validated, "retryable", False)),
            },
            result_status="success",
            error_code=None,
        )
        return validated
    finally:
        clear_contextvars()
