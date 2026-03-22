from __future__ import annotations

import os
import threading
import time

import httpx
import pytest

from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode
from gangqing.common.llamacpp_client import LlamaCppClient, map_llamacpp_exception


def test_map_timeout_exception_to_upstream_timeout() -> None:
    ctx = RequestContext(requestId="r1", tenantId="t1", projectId="p1")
    err = map_llamacpp_exception(
        ctx=ctx,
        stage="llamacpp.models.list",
        duration_ms=12,
        timeout_ms=100,
        error=httpx.TimeoutException("timeout"),
        upstream_status_code=None,
    )
    assert err.code == ErrorCode.UPSTREAM_TIMEOUT
    assert err.retryable is True
    assert err.request_id == "r1"
    assert isinstance(err.details, dict)
    assert err.details.get("timeoutMs") == 100


def test_http_5xx_is_mapped_to_upstream_unavailable_retryable_true() -> None:
    ctx = RequestContext(requestId="r_http_1", tenantId="t1", projectId="p1")
    req = httpx.Request("GET", "http://example.invalid/v1/models")
    resp = httpx.Response(status_code=503, request=req, content=b"service down")
    err = map_llamacpp_exception(
        ctx=ctx,
        stage="llamacpp.models.list",
        duration_ms=20,
        timeout_ms=200,
        error=httpx.HTTPStatusError("upstream error", request=req, response=resp),
        upstream_status_code=503,
        attempt=1,
        max_attempts=3,
    )
    assert err.code == ErrorCode.UPSTREAM_UNAVAILABLE
    assert err.retryable is True
    assert isinstance(err.details, dict)
    assert err.details.get("upstreamStatusCode") == 503
    assert err.details.get("attempt") == 1
    assert err.details.get("maxAttempts") == 3


def test_invalid_json_is_mapped_to_contract_violation_retryable_false() -> None:
    ctx = RequestContext(requestId="r_json_1", tenantId="t1", projectId="p1")
    err = map_llamacpp_exception(
        ctx=ctx,
        stage="llamacpp.models.list",
        duration_ms=5,
        timeout_ms=200,
        error=ValueError("Invalid JSON"),
        upstream_status_code=200,
        attempt=1,
        max_attempts=1,
    )
    assert err.code == ErrorCode.CONTRACT_VIOLATION
    assert err.retryable is False
    assert isinstance(err.details, dict)
    assert err.details.get("upstreamStatusCode") == 200
    assert err.details.get("attempt") == 1
    assert err.details.get("maxAttempts") == 1


def test_http_408_is_mapped_to_upstream_timeout_retryable_true() -> None:
    ctx = RequestContext(requestId="r_http_408_1", tenantId="t1", projectId="p1")
    req = httpx.Request("GET", "http://example.invalid/v1/models")
    resp = httpx.Response(status_code=408, request=req, content=b"timeout")
    err = map_llamacpp_exception(
        ctx=ctx,
        stage="llamacpp.models.list",
        duration_ms=20,
        timeout_ms=200,
        error=httpx.HTTPStatusError("upstream error", request=req, response=resp),
        upstream_status_code=408,
        attempt=1,
        max_attempts=2,
    )
    assert err.code == ErrorCode.UPSTREAM_TIMEOUT
    assert err.retryable is True
    assert err.request_id == "r_http_408_1"


def test_http_429_is_mapped_to_upstream_unavailable_retryable_true() -> None:
    ctx = RequestContext(requestId="r_http_429_1", tenantId="t1", projectId="p1")
    req = httpx.Request("GET", "http://example.invalid/v1/models")
    resp = httpx.Response(status_code=429, request=req, content=b"rate limited")
    err = map_llamacpp_exception(
        ctx=ctx,
        stage="llamacpp.models.list",
        duration_ms=20,
        timeout_ms=200,
        error=httpx.HTTPStatusError("upstream error", request=req, response=resp),
        upstream_status_code=429,
        attempt=1,
        max_attempts=2,
    )
    assert err.code == ErrorCode.UPSTREAM_UNAVAILABLE
    assert err.retryable is True
    assert err.request_id == "r_http_429_1"


def test_client_requires_base_url_configured() -> None:
    original = os.environ.get("GANGQING_LLAMACPP_BASE_URL")
    os.environ["GANGQING_LLAMACPP_BASE_URL"] = ""
    try:
        client = LlamaCppClient()
        ctx = RequestContext(requestId="r2", tenantId="t1", projectId="p1")
        with pytest.raises(AppError) as e:
            client.list_models(ctx=ctx)
        assert e.value.code == ErrorCode.SERVICE_UNAVAILABLE
        assert e.value.retryable is False
        assert e.value.request_id == "r2"
    finally:
        if original is None:
            os.environ.pop("GANGQING_LLAMACPP_BASE_URL", None)
        else:
            os.environ["GANGQING_LLAMACPP_BASE_URL"] = original


def test_client_concurrency_queue_timeout_is_mapped() -> None:
    original_base_url = os.environ.get("GANGQING_LLAMACPP_BASE_URL")
    original_timeout = os.environ.get("GANGQING_LLAMACPP_TIMEOUT_SECONDS")
    original_concurrency = os.environ.get("GANGQING_LLAMACPP_MAX_CONCURRENCY")
    try:
        os.environ["GANGQING_LLAMACPP_BASE_URL"] = "http://127.0.0.1:9/v1"
        os.environ["GANGQING_LLAMACPP_TIMEOUT_SECONDS"] = "0.2"
        os.environ["GANGQING_LLAMACPP_MAX_CONCURRENCY"] = "1"

        client = LlamaCppClient()
        ctx = RequestContext(requestId="r3", tenantId="t1", projectId="p1")

        def hold() -> None:
            assert client._semaphore.acquire(timeout=0.1)
            time.sleep(0.4)
            client._semaphore.release()

        t = threading.Thread(target=hold, daemon=True)
        t.start()
        time.sleep(0.05)

        with pytest.raises(AppError) as e:
            client.list_models(ctx=ctx)

        assert e.value.code == ErrorCode.UPSTREAM_TIMEOUT
        assert e.value.retryable is True
        assert e.value.request_id == "r3"
        assert isinstance(e.value.details, dict)
        assert e.value.details.get("reason") == "concurrency_queue_timeout"
    finally:
        if original_base_url is None:
            os.environ.pop("GANGQING_LLAMACPP_BASE_URL", None)
        else:
            os.environ["GANGQING_LLAMACPP_BASE_URL"] = original_base_url

        if original_timeout is None:
            os.environ.pop("GANGQING_LLAMACPP_TIMEOUT_SECONDS", None)
        else:
            os.environ["GANGQING_LLAMACPP_TIMEOUT_SECONDS"] = original_timeout

        if original_concurrency is None:
            os.environ.pop("GANGQING_LLAMACPP_MAX_CONCURRENCY", None)
        else:
            os.environ["GANGQING_LLAMACPP_MAX_CONCURRENCY"] = original_concurrency
