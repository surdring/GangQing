from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import httpx
import structlog
from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


logger = structlog.get_logger(__name__)


class HealthOverallStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"


class HealthDependencyName(str, Enum):
    postgres = "postgres"
    llama_cpp = "llama_cpp"
    provider = "provider"
    model = "model"
    config = "config"


class HealthDependencyStatus(str, Enum):
    ok = "ok"
    degraded = "degraded"
    unavailable = "unavailable"


class HealthDependencyDetails(BaseModel):
    reason: str | None = None
    error_class: str | None = Field(default=None, alias="errorClass")
    missing_keys: list[str] | None = Field(default=None, alias="missingKeys")

    model_config = {"populate_by_name": True}


class HealthDependency(BaseModel):
    name: HealthDependencyName
    status: HealthDependencyStatus
    critical: bool
    latency_ms: float | None = Field(default=None, alias="latencyMs")
    checked_at: str = Field(alias="checkedAt")
    details: HealthDependencyDetails | None = None

    model_config = {"populate_by_name": True}


class VersionInfo(BaseModel):
    service: str
    api_version: str = Field(alias="apiVersion")
    build: str
    commit: str
    started_at: str = Field(alias="startedAt")

    model_config = {"populate_by_name": True}


class HealthResponse(BaseModel):
    status: HealthOverallStatus
    request_id: str = Field(alias="requestId")
    version: VersionInfo
    dependencies: list[HealthDependency]

    model_config = {"populate_by_name": True}


class HealthcheckSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GANGQING_", extra="ignore")

    database_url: str = Field(default="")

    healthcheck_postgres_connect_timeout_seconds: float = Field(default=2.0, ge=0.1, le=30.0)

    llamacpp_base_url: str = Field(default="")
    llamacpp_api_key: str = Field(default="")
    llamacpp_health_path: str = Field(default="/health")
    llamacpp_timeout_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    llamacpp_trust_env: bool = Field(default=False)
    llamacpp_critical: bool = Field(default=False)

    provider_healthcheck_url: str = Field(default="")
    provider_api_key: str = Field(default="")
    provider_timeout_seconds: float = Field(default=1.5, ge=0.1, le=30.0)
    provider_trust_env: bool = Field(default=False)

    service_name: str = Field(default="gangqing-api")
    build: str = Field(default="unknown")
    commit: str = Field(default="unknown")

    @field_validator("llamacpp_health_path")
    @classmethod
    def validate_llamacpp_health_path(cls, v: str) -> str:
        value = (v or "").strip()
        return value or "/health"


_STARTED_AT = datetime.now(timezone.utc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_healthcheck_settings() -> HealthcheckSettings:
    return HealthcheckSettings()


def probe_config(settings: HealthcheckSettings) -> HealthDependency:
    started = time.perf_counter()
    missing: list[str] = []
    if not settings.database_url.strip():
        missing.append("GANGQING_DATABASE_URL")

    has_llama_config = bool(settings.llamacpp_base_url.strip())
    has_provider_config = bool(settings.provider_healthcheck_url.strip())
    if not (has_llama_config or has_provider_config):
        missing.append("GANGQING_LLAMACPP_BASE_URL")
        missing.append("GANGQING_PROVIDER_HEALTHCHECK_URL")

    status = HealthDependencyStatus.ok
    details: HealthDependencyDetails | None = None
    if missing:
        status = HealthDependencyStatus.unavailable
        reason = "not_configured"
        if ("GANGQING_LLAMACPP_BASE_URL" in missing) and (
            "GANGQING_PROVIDER_HEALTHCHECK_URL" in missing
        ):
            reason = "not_configured_model_provider_required"
        details = HealthDependencyDetails(reason=reason, missing_keys=missing)

    return HealthDependency(
        name=HealthDependencyName.config,
        status=status,
        critical=True,
        latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
        checked_at=_now_iso(),
        details=details,
    )


def probe_postgres(settings: HealthcheckSettings) -> HealthDependency:
    started = time.perf_counter()
    checked_at = _now_iso()

    if not settings.database_url.strip():
        return HealthDependency(
            name=HealthDependencyName.postgres,
            status=HealthDependencyStatus.unavailable,
            critical=True,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="not_configured"),
        )

    try:
        connect_timeout_s = float(settings.healthcheck_postgres_connect_timeout_seconds)
        connect_timeout_int = max(1, int(round(connect_timeout_s)))
        engine = create_engine(
            settings.database_url,
            pool_pre_ping=False,
            poolclass=NullPool,
            connect_args={"connect_timeout": connect_timeout_int},
        )
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
        finally:
            try:
                engine.dispose()
            except Exception:
                pass
        return HealthDependency(
            name=HealthDependencyName.postgres,
            status=HealthDependencyStatus.ok,
            critical=True,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=None,
        )
    except Exception as e:
        return HealthDependency(
            name=HealthDependencyName.postgres,
            status=HealthDependencyStatus.unavailable,
            critical=True,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="connection_failed", error_class=e.__class__.__name__),
        )


