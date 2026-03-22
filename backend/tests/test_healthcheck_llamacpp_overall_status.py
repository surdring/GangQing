from __future__ import annotations

from gangqing.common.healthcheck import (
    HealthDependency,
    HealthDependencyDetails,
    HealthDependencyName,
    HealthDependencyStatus,
    HealthOverallStatus,
    aggregate_overall_status,
    probe_model,
)


def _dep(
    *,
    name: HealthDependencyName,
    status: HealthDependencyStatus,
    critical: bool,
    reason: str | None = None,
) -> HealthDependency:
    details = None if reason is None else HealthDependencyDetails(reason=reason)
    return HealthDependency(
        name=name,
        status=status,
        critical=critical,
        latencyMs=None,
        checkedAt="2026-03-11T00:00:00Z",
        details=details,
    )


def test_overall_unhealthy_when_model_dependency_unavailable() -> None:
    llama = _dep(
        name=HealthDependencyName.llama_cpp,
        status=HealthDependencyStatus.unavailable,
        critical=False,
        reason="connection_failed",
    )
    provider = _dep(
        name=HealthDependencyName.provider,
        status=HealthDependencyStatus.unavailable,
        critical=False,
        reason="connection_failed",
    )
    model = probe_model(llama, provider)
    assert model.critical is True
    assert model.status == HealthDependencyStatus.unavailable

    overall = aggregate_overall_status([model])
    assert overall == HealthOverallStatus.unhealthy


def test_overall_degraded_when_llama_down_but_provider_ok() -> None:
    config = _dep(
        name=HealthDependencyName.config,
        status=HealthDependencyStatus.ok,
        critical=True,
        reason=None,
    )
    postgres = _dep(
        name=HealthDependencyName.postgres,
        status=HealthDependencyStatus.ok,
        critical=True,
        reason=None,
    )
    llama = _dep(
        name=HealthDependencyName.llama_cpp,
        status=HealthDependencyStatus.degraded,
        critical=False,
        reason="timeout",
    )
    provider = _dep(
        name=HealthDependencyName.provider,
        status=HealthDependencyStatus.ok,
        critical=False,
        reason=None,
    )
    model = probe_model(llama, provider)
    assert model.status == HealthDependencyStatus.ok

    overall = aggregate_overall_status([config, postgres, llama, provider, model])
    assert overall == HealthOverallStatus.degraded


def test_overall_unhealthy_when_llama_critical_and_unavailable() -> None:
    config = _dep(
        name=HealthDependencyName.config,
        status=HealthDependencyStatus.ok,
        critical=True,
        reason=None,
    )
    postgres = _dep(
        name=HealthDependencyName.postgres,
        status=HealthDependencyStatus.ok,
        critical=True,
        reason=None,
    )
    llama = _dep(
        name=HealthDependencyName.llama_cpp,
        status=HealthDependencyStatus.unavailable,
        critical=True,
        reason="connection_failed",
    )
    provider = _dep(
        name=HealthDependencyName.provider,
        status=HealthDependencyStatus.ok,
        critical=False,
        reason=None,
    )
    model = probe_model(llama, provider)
    assert model.status == HealthDependencyStatus.ok

    overall = aggregate_overall_status([config, postgres, llama, provider, model])
    assert overall == HealthOverallStatus.unhealthy


def test_overall_unhealthy_when_config_dependency_unavailable() -> None:
    config = _dep(
        name=HealthDependencyName.config,
        status=HealthDependencyStatus.unavailable,
        critical=True,
        reason="not_configured_model_provider_required",
    )
    overall = aggregate_overall_status([config])
    assert overall == HealthOverallStatus.unhealthy
