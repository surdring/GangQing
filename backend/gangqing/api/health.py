from __future__ import annotations

import os
import threading
import time
import structlog
from fastapi import APIRouter, Depends
from fastapi import Response

from gangqing.common.context import RequestContext, build_request_context
from gangqing.common.healthcheck import HealthResponse
from gangqing.common.healthcheck import HealthOverallStatus
from gangqing.common.healthcheck import aggregate_overall_status
from gangqing.common.healthcheck import build_version_info
from gangqing.common.healthcheck import load_healthcheck_settings
from gangqing.common.healthcheck import run_dependency_probes


router = APIRouter()

logger = structlog.get_logger(__name__)


_CACHE_LOCK = threading.Lock()
_CACHED_AT_MONO: float | None = None
_CACHED_PAYLOAD: HealthResponse | None = None


def _load_cache_ttl_seconds() -> float:
    raw = (os.environ.get("GANGQING_HEALTHCHECK_CACHE_TTL_SECONDS") or "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def _get_cached_payload() -> HealthResponse | None:
    ttl = _load_cache_ttl_seconds()
    if ttl <= 0:
        return None
    with _CACHE_LOCK:
        if _CACHED_AT_MONO is None or _CACHED_PAYLOAD is None:
            return None
        if (time.monotonic() - _CACHED_AT_MONO) > ttl:
            return None
        return _CACHED_PAYLOAD


def _set_cached_payload(payload: HealthResponse) -> None:
    ttl = _load_cache_ttl_seconds()
    if ttl <= 0:
        return
    if payload.status == HealthOverallStatus.unhealthy:
        return
    with _CACHE_LOCK:
        global _CACHED_AT_MONO, _CACHED_PAYLOAD
        _CACHED_AT_MONO = time.monotonic()
        _CACHED_PAYLOAD = payload


@router.get("/health", response_model=HealthResponse)
def get_health(
    response: Response,
    ctx: RequestContext = Depends(build_request_context),
) -> HealthResponse:
    cached = _get_cached_payload()
    if cached is not None:
        response.headers["X-Request-Id"] = ctx.request_id
        return HealthResponse(
            status=cached.status,
            request_id=ctx.request_id,
            version=cached.version,
            dependencies=cached.dependencies,
        )

    settings = load_healthcheck_settings()
    dependencies = run_dependency_probes(settings)
    overall_status = aggregate_overall_status(dependencies)

    if overall_status == HealthOverallStatus.unhealthy:
        response.status_code = 503

    payload = HealthResponse(
        status=overall_status,
        request_id=ctx.request_id,
        version=build_version_info(settings),
        dependencies=dependencies,
    )

    logger.info(
        "healthcheck",
        overall_status=overall_status.value,
        dependencies=[
            {
                "name": dep.name.value,
                "status": dep.status.value,
                "critical": dep.critical,
                "latencyMs": dep.latency_ms,
                "reason": (dep.details.reason if dep.details else None),
            }
            for dep in dependencies
        ],
    )

    _set_cached_payload(payload)

    return payload
