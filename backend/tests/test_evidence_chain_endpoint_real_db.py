from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from gangqing.app.main import create_app
from gangqing.common.auth import create_access_token
from gangqing.common.context import RequestContext
from gangqing_db.evidence import Evidence, EvidenceTimeRange
from gangqing_db.evidence_store import upsert_evidence
from gangqing_db.audit_log import AuditLogEvent, insert_audit_log_event
from gangqing_db.settings import load_settings


def _require_database_url() -> str:
    settings = load_settings()
    if not settings.database_url.strip():
        raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL")
    return settings.database_url


def test_get_evidence_chain_by_request_id_returns_evidences_real_db() -> None:
    os.environ.setdefault("GANGQING_JWT_SECRET", "0123456789abcdef0123456789abcdef")
    _ = _require_database_url()

    app = create_app()
    client = TestClient(app)

    tenant_id = "t1"
    project_id = "p1"
    request_id = "rid_unit_evidence_chain_1"

    token, _ = create_access_token(
        user_id="admin_u",
        role="plant_manager",
        tenant_id=tenant_id,
        project_id=project_id,
    )

    ctx = RequestContext(
        requestId=request_id,
        tenantId=tenant_id,
        projectId=project_id,
        role="plant_manager",
        userId="admin_u",
    )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    ev = Evidence(
        evidenceId="e_test_1",
        sourceSystem="Postgres",
        sourceLocator={"tableOrView": "fact_production_daily"},
        timeRange=EvidenceTimeRange(start=now.replace(hour=0, minute=0, second=0), end=now),
        toolCallId="tc_test_1",
        lineageVersion=None,
        dataQualityScore=None,
        confidence="High",
        validation="verifiable",
        redactions=None,
    )
    upsert_evidence(ctx=ctx, request_id=request_id, evidence=ev, mode="append")

    insert_audit_log_event(
        AuditLogEvent(
            eventType="tool_call",
            requestId=request_id,
            tenantId=tenant_id,
            projectId=project_id,
            sessionId=None,
            userId="admin_u",
            role="plant_manager",
            resource="tool.postgres_readonly.query",
            actionSummary={
                "toolName": "tool.postgres_readonly.query",
                "toolCallId": "tc_test_1",
                "durationMs": 12,
                "argsSummary": {
                    "stage": "tool.execution",
                    "resultSummary": {"rowCount": 123, "truncated": False},
                },
            },
            result="success",
            errorCode=None,
            evidenceRefs=["e_test_1"],
        ),
        ctx=ctx,
    )

    resp = client.get(
        f"/api/v1/evidence/chains/{request_id}",
        headers={
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id,
            "Authorization": f"Bearer {token}",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    chain = body.get("evidenceChain") or {}
    evidences = chain.get("evidences")
    assert isinstance(evidences, list)
    assert any(isinstance(e, dict) and e.get("evidenceId") == "e_test_1" for e in evidences)

    tool_traces = chain.get("toolTraces")
    assert isinstance(tool_traces, list)
    assert any(
        isinstance(t, dict) and t.get("toolCallId") == "tc_test_1" for t in tool_traces
    ), f"Expected toolCallId tc_test_1 in toolTraces, got: {tool_traces}"

    matching = [t for t in tool_traces if isinstance(t, dict) and t.get("toolCallId") == "tc_test_1"]
    assert len(matching) == 1
    assert matching[0].get("resultSummary") == {"rowCount": 123, "truncated": False}
