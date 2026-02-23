from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from gangqing.common.errors import AppError
from gangqing.tools.isolation import resolve_scope
from gangqing_db.errors import AuthError, EvidenceMismatchError, EvidenceMissingError, MigrationError, map_db_error
from gangqing_db.settings import load_settings


class MetricLineageScenarioResolveRequest(BaseModel):
    tenant_id: str | None = Field(default=None, alias="tenantId")
    project_id: str | None = Field(default=None, alias="projectId")
    metric_name: str = Field(min_length=1)
    scenario_key: str = Field(min_length=1, alias="scenarioKey")

    model_config = {"populate_by_name": True}


@dataclass(frozen=True)
class ScenarioMappingRecord:
    lineage_version: str
    status: str
    is_active: bool


def _engine_from_settings():
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def resolve_lineage_by_scenario(
    request: MetricLineageScenarioResolveRequest,
    *,
    ctx,
) -> ScenarioMappingRecord:
    try:
        try:
            tenant_id, project_id, _ = resolve_scope(
                ctx=ctx,
                tenant_id=request.tenant_id,
                project_id=request.project_id,
            )
        except AppError as e:
            raise AuthError(
                e.message,
                request_id=getattr(ctx, "request_id", None),
                details=e.details,
            ) from e

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

            rows = conn.execute(
                text(
                    """
                    SELECT lineage_version, status, is_active
                    FROM metric_lineage_scenario_mapping
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND metric_name = :metric_name
                      AND scenario_key = :scenario_key
                      AND is_active = true
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "metric_name": request.metric_name,
                    "scenario_key": request.scenario_key,
                },
            ).mappings().all()

            if not rows:
                raise EvidenceMissingError(
                    request.metric_name,
                    lineage_version=None,
                    request_id=ctx.request_id,
                )

            if len(rows) > 1:
                raise EvidenceMismatchError(
                    request.metric_name,
                    reason="scenario_mapping_conflict",
                    details={
                        "scenario_key": request.scenario_key,
                        "count": len(rows),
                    },
                    request_id=ctx.request_id,
                )

            row = rows[0]
            return ScenarioMappingRecord(
                lineage_version=str(row["lineage_version"]),
                status=str(row["status"]),
                is_active=bool(row["is_active"]),
            )

    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=ctx.request_id)
