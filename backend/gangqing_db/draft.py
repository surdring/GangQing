from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from gangqing_db.errors import MigrationError, map_db_error
from gangqing_db.settings import load_settings


class DraftRecord(BaseModel):
    draft_id: str = Field(min_length=1, alias="draftId")
    tenant_id: str = Field(min_length=1, alias="tenantId")
    project_id: str = Field(min_length=1, alias="projectId")
    payload: dict[str, Any]
    created_at: datetime = Field(alias="createdAt")

    model_config = {"populate_by_name": True}


def _engine_from_settings():
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def insert_draft(*, draft_id: str, payload: dict[str, Any], ctx: Any) -> None:
    try:
        engine = _engine_from_settings()
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": getattr(ctx, "tenant_id")},
                )
                conn.execute(
                    text("SELECT set_config('app.current_project', :p, true)"),
                    {"p": getattr(ctx, "project_id")},
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO draft(
                            tenant_id,
                            project_id,
                            draft_id,
                            payload
                        ) VALUES (
                            :tenant_id,
                            :project_id,
                            :draft_id,
                            CAST(:payload AS jsonb)
                        )
                        """
                    ),
                    {
                        "tenant_id": getattr(ctx, "tenant_id"),
                        "project_id": getattr(ctx, "project_id"),
                        "draft_id": draft_id,
                        "payload": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    },
                )
    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))


def get_draft_by_id(*, draft_id: str, ctx: Any) -> DraftRecord | None:
    try:
        engine = _engine_from_settings()
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": getattr(ctx, "tenant_id")},
                )
                conn.execute(
                    text("SELECT set_config('app.current_project', :p, true)"),
                    {"p": getattr(ctx, "project_id")},
                )

                row = conn.execute(
                    text(
                        """
                        SELECT draft_id, tenant_id, project_id, payload, created_at
                        FROM draft
                        WHERE tenant_id = :tenant_id AND project_id = :project_id AND draft_id = :draft_id
                        """
                    ),
                    {
                        "tenant_id": getattr(ctx, "tenant_id"),
                        "project_id": getattr(ctx, "project_id"),
                        "draft_id": draft_id,
                    },
                ).mappings().first()

                if row is None:
                    return None

                obj = {
                    "draftId": row.get("draft_id"),
                    "tenantId": row.get("tenant_id"),
                    "projectId": row.get("project_id"),
                    "payload": dict(row.get("payload") or {}),
                    "createdAt": row.get("created_at"),
                }
                return DraftRecord.model_validate(obj)
    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))
