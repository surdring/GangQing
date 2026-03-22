from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from gangqing.app.main import create_app
from gangqing.common.auth import create_access_token


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise AssertionError(f"Missing required env for tests: {name}")
    return value


def test_sse_retry_events_include_reason_code_and_final_error() -> None:
    _require_env("GANGQING_DATABASE_URL")

    original_db = os.environ.get("GANGQING_DATABASE_URL")
    try:
        os.environ["GANGQING_DATABASE_URL"] = "postgresql+psycopg://user:password@127.0.0.1:1/gangqing"

        os.environ["GANGQING_TOOL_MAX_RETRIES"] = "1"
        os.environ["GANGQING_TOOL_BACKOFF_BASE_MS"] = "0"
        os.environ["GANGQING_TOOL_BACKOFF_MAX_MS"] = "0"
        os.environ["GANGQING_TOOL_BACKOFF_JITTER_RATIO"] = "0"

        app = create_app()
        client = TestClient(app)

        token, _ = create_access_token(
            user_id="u1",
            role="plant_manager",
            tenant_id="t1",
            project_id="p1",
        )

        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "slow"},
            headers={
                "X-Tenant-Id": "t1",
                "X-Project-Id": "p1",
                "X-Request-Id": "rid_sse_retry_1",
                "Authorization": f"Bearer {token}",
            },
        ) as resp:
            assert resp.status_code == 200
            events: list[dict] = []
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: ") :]))
    finally:
        if original_db is None:
            os.environ.pop("GANGQING_DATABASE_URL", None)
        else:
            os.environ["GANGQING_DATABASE_URL"] = original_db

    assert events
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "final"
    assert events[-1]["payload"]["status"] == "error"

    types = [str(e.get("type") or "") for e in events]
    error_positions = [idx for idx, t in enumerate(types) if t == "error"]
    assert error_positions, "Expected an error event when all attempts failed"
    assert error_positions[-1] == len(types) - 2, "Expected error event to be immediately before final"

    err_payload = events[error_positions[-1]].get("payload")
    assert isinstance(err_payload, dict)
    for required_key in ["code", "message", "retryable", "requestId"]:
        assert required_key in err_payload, f"Missing required key in error.payload: {required_key}"
    msg = str(err_payload.get("message") or "")
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in msg), "Expected ErrorResponse.message to be English"

    warning_events = [e for e in events if str(e.get("type") or "").strip() == "warning"]
    if warning_events:
        warning = warning_events[0]
        payload = warning.get("payload") or {}
        details = payload.get("details") or {}

        assert details.get("toolName")
        assert int(details.get("attempt") or 0) >= 1
        assert int(details.get("maxAttempts") or 0) >= 1
        assert str(details.get("reasonCode") or "").strip(), "Expected reasonCode in warning.details"
    else:
        tool_failure_events = [
            e
            for e in events
            if str(e.get("type") or "").strip() == "tool.result"
            and isinstance(e.get("payload"), dict)
            and e["payload"].get("status") == "failure"
        ]
        assert tool_failure_events, "Expected at least one tool.result failure event"
        first_failure = tool_failure_events[0]["payload"]
        assert str(first_failure.get("toolCallId") or "").strip()
        assert str(first_failure.get("toolName") or "").strip()
        err = first_failure.get("error")
        assert isinstance(err, dict)
        assert str(err.get("code") or "").strip()

    error_events = [e for e in events if e.get("type") == "error"]
    assert error_events, "Expected an error event when all attempts failed"