def probe_llama_cpp(settings: HealthcheckSettings) -> HealthDependency:
    started = time.perf_counter()
    checked_at = _now_iso()

    is_critical = bool(settings.llamacpp_critical)

    if not settings.llamacpp_base_url.strip():
        return HealthDependency(
            name=HealthDependencyName.llama_cpp,
            status=HealthDependencyStatus.unavailable,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="not_configured"),
        )

    base_url = settings.llamacpp_base_url.strip().rstrip("/")
    health_path = "/" + settings.llamacpp_health_path.strip().lstrip("/")

    url_candidates: list[str] = []

    # Compatibility fallback:
    # Some OpenAI-compatible servers expose endpoints under /v1, some don't.
    if base_url.endswith("/v1"):
        # Prefer trying without /v1 first to avoid hanging on a wrong prefix.
        url_candidates.append(base_url.removesuffix("/v1") + health_path)
        url_candidates.append(base_url + health_path)
    else:
        url_candidates.append(base_url + health_path)
        if not health_path.startswith("/v1/"):
            url_candidates.append(base_url + "/v1" + health_path)

    seen: set[str] = set()
    url_candidates = [u for u in url_candidates if not (u in seen or seen.add(u))]

    try:
        headers: dict[str, str] = {"Accept": "application/json", "Connection": "close"}
        api_key = settings.llamacpp_api_key.strip()
        if api_key:
            headers["Authorization"] = api_key if " " in api_key else f"Bearer {api_key}"
            headers["X-Api-Key"] = api_key

        last_status_code: int | None = None
        last_error_class: str | None = None
        had_timeout = False

        per_attempt_timeout = float(settings.llamacpp_timeout_seconds)
        if len(url_candidates) > 1:
            per_attempt_timeout = max(0.1, per_attempt_timeout / float(len(url_candidates)))

        with httpx.Client(
            timeout=per_attempt_timeout,
            trust_env=bool(settings.llamacpp_trust_env),
        ) as client:
            for url in url_candidates:
                try:
                    resp = client.get(url, headers=headers, follow_redirects=True)
                    last_status_code = int(resp.status_code)
                    if 200 <= last_status_code < 300:
                        return HealthDependency(
                            name=HealthDependencyName.llama_cpp,
                            status=HealthDependencyStatus.ok,
                            critical=is_critical,
                            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
                            checked_at=checked_at,
                            details=None,
                        )
                except httpx.TimeoutException as e:
                    had_timeout = True
                    last_error_class = e.__class__.__name__
                    continue
                except Exception as e:
                    last_error_class = e.__class__.__name__
                    continue

        if last_status_code is not None:
            return HealthDependency(
                name=HealthDependencyName.llama_cpp,
                status=HealthDependencyStatus.unavailable
                if is_critical
                else HealthDependencyStatus.degraded,
                critical=is_critical,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
                checked_at=checked_at,
                details=HealthDependencyDetails(reason="unexpected_response"),
            )
        if had_timeout:
            return HealthDependency(
                name=HealthDependencyName.llama_cpp,
                status=HealthDependencyStatus.unavailable
                if is_critical
                else HealthDependencyStatus.degraded,
                critical=is_critical,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
                checked_at=checked_at,
                details=HealthDependencyDetails(reason="timeout", error_class=last_error_class),
            )
        return HealthDependency(
            name=HealthDependencyName.llama_cpp,
            status=HealthDependencyStatus.unavailable
            if is_critical
            else HealthDependencyStatus.degraded,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="connection_failed", error_class=last_error_class),
        )
    except httpx.TimeoutException as e:
        return HealthDependency(
            name=HealthDependencyName.llama_cpp,
            status=HealthDependencyStatus.unavailable
            if is_critical
            else HealthDependencyStatus.degraded,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="timeout", error_class=e.__class__.__name__),
        )
    except Exception as e:
        return HealthDependency(
            name=HealthDependencyName.llama_cpp,
            status=HealthDependencyStatus.unavailable
            if is_critical
            else HealthDependencyStatus.degraded,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="connection_failed", error_class=e.__class__.__name__),
        )


