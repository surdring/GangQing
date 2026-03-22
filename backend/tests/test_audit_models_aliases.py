from __future__ import annotations

from datetime import datetime, timezone

from gangqing_db.audit_log import AuditError, AuditLogEvent
from gangqing_db.audit_query import AuditLogRecord


def test_audit_log_event_dump_uses_contract_aliases() -> None:
    event = AuditLogEvent(
        eventType="audit.query",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        requestId="rid_1",
        tenantId="t1",
        projectId="p1",
        sessionId=None,
        userId="u1",
        role="admin",
        resource="/api/v1/audit/events",
        correlationId="corr_1",
        supersedesEventId=None,
        actionSummary={"k": "v"},
        resultSummary={"durationMs": 1},
        toolCallId=None,
        stepId=None,
        error={"code": "FORBIDDEN", "message": "Forbidden"},
        result="success",
        errorCode=None,
        evidenceRefs=None,
    )

    dumped = event.model_dump(by_alias=True, mode="json")
    assert "eventType" in dumped and dumped["eventType"] == "audit.query"
    assert "requestId" in dumped and dumped["requestId"] == "rid_1"
    assert "tenantId" in dumped and dumped["tenantId"] == "t1"
    assert "projectId" in dumped and dumped["projectId"] == "p1"
    assert "result" in dumped and dumped["result"] == "success"
    assert "correlationId" in dumped and dumped["correlationId"] == "corr_1"
    assert "supersedesEventId" in dumped


def test_audit_log_record_uses_contract_aliases() -> None:
    record = AuditLogRecord(
        id="id1",
        eventType="audit.query",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        requestId="rid_1",
        tenantId="t1",
        projectId="p1",
        sessionId=None,
        userId="u1",
        role="admin",
        resource="/api/v1/audit/events",
        correlationId="corr_1",
        supersedesEventId=None,
        actionSummary={"query": {"requestId": "rid_1"}},
        result="success",
        errorCode=None,
        evidenceRefs=None,
    )

    dumped = record.model_dump(by_alias=True, mode="json")
    assert "eventType" in dumped and dumped["eventType"] == "audit.query"
    assert "result" in dumped and dumped["result"] == "success"
    assert dumped.get("correlationId") == "corr_1"


def test_audit_error_rejects_non_english_message() -> None:
    try:
        AuditError(code="INTERNAL_ERROR", message="中文错误")
    except ValueError as e:
        msg = str(e)
        assert "must be English" in msg
    else:
        raise AssertionError("Expected ValueError for non-English message")
