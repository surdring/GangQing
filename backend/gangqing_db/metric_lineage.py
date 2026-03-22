from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, text

from gangqing.common.errors import AppError
from gangqing.tools.isolation import resolve_scope
from gangqing_db.audit_log import AuditLogEvent, insert_audit_log_event
from gangqing_db.errors import (
    AuthError,
    EvidenceMismatchError,
    EvidenceMissingError,
    ForbiddenError,
    MigrationError,
    map_db_error,
)
from gangqing_db.evidence import Evidence
from gangqing_db.metric_lineage_scenario_mapping import (
    MetricLineageScenarioResolveRequest,
    resolve_lineage_by_scenario,
)
from gangqing_db.settings import load_settings


_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


MetricLineageStatusLiteral = Literal["draft", "active", "deprecated", "retired"]


MetricLineageBindingMethodLiteral = Literal[
    "user_specified",
    "default_active",
]


class MetricLineageRecord(BaseModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    project_id: str = Field(alias="projectId")
    metric_name: str
    lineage_version: str = Field(alias="lineageVersion")
    status: MetricLineageStatusLiteral
    formula: str | None = None
    source_systems: list[str] | None = None
    owner: str | None = None
    is_active: bool
    created_at: datetime | None = None

    model_config = {"populate_by_name": True}


class MetricLineageBindingRequest(BaseModel):
    tenant_id: str | None = Field(default=None, alias="tenantId")
    project_id: str | None = Field(default=None, alias="projectId")
    metric_name: str = Field(min_length=1)
    lineage_version: str | None = Field(default=None, alias="lineageVersion")
    scenario_key: str | None = Field(default=None, alias="scenarioKey")

    model_config = {"populate_by_name": True}

    @field_validator("lineage_version")
    @classmethod
    def validate_lineage_version_semver(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        if not _SEMVER_RE.match(value):
            raise ValueError("lineageVersion must be SemVer (X.Y.Z)")
        return value


class MetricLineageBindingDecision(BaseModel):
    metric_name: str
    lineage_version: str = Field(alias="lineageVersion")
    method: MetricLineageBindingMethodLiteral

    model_config = {"populate_by_name": True}


class MetricLineageQuery(BaseModel):
    tenant_id: str | None = Field(default=None, alias="tenantId")
    project_id: str | None = Field(default=None, alias="projectId")
    metric_name: str = Field(min_length=1)
    lineage_version: str | None = Field(default=None, alias="lineageVersion")

    model_config = {"populate_by_name": True}

    @field_validator("lineage_version")
    @classmethod
    def validate_lineage_version_semver(cls, v: str | None) -> str | None:
        if v is None:
            return None
        value = v.strip()
        if not _SEMVER_RE.match(value):
            raise ValueError("lineageVersion must be SemVer (X.Y.Z)")
        return value


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    tenant_id: str
    project_id: str
    capabilities: set[str]


_REQUIRED_CAPABILITY = "metric:lineage:read"


def _require_capability(ctx: RequestContext) -> None:
    if _REQUIRED_CAPABILITY not in ctx.capabilities:
        raise ForbiddenError(_REQUIRED_CAPABILITY, request_id=ctx.request_id)


def _require_scope(ctx: RequestContext) -> None:
    if not ctx.tenant_id or not ctx.project_id:
        raise AuthError(
            "Authentication context missing tenantId/projectId",
            request_id=ctx.request_id,
        )


def _resolve_default_scope(
    *,
    ctx: RequestContext,
    tenant_id: str | None,
    project_id: str | None,
) -> tuple[str, str, str]:
    try:
        return resolve_scope(ctx=ctx, tenant_id=tenant_id, project_id=project_id)
    except AppError as e:
        raise AuthError(
            e.message,
            request_id=ctx.request_id,
            details=e.details,
        ) from e


def _engine_from_settings():
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_metric_lineage(
    query: MetricLineageQuery,
    *,
    ctx: RequestContext,
) -> MetricLineageRecord:
    """Get metric lineage record by metric_name + lineage_version.

    Rules:
    - If lineage_version is provided: must exist exactly one record.
    - If lineage_version is missing: allowed only when there is exactly one active record.
    """

    _require_scope(ctx)
    _require_capability(ctx)

    tenant_id, project_id, _ = _resolve_default_scope(
        ctx=ctx,
        tenant_id=query.tenant_id,
        project_id=query.project_id,
    )

    try:
        engine = _engine_from_settings()

        with engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": ctx.tenant_id},
            )
            conn.execute(
                text("SELECT set_config('app.current_project', :p, true)"),
                {"p": ctx.project_id},
            )
            conn.commit()

            if query.lineage_version is not None:
                rows = conn.execute(
                    text(
                        """
                        SELECT
                            id::text,
                            tenant_id,
                            project_id,
                            metric_name,
                            lineage_version,
                            status,
                            formula,
                            source_systems,
                            owner,
                            is_active,
                            created_at
                        FROM metric_lineage
                        WHERE tenant_id = :tenant_id
                          AND project_id = :project_id
                          AND metric_name = :metric_name
                          AND lineage_version = :lineage_version
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "metric_name": query.metric_name,
                        "lineage_version": query.lineage_version,
                    },
                ).mappings().all()

                if not rows:
                    raise EvidenceMissingError(
                        query.metric_name,
                        lineage_version=query.lineage_version,
                        request_id=ctx.request_id,
                    )

                if len(rows) > 1:
                    raise EvidenceMismatchError(
                        query.metric_name,
                        reason="duplicate_metric_lineage",
                        details={"count": len(rows)},
                        request_id=ctx.request_id,
                    )

                return MetricLineageRecord(**dict(rows[0]))

            active_rows = conn.execute(
                text(
                    """
                    SELECT
                        id::text,
                        tenant_id,
                        project_id,
                        metric_name,
                        lineage_version,
                        status,
                        formula,
                        source_systems,
                        owner,
                        is_active,
                        created_at
                    FROM metric_lineage
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND metric_name = :metric_name
                      AND is_active = true
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "metric_name": query.metric_name,
                },
            ).mappings().all()

            if not active_rows:
                raise EvidenceMissingError(
                    query.metric_name,
                    lineage_version=None,
                    request_id=ctx.request_id,
                )

            if len(active_rows) > 1:
                raise EvidenceMismatchError(
                    query.metric_name,
                    reason="multiple_active_lineage_versions",
                    details={"count": len(active_rows)},
                    request_id=ctx.request_id,
                )

            return MetricLineageRecord(**dict(active_rows[0]))

    except MigrationError:
        raise
    except Exception as e:
        mapped = map_db_error(e, request_id=ctx.request_id)
        raise mapped


def bind_metric_lineage_for_computation(
    request: MetricLineageBindingRequest,
    *,
    ctx: RequestContext,
    allow_default_active: bool = False,
    allow_inactive: bool = False,
    allow_deprecated: bool = False,
    data_time_range: dict[str, datetime] | None = None,
    audit: bool = True,
) -> tuple[MetricLineageRecord, MetricLineageBindingDecision, Evidence]:
    _require_scope(ctx)
    _require_capability(ctx)

    tenant_id, project_id, scope_mode = _resolve_default_scope(
        ctx=ctx,
        tenant_id=request.tenant_id,
        project_id=request.project_id,
    )

    try:
        resolved_by: str

        if request.lineage_version is not None:
            resolved_by = "user_specified"
            record = get_metric_lineage(
                MetricLineageQuery(
                    tenantId=tenant_id,
                    projectId=project_id,
                    metric_name=request.metric_name,
                    lineageVersion=request.lineage_version,
                ),
                ctx=ctx,
            )
            decision = MetricLineageBindingDecision(
                metric_name=request.metric_name,
                lineageVersion=record.lineage_version,
                method="user_specified",
            )
        elif request.scenario_key is not None:
            resolved_by = "scenario_mapping"
            mapping = resolve_lineage_by_scenario(
                MetricLineageScenarioResolveRequest(
                    tenantId=tenant_id,
                    projectId=project_id,
                    metric_name=request.metric_name,
                    scenarioKey=request.scenario_key,
                ),
                ctx=ctx,
            )
            record = get_metric_lineage(
                MetricLineageQuery(
                    tenantId=tenant_id,
                    projectId=project_id,
                    metric_name=request.metric_name,
                    lineageVersion=mapping.lineage_version,
                ),
                ctx=ctx,
            )
            decision = MetricLineageBindingDecision(
                metric_name=request.metric_name,
                lineageVersion=record.lineage_version,
                method="user_specified",
            )
        else:
            if not allow_default_active:
                raise EvidenceMismatchError(
                    request.metric_name,
                    reason="lineage_version_required",
                    details={
                        "hint": "Specify lineageVersion explicitly or provide scenarioKey",
                    },
                    request_id=ctx.request_id,
                )
            resolved_by = "default_active"
            record = get_metric_lineage(
                MetricLineageQuery(
                    tenantId=tenant_id,
                    projectId=project_id,
                    metric_name=request.metric_name,
                    lineageVersion=None,
                ),
                ctx=ctx,
            )
            decision = MetricLineageBindingDecision(
                metric_name=request.metric_name,
                lineageVersion=record.lineage_version,
                method="default_active",
            )

        if not allow_inactive and not record.is_active:
            raise EvidenceMismatchError(
                request.metric_name,
                reason="lineage_version_not_active",
                details={"lineage_version": record.lineage_version, "status": record.status},
                request_id=ctx.request_id,
            )

        if record.status == "deprecated" and not allow_deprecated:
            raise EvidenceMismatchError(
                request.metric_name,
                reason="lineage_version_deprecated",
                details={"lineage_version": record.lineage_version},
                request_id=ctx.request_id,
            )

        if data_time_range is not None:
            time_range = data_time_range
        else:
            if record.created_at is None:
                raise EvidenceMismatchError(
                    request.metric_name,
                    reason="evidence_time_range_unavailable",
                    details={"lineage_version": record.lineage_version},
                    request_id=ctx.request_id,
                )
            time_range = {
                "start": record.created_at,
                "end": record.created_at + timedelta(microseconds=1),
            }

        evidence = Evidence(
            evidenceId=f"metric_lineage:{record.metric_name}:{record.lineage_version}",
            sourceSystem="Manual",
            sourceLocator={"table": "metric_lineage", "id": record.id},
            timeRange=time_range,
            lineageVersion=build_evidence_lineage_version(record),
            dataQualityScore=None,
            confidence="High",
            validation="verifiable",
            redactions=None,
        )

        if audit:
            insert_audit_log_event(
                AuditLogEvent(
                    event_type="query",
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                    project_id=ctx.project_id,
                    resource="metric_lineage_binding",
                    action_summary={
                        "scopeFilter": {
                            "tenantId": ctx.tenant_id,
                            "projectId": ctx.project_id,
                            "mode": scope_mode,
                            "policyVersion": "v1",
                        },
                        "metric_name": request.metric_name,
                        "requested_lineage_version": request.lineage_version,
                        "scenario_key": request.scenario_key,
                        "bound_lineage_version": record.lineage_version,
                        "method": decision.method,
                        "resolved_by": resolved_by,
                        "status": record.status,
                        "allow_default_active": allow_default_active,
                        "allow_inactive": allow_inactive,
                        "allow_deprecated": allow_deprecated,
                    },
                    result_status="success",
                    error_code=None,
                    evidence_refs=[evidence.evidence_id],
                ),
                ctx=ctx,
            )

        return record, decision, evidence

    except MigrationError as e:
        if audit:
            try:
                insert_audit_log_event(
                    AuditLogEvent(
                        event_type="query",
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        resource="metric_lineage_binding",
                        action_summary={
                            "scopeFilter": {
                                "tenantId": ctx.tenant_id,
                                "projectId": ctx.project_id,
                                "mode": scope_mode,
                                "policyVersion": "v1",
                            },
                            "metric_name": request.metric_name,
                            "requested_lineage_version": request.lineage_version,
                            "scenario_key": request.scenario_key,
                            "allow_default_active": allow_default_active,
                            "allow_inactive": allow_inactive,
                            "allow_deprecated": allow_deprecated,
                        },
                        result_status="failure",
                        error_code=e.code.value,
                        evidence_refs=None,
                    ),
                    ctx=ctx,
                )
            except Exception:
                pass
        raise
    except Exception as e:
        mapped = map_db_error(e, request_id=ctx.request_id)
        if audit:
            try:
                insert_audit_log_event(
                    AuditLogEvent(
                        event_type="query",
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                        project_id=ctx.project_id,
                        resource="metric_lineage_binding",
                        action_summary={
                            "scopeFilter": {
                                "tenantId": ctx.tenant_id,
                                "projectId": ctx.project_id,
                                "mode": scope_mode,
                                "policyVersion": "v1",
                            },
                            "metric_name": request.metric_name,
                            "requested_lineage_version": request.lineage_version,
                            "scenario_key": request.scenario_key,
                            "allow_default_active": allow_default_active,
                            "allow_inactive": allow_inactive,
                            "allow_deprecated": allow_deprecated,
                        },
                        result_status="failure",
                        error_code=mapped.code.value,
                        evidence_refs=None,
                    ),
                    ctx=ctx,
                )
            except Exception:
                pass
        raise mapped


def build_evidence_lineage_version(record: MetricLineageRecord) -> str:
    """Return the external Evidence lineageVersion value.

    This is the authoritative mapping between metric_lineage.lineage_version and Evidence.lineageVersion.
    """

    return record.lineage_version
