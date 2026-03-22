from __future__ import annotations

import json
import time
import threading
from typing import Any

import httpx
import structlog

from gangqing.common.audit import write_tool_call_event
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.settings import load_settings
from gangqing.tools.retry import RetryPolicy, compute_backoff_ms, should_retry_error


logger = structlog.get_logger(__name__)


def _build_llamacpp_headers(*, api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = key if " " in key else f"Bearer {key}"
        headers["X-Api-Key"] = key
    return headers


def _normalize_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    return value


def _join_v1_path(*, base_url: str, path: str) -> str:
    base = _normalize_base_url(base_url)
    suffix = "/" + (path or "").lstrip("/")
    return base + suffix


def _build_url_candidates(*, base_url: str, path: str) -> list[str]:
    base = _normalize_base_url(base_url)
    raw_path = "/" + (path or "").lstrip("/")

    candidates: list[str] = []
    if base.endswith("/v1"):
        candidates.append(base.removesuffix("/v1") + raw_path)
        candidates.append(base + raw_path)
    else:
        candidates.append(base + raw_path)
        if not raw_path.startswith("/v1/"):
            candidates.append(base + "/v1" + raw_path)

    seen: set[str] = set()
    return [u for u in candidates if not (u in seen or seen.add(u))]


def _extract_upstream_status_code(resp: httpx.Response | None) -> int | None:
    if resp is None:
        return None
    try:
        return int(resp.status_code)
    except Exception:
        return None


def map_llamacpp_exception(
    *,
    ctx: RequestContext,
    stage: str,
    duration_ms: int,
    timeout_ms: int,
    error: Exception,
    upstream_status_code: int | None = None,
    attempt: int | None = None,
    max_attempts: int | None = None,
) -> AppError:
    details: dict[str, Any] = {
        "stage": stage,
        "durationMs": int(duration_ms),
        "timeoutMs": int(timeout_ms),
    }
    if attempt is not None:
        details["attempt"] = int(attempt)
    if max_attempts is not None:
        details["maxAttempts"] = int(max_attempts)
    if upstream_status_code is not None:
        details["upstreamStatusCode"] = int(upstream_status_code)

    if isinstance(error, (json.JSONDecodeError, ValueError)):
        return AppError(
            ErrorCode.CONTRACT_VIOLATION,
            "Upstream response is not valid JSON",
            request_id=ctx.request_id,
            details=details,
            retryable=False,
        )

    if isinstance(error, httpx.TimeoutException):
        return AppError(
            ErrorCode.UPSTREAM_TIMEOUT,
            "Upstream request timed out",
            request_id=ctx.request_id,
            details=details,
            retryable=True,
        )

    if isinstance(error, httpx.HTTPStatusError):
        status = upstream_status_code
        if status is not None and status >= 500:
            return AppError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Upstream service is unavailable",
                request_id=ctx.request_id,
                details=details,
                retryable=True,
            )
        if status is not None and status in {408, 429}:
            return AppError(
                ErrorCode.UPSTREAM_TIMEOUT if status == 408 else ErrorCode.UPSTREAM_UNAVAILABLE,
                "Upstream request timed out" if status == 408 else "Upstream service is unavailable",
                request_id=ctx.request_id,
                details=details,
                retryable=True,
            )
        if status is not None and status in {401, 403}:
            return AppError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Upstream authorization failed",
                request_id=ctx.request_id,
                details=details,
                retryable=False,
            )
        return AppError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            "Upstream request failed",
            request_id=ctx.request_id,
            details=details,
            retryable=False,
        )

    if isinstance(error, httpx.RequestError):
        return AppError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            "Upstream service is unavailable",
            request_id=ctx.request_id,
            details=details,
            retryable=True,
        )

    return AppError(
        ErrorCode.INTERNAL_ERROR,
        "Internal error",
        request_id=ctx.request_id,
        details=details,
        retryable=False,
    )


