from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from gangqing.common.context import RequestContext
from gangqing_db.evidence import Evidence
from gangqing_db.evidence_chain import EvidenceWarning, merge_evidence_update
from gangqing_db.errors import MigrationError, map_db_error
from gangqing_db.settings import load_settings


class EvidenceStoreRecord(BaseModel):
    request_id: str = Field(alias="requestId")
    evidence_id: str = Field(alias="evidenceId")
    payload: dict[str, Any]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


def _engine_from_settings():
    settings = load_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def _set_rls_context(conn, *, tenant_id: str, project_id: str) -> None:
    conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tenant_id})
    conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": project_id})


def upsert_evidence(
    *,
    ctx: RequestContext,
    request_id: str,
    evidence: Evidence,
    mode: str,
) -> list[EvidenceWarning]:
    try:
        engine = _engine_from_settings()
        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=ctx.tenant_id, project_id=ctx.project_id)
            conn.commit()

            existing_payload: dict[str, Any] | None = None
            existing_row = conn.execute(
                text(
                    """
                    SELECT payload
                    FROM evidence_store
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND request_id = :request_id
                      AND evidence_id = :evidence_id
                    """
                ),
                {
                    "tenant_id": ctx.tenant_id,
                    "project_id": ctx.project_id,
                    "request_id": request_id,
                    "evidence_id": evidence.evidence_id,
                },
            ).mappings().one_or_none()
            if existing_row is not None:
                raw = existing_row.get("payload")
                if isinstance(raw, dict):
                    existing_payload = raw
                elif raw is not None:
                    try:
                        existing_payload = json.loads(raw)
                    except Exception:
                        existing_payload = None

            warnings: list[EvidenceWarning] = []
            payload_obj = evidence.model_dump(by_alias=True, mode="json")

            if mode == "update" and existing_payload is not None:
                try:
                    existing_evidence = Evidence.model_validate(existing_payload)
                    merged, merge_warnings = merge_evidence_update(
                        request_id=request_id,
                        existing=existing_evidence,
                        update=evidence,
                    )
                    warnings.extend(merge_warnings)
                    payload_obj = merged.model_dump(by_alias=True, mode="json")
                except Exception:
                    payload_obj = evidence.model_dump(by_alias=True, mode="json")

            conn.execute(
                text(
                    """
                    INSERT INTO evidence_store(
                        tenant_id,
                        project_id,
                        request_id,
                        evidence_id,
                        payload
                    ) VALUES (
                        :tenant_id,
                        :project_id,
                        :request_id,
                        :evidence_id,
                        CAST(:payload AS jsonb)
                    )
                    ON CONFLICT (tenant_id, project_id, request_id, evidence_id)
                    DO UPDATE SET
                        payload = EXCLUDED.payload,
                        updated_at = now();
                    """
                ),
                {
                    "tenant_id": ctx.tenant_id,
                    "project_id": ctx.project_id,
                    "request_id": request_id,
                    "evidence_id": evidence.evidence_id,
                    "payload": json.dumps(payload_obj, ensure_ascii=False, sort_keys=True),
                },
            )
            conn.commit()
            return warnings

    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))


def list_evidences_by_request_id(
    *,
    ctx: RequestContext,
    request_id: str,
) -> list[Evidence]:
    try:
        engine = _engine_from_settings()
        with engine.connect() as conn:
            _set_rls_context(conn, tenant_id=ctx.tenant_id, project_id=ctx.project_id)
            conn.commit()
            rows = conn.execute(
                text(
                    """
                    SELECT evidence_id, payload
                    FROM evidence_store
                    WHERE tenant_id = :tenant_id
                      AND project_id = :project_id
                      AND request_id = :request_id
                    ORDER BY evidence_id ASC
                    """
                ),
                {
                    "tenant_id": ctx.tenant_id,
                    "project_id": ctx.project_id,
                    "request_id": request_id,
                },
            ).mappings().all()

            evidences: list[Evidence] = []
            for r in rows:
                payload = r.get("payload")
                if isinstance(payload, dict):
                    evidences.append(Evidence.model_validate(payload))
                elif payload is not None:
                    evidences.append(Evidence.model_validate(json.loads(payload)))
            return evidences

    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))
