from __future__ import annotations

from enum import Enum


class AuditEventType(str, Enum):
    API_RESPONSE = "api.response"
    AUTH_DENIED = "auth.denied"
    RBAC_DENIED = "rbac.denied"
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILURE = "login.failure"
    TOOL_CALL = "tool_call"
    QUERY = "query"
    DATA_MASKED = "data.masked"
    DATA_UNMASK = "data.unmask"