class LlamaCppClient:
    def __init__(self) -> None:
        settings = load_settings()
        self._base_url = _normalize_base_url(settings.llamacpp_base_url)
        self._api_key = settings.llamacpp_api_key
        self._models_path = str(getattr(settings, "llamacpp_models_path", "/models") or "/models")
        self._timeout_seconds = float(settings.llamacpp_timeout_seconds)
        self._timeout_ms = int(round(self._timeout_seconds * 1000.0))
        self._trust_env = bool(settings.llamacpp_trust_env)
        self._max_concurrency = int(settings.llamacpp_max_concurrency)
        self._semaphore = threading.BoundedSemaphore(value=max(1, int(self._max_concurrency)))

        self._provider_base_url = _normalize_base_url(settings.provider_base_url)
        self._provider_api_key = settings.provider_api_key
        self._provider_timeout_seconds = float(settings.provider_timeout_seconds)
        self._provider_timeout_ms = int(round(self._provider_timeout_seconds * 1000.0))
        self._provider_trust_env = bool(settings.provider_trust_env)
        self._retry_policy = RetryPolicy(
            max_retries=int(settings.tool_max_retries),
            backoff_base_ms=int(settings.tool_backoff_base_ms),
            backoff_multiplier=float(settings.tool_backoff_multiplier),
            backoff_max_ms=int(settings.tool_backoff_max_ms),
            backoff_jitter_ratio=float(settings.tool_backoff_jitter_ratio),
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def _require_configured(self, *, ctx: RequestContext) -> None:
        if not self._base_url:
            raise AppError(
                ErrorCode.SERVICE_UNAVAILABLE,
                "llama.cpp base URL is not configured",
                request_id=ctx.request_id,
                details={"missing": "GANGQING_LLAMACPP_BASE_URL"},
                retryable=False,
            )

    def list_models(self, *, ctx: RequestContext) -> dict[str, Any]:
        self._require_configured(ctx=ctx)

        started = time.perf_counter()
        stage = "llamacpp.models.list"
        url_candidates = _build_url_candidates(base_url=self._base_url, path=self._models_path)

        headers = _build_llamacpp_headers(api_key=self._api_key)

        status_code: int | None = None
        err: AppError | None = None
        acquired = False
        try:
            acquired = bool(self._semaphore.acquire(timeout=self._timeout_seconds))
            if not acquired:
                raise httpx.TimeoutException("Concurrency queue timeout")

            max_attempts = int(self._retry_policy.max_attempts)
            last_exc: Exception | None = None
            last_app_error: AppError | None = None

            with httpx.Client(timeout=self._timeout_seconds, trust_env=self._trust_env) as client:
                for attempt in range(1, max_attempts + 1):
                    try:
                        last_http_exc: Exception | None = None
                        last_upstream_status: int | None = None
                        last_json: dict[str, Any] | None = None

                        for url in url_candidates:
                            try:
                                resp = client.get(url, headers=headers, follow_redirects=True)
                                status_code = int(resp.status_code)
                                last_upstream_status = status_code
                                resp.raise_for_status()
                                try:
                                    last_json = resp.json() if resp.content else {}
                                except Exception as je:
                                    raise ValueError("Invalid JSON") from je
                                break
                            except Exception as ue:
                                last_http_exc = ue
                                if isinstance(ue, httpx.HTTPStatusError):
                                    last_upstream_status = _extract_upstream_status_code(
                                        getattr(ue, "response", None)
                                    )
                                continue

                        if last_json is None:
                            raise last_http_exc or httpx.RequestError(
                                "Upstream request failed", request=httpx.Request("GET", url_candidates[0])
                            )

                        data = last_json

                        duration_ms = int((time.perf_counter() - started) * 1000)
                        write_tool_call_event(
                            ctx=ctx,
                            tool_name="llama_cpp",
                            tool_call_id=None,
                            duration_ms=duration_ms,
                            args_summary={
                                "stage": stage,
                                "durationMs": duration_ms,
                                "timeoutMs": self._timeout_ms,
                                "endpoint": self._models_path,
                                "maxConcurrency": self._max_concurrency,
                                "attempt": attempt,
                                "maxAttempts": max_attempts,
                                "statusCode": status_code,
                            },
                            result_status="success",
                            error_code=None,
                            evidence_refs=None,
                        )
                        return data

                    except Exception as e:
                        last_exc = e
                        duration_ms = int((time.perf_counter() - started) * 1000)
                        upstream_status_code = status_code
                        if isinstance(e, httpx.HTTPStatusError):
                            upstream_status_code = _extract_upstream_status_code(
                                getattr(e, "response", None)
                            )

                        last_app_error = map_llamacpp_exception(
                            ctx=ctx,
                            stage=stage,
                            duration_ms=duration_ms,
                            timeout_ms=self._timeout_ms,
                            error=e if isinstance(e, Exception) else Exception("Unknown error"),
                            upstream_status_code=upstream_status_code,
                            attempt=attempt,
                            max_attempts=max_attempts,
                        )

                        if (
                            isinstance(e, httpx.TimeoutException)
                            and str(getattr(e, "args", [""])[0] if getattr(e, "args", None) else "")
                            == "Concurrency queue timeout"
                            and isinstance(last_app_error.details, dict)
                        ):
                            last_app_error.details["reason"] = "concurrency_queue_timeout"

                        will_retry = (attempt < max_attempts) and should_retry_error(
                            error=last_app_error
                        )
                        if not will_retry:
                            raise last_app_error

                        backoff_ms = compute_backoff_ms(policy=self._retry_policy, attempt=attempt)
                        logger.warning(
                            "llamacpp_retry_scheduled",
                            stage=stage,
                            attempt=attempt,
                            maxAttempts=max_attempts,
                            backoffMs=backoff_ms,
                            errorCode=last_app_error.code.value,
                            retryable=last_app_error.retryable,
                        )
                        if backoff_ms > 0:
                            time.sleep(float(backoff_ms) / 1000.0)

            final_err = last_app_error or map_llamacpp_exception(
                ctx=ctx,
                stage=stage,
                duration_ms=int((time.perf_counter() - started) * 1000),
                timeout_ms=self._timeout_ms,
                error=last_exc or Exception("Unknown error"),
                upstream_status_code=status_code,
                attempt=max_attempts,
                max_attempts=max_attempts,
            )

            if (
                final_err.code in {ErrorCode.UPSTREAM_TIMEOUT, ErrorCode.UPSTREAM_UNAVAILABLE}
                and bool(self._provider_base_url.strip())
            ):
                provider_started = time.perf_counter()
                provider_stage = "provider.models.list"
                provider_headers = _build_llamacpp_headers(api_key=self._provider_api_key)
                provider_urls = _build_url_candidates(base_url=self._provider_base_url, path="/models")
                logger.warning(
                    "llamacpp_fallback_to_provider",
                    stage=stage,
                    requestId=ctx.request_id,
                    fallbackTo="provider",
                    errorCode=final_err.code.value,
                )
                write_tool_call_event(
                    ctx=ctx,
                    tool_name="model_fallback",
                    args_summary={
                        "route": "llama_cpp->provider",
                        "stage": stage,
                        "errorCode": final_err.code.value,
                    },
                    result_status="success",
                    error_code=None,
                    evidence_refs=None,
                )

                try:
                    with httpx.Client(
                        timeout=self._provider_timeout_seconds,
                        trust_env=self._provider_trust_env,
                    ) as provider_client:
                        last_provider_exc: Exception | None = None
                        last_provider_status: int | None = None
                        for url in provider_urls:
                            try:
                                resp = provider_client.get(
                                    url, headers=provider_headers, follow_redirects=True
                                )
                                last_provider_status = int(resp.status_code)
                                resp.raise_for_status()
                                data = resp.json() if resp.content else {}
                                duration_ms = int((time.perf_counter() - provider_started) * 1000)
                                write_tool_call_event(
                                    ctx=ctx,
                                    tool_name="provider",
                                    args_summary={
                                        "stage": provider_stage,
                                        "durationMs": duration_ms,
                                        "timeoutMs": self._provider_timeout_ms,
                                        "endpoint": "/models",
                                        "statusCode": last_provider_status,
                                    },
                                    result_status="success",
                                    error_code=None,
                                    evidence_refs=None,
                                )
                                return data
                            except Exception as pe:
                                last_provider_exc = pe
                                if isinstance(pe, httpx.HTTPStatusError):
                                    last_provider_status = _extract_upstream_status_code(
                                        getattr(pe, "response", None)
                                    )
                                continue
                        raise last_provider_exc or Exception("Provider request failed")
                except Exception as pe:
                    duration_ms = int((time.perf_counter() - provider_started) * 1000)
                    provider_app_err = map_llamacpp_exception(
                        ctx=ctx,
                        stage=provider_stage,
                        duration_ms=duration_ms,
                        timeout_ms=self._provider_timeout_ms,
                        error=pe if isinstance(pe, Exception) else Exception("Unknown error"),
                        upstream_status_code=None,
                        attempt=1,
                        max_attempts=1,
                    )
                    write_tool_call_event(
                        ctx=ctx,
                        tool_name="provider",
                        args_summary={
                            "stage": provider_stage,
                            "durationMs": duration_ms,
                            "timeoutMs": self._provider_timeout_ms,
                            "endpoint": "/models",
                            "errorCode": provider_app_err.code.value,
                            "retryable": provider_app_err.retryable,
                        },
                        result_status="failure",
                        error_code=provider_app_err.code.value,
                        evidence_refs=None,
                    )

                    raise final_err

            raise final_err

        except Exception as e:
            duration_ms = int((time.perf_counter() - started) * 1000)
            upstream_status_code = status_code
            if isinstance(e, httpx.HTTPStatusError):
                upstream_status_code = _extract_upstream_status_code(getattr(e, "response", None))

            max_attempts = int(self._retry_policy.max_attempts)

            err = map_llamacpp_exception(
                ctx=ctx,
                stage=stage,
                duration_ms=duration_ms,
                timeout_ms=self._timeout_ms,
                error=e if isinstance(e, Exception) else Exception("Unknown error"),
                upstream_status_code=upstream_status_code,
                attempt=max_attempts,
                max_attempts=max_attempts,
            )
            if (
                isinstance(e, httpx.TimeoutException)
                and str(getattr(e, "args", [""])[0] if getattr(e, "args", None) else "")
                == "Concurrency queue timeout"
                and isinstance(err.details, dict)
            ):
                err.details["reason"] = "concurrency_queue_timeout"
            write_tool_call_event(
                ctx=ctx,
                tool_name="llama_cpp",
                args_summary={
                    "stage": stage,
                    "durationMs": duration_ms,
                    "timeoutMs": self._timeout_ms,
                    "endpoint": self._models_path,
                    "maxConcurrency": self._max_concurrency,
                    "attempt": max_attempts,
                    "maxAttempts": max_attempts,
                    "statusCode": upstream_status_code,
                    "errorCode": err.code.value,
                    "retryable": err.retryable,
                },
                result_status="failure",
                error_code=err.code.value,
                evidence_refs=None,
            )
            logger.warning(
                "llamacpp_request_failed",
                stage=stage,
                durationMs=duration_ms,
                statusCode=upstream_status_code,
                errorClass=e.__class__.__name__,
            )
            raise err
        finally:
            if acquired:
                try:
                    self._semaphore.release()
                except ValueError:
                    pass