def probe_provider(settings: HealthcheckSettings) -> HealthDependency:
    started = time.perf_counter()
    checked_at = _now_iso()

    is_critical = False

    if not settings.provider_healthcheck_url.strip():
        return HealthDependency(
            name=HealthDependencyName.provider,
            status=HealthDependencyStatus.unavailable,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="not_configured"),
        )

    try:
        headers: dict[str, str] = {"Accept": "application/json", "Connection": "close"}
        api_key = settings.provider_api_key.strip()
        if api_key:
            headers["Authorization"] = api_key if " " in api_key else f"Bearer {api_key}"
            headers["X-Api-Key"] = api_key

        with httpx.Client(
            timeout=float(settings.provider_timeout_seconds),
            trust_env=bool(settings.provider_trust_env),
        ) as client:
            resp = client.get(settings.provider_healthcheck_url, headers=headers, follow_redirects=True)

        if 200 <= int(resp.status_code) < 300:
            return HealthDependency(
                name=HealthDependencyName.provider,
                status=HealthDependencyStatus.ok,
                critical=is_critical,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
                checked_at=checked_at,
                details=None,
            )
        return HealthDependency(
            name=HealthDependencyName.provider,
            status=HealthDependencyStatus.unavailable
            if is_critical
            else HealthDependencyStatus.degraded,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="unexpected_response"),
        )
    except httpx.TimeoutException as e:
        return HealthDependency(
            name=HealthDependencyName.provider,
            status=HealthDependencyStatus.unavailable
            if is_critical
            else HealthDependencyStatus.degraded,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="timeout", error_class=e.__class__.__name__),
        )
    except Exception as e:
        return HealthDependency(
            name=HealthDependencyName.provider,
            status=HealthDependencyStatus.unavailable
            if is_critical
            else HealthDependencyStatus.degraded,
            critical=is_critical,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            checked_at=checked_at,
            details=HealthDependencyDetails(reason="connection_failed", error_class=e.__class__.__name__),
        )


def probe_model(llama: HealthDependency, provider: HealthDependency) -> HealthDependency:
    checked_at = _now_iso()
    model_ok = (llama.status == HealthDependencyStatus.ok) or (provider.status == HealthDependencyStatus.ok)
    if model_ok:
        return HealthDependency(
            name=HealthDependencyName.model,
            status=HealthDependencyStatus.ok,
            critical=True,
            latency_ms=None,
            checked_at=checked_at,
            details=None,
        )
    return HealthDependency(
        name=HealthDependencyName.model,
        status=HealthDependencyStatus.unavailable,
        critical=True,
        latency_ms=None,
        checked_at=checked_at,
        details=HealthDependencyDetails(reason="no_model_provider_online"),
    )


def aggregate_overall_status(dependencies: list[HealthDependency]) -> HealthOverallStatus:
    has_degraded = any(dep.status == HealthDependencyStatus.degraded for dep in dependencies)
    has_unavailable_noncritical = any(
        dep.status == HealthDependencyStatus.unavailable and not dep.critical for dep in dependencies
    )
    has_unavailable_critical = any(
        dep.status == HealthDependencyStatus.unavailable and dep.critical for dep in dependencies
    )

    if has_unavailable_critical:
        return HealthOverallStatus.unhealthy
    if has_degraded or has_unavailable_noncritical:
        return HealthOverallStatus.degraded
    return HealthOverallStatus.healthy


def build_version_info(settings: HealthcheckSettings) -> VersionInfo:
    return VersionInfo(
        service=settings.service_name,
        api_version="v1",
        build=settings.build,
        commit=settings.commit,
        started_at=_STARTED_AT.isoformat(),
    )


def run_dependency_probes(settings: HealthcheckSettings) -> list[HealthDependency]:
    config_dep = probe_config(settings)

    with ThreadPoolExecutor(max_workers=3) as executor:
        postgres_future = executor.submit(probe_postgres, settings)
        llama_future = executor.submit(probe_llama_cpp, settings)
        provider_future = executor.submit(probe_provider, settings)

        postgres_dep = postgres_future.result()
        llama_dep = llama_future.result()
        provider_dep = provider_future.result()
    model_dep = probe_model(llama_dep, provider_dep)
    deps = [config_dep, postgres_dep, llama_dep, provider_dep, model_dep]

    logger.info(
        "health_probes",
        dependencies=[
            {
                "name": dep.name.value,
                "status": dep.status.value,
                "critical": dep.critical,
                "latencyMs": dep.latency_ms,
                "reason": (dep.details.reason if dep.details else None),
            }
            for dep in deps
        ],
    )

    return deps
