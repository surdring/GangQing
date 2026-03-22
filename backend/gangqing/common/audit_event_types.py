from __future__ import annotations

from enum import Enum


class AuditEventType(str, Enum):
    RESPONSE = "response"
    API_RESPONSE = "api.response"
    AUTH_DENIED = "auth.denied"
    RBAC_DENIED = "rbac.denied"
    GUARDRAIL_HIT = "guardrail.hit"
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILURE = "login.failure"
    TOOL_CALL = "tool.call"
    TOOL_CALL_START = "tool.call"
    TOOL_RESULT = "tool.result"
    TOOL_RESULT_END = "tool.result"
    TOOL_CALL_AUDIT = "tool_call"
    QUERY = "query"
    AUDIT_QUERY = "audit.query"
    ERROR = "error"
    DATA_MASKED = "data.masked"
    DATA_UNMASK = "data.unmask"
    # Mapping events for aggregation gate (T56.3)
    MAPPING_CONFLICT_DETECTED = "mapping.conflict_detected"
    MAPPING_CONFLICT_RESOLVED = "mapping.conflict_resolved"
    MAPPING_AGGREGATION_BLOCKED = "mapping.aggregation_blocked"
