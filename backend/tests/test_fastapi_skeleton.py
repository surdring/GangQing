from __future__ import annotations

import os
import json
import socket
import threading
import time

import pytest
from fastapi.testclient import TestClient

from gangqing.app.main import create_app
from gangqing.common.auth import create_access_token
from gangqing.api.chat import _build_error_payload
from gangqing.common.context import RequestContext
from gangqing.common.errors import AppError, ErrorCode


def test_sse_error_payload_contains_request_id() -> None:
    payload = _build_error_payload(
        ctx=RequestContext(requestId="rid_sse_err", tenantId="t1", projectId="p1"),
        error=AppError(
            ErrorCode.AUTH_ERROR,
            "Missing Authorization header",
            request_id="rid_sse_err",
            details=None,
            retryable=False,
        ),
    )
    assert payload["requestId"] == "rid_sse_err"


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise AssertionError(f"Missing required env for tests: {name}")
    return value


def _deps_by_name(dependencies: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for dep in dependencies:
        dep_name = str(dep.get("name") or "")
        if dep_name:
            out[dep_name] = dep
    return out


def _start_blackhole_http_server() -> tuple[str, int, threading.Thread, threading.Event]:
    stop_event = threading.Event()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(50)
    host, port = sock.getsockname()

    def run() -> None:
        sock.settimeout(0.2)
        conns: list[socket.socket] = []
        try:
            while not stop_event.is_set():
                try:
                    conn, _ = sock.accept()
                    conn.settimeout(0.2)
                    conns.append(conn)
                except TimeoutError:
                    continue
                except OSError:
                    break
        finally:
            for c in conns:
                try:
                    c.close()
                except Exception:
                    pass
            try:
                sock.close()
            except Exception:
                pass

    t = threading.Thread(target=run, name="blackhole-http", daemon=True)
    t.start()
    return str(host), int(port), t, stop_event


def _assert_no_sensitive_leak(text: str) -> None:
    lowered = text.lower()
    forbidden_fragments = [
        "postgresql://",
        "psycopg://",
        "password",
        "secret",
        "sk-",
        "nvapi-",
        "127.0.0.1:5432",
    ]
    for frag in forbidden_fragments:
        assert frag not in lowered


def test_health_ok() -> None:
    app = create_app()
    client = TestClient(app)

    _require_env("GANGQING_DATABASE_URL")

    resp = client.get(
        "/api/v1/health",
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1"},
    )

    assert resp.status_code in {200, 503}
    body = resp.json()
    assert body["status"] in {"healthy", "degraded", "unhealthy"}
    assert body["requestId"].strip()
    assert body["version"]["service"]
    assert body["version"]["apiVersion"] == "v1"
    assert isinstance(body["dependencies"], list)

    deps = _deps_by_name(body["dependencies"])
    assert deps["config"]["status"] in {"ok", "unavailable", "degraded"}
    assert deps["config"]["critical"] is True
    assert deps["postgres"]["status"] in {"ok", "unavailable", "degraded"}
    assert deps["postgres"]["critical"] is True
    assert deps["llama_cpp"]["status"] in {"ok", "unavailable", "degraded"}
    assert deps["provider"]["status"] in {"ok", "unavailable", "degraded"}
    assert deps["model"]["status"] in {"ok", "unavailable", "degraded"}
    assert deps["model"]["critical"] is True
    assert "X-Request-Id" in resp.headers
    assert resp.headers["X-Request-Id"].strip()

    _assert_no_sensitive_leak(json.dumps(body, ensure_ascii=False))


def test_health_unhealthy_when_database_url_missing() -> None:
    app = create_app()
    client = TestClient(app)

    original = os.environ.pop("GANGQING_DATABASE_URL", None)
    try:
        resp = client.get(
            "/api/v1/health",
            headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_h_missing_db"},
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["requestId"] == "rid_h_missing_db"
        deps = _deps_by_name(body["dependencies"])
        assert deps["config"]["status"] == "unavailable"

        _assert_no_sensitive_leak(json.dumps(body, ensure_ascii=False))
    finally:
        if original is not None:
            os.environ["GANGQING_DATABASE_URL"] = original


def test_health_unhealthy_when_no_model_provider_configured() -> None:
    app = create_app()
    client = TestClient(app)

    original_llama = os.environ.pop("GANGQING_LLAMACPP_BASE_URL", None)
    original_provider = os.environ.pop("GANGQING_PROVIDER_HEALTHCHECK_URL", None)
    try:
        resp = client.get(
            "/api/v1/health",
            headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_h_missing_model"},
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "unhealthy"
        deps = _deps_by_name(body["dependencies"])
        assert deps["config"]["status"] == "unavailable"
        assert deps["model"]["status"] == "unavailable"

        _assert_no_sensitive_leak(json.dumps(body, ensure_ascii=False))
    finally:
        if original_llama is not None:
            os.environ["GANGQING_LLAMACPP_BASE_URL"] = original_llama
        if original_provider is not None:
            os.environ["GANGQING_PROVIDER_HEALTHCHECK_URL"] = original_provider


def test_missing_tenant_header_returns_auth_error() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/v1/health", headers={"X-Project-Id": "p1"})

    assert resp.status_code == 401
    body = resp.json()
    assert sorted(body.keys()) == ["code", "details", "message", "requestId", "retryable"]
    assert body["code"] == "AUTH_ERROR"
    assert body["requestId"].strip()
    assert body["details"] == {"header": "X-Tenant-Id"}

    _assert_no_sensitive_leak(json.dumps(body, ensure_ascii=False))


def test_missing_project_header_returns_auth_error() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/v1/health", headers={"X-Tenant-Id": "t1"})

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_ERROR"
    assert body["requestId"].strip()
    assert body["details"] == {"header": "X-Project-Id"}

    _assert_no_sensitive_leak(json.dumps(body, ensure_ascii=False))


def test_llamacpp_timeout_dependency_details_are_structured() -> None:
    host, port, thread, stop_event = _start_blackhole_http_server()
    try:
        os.environ["GANGQING_LLAMACPP_BASE_URL"] = f"http://{host}:{port}/v1"
        os.environ["GANGQING_LLAMACPP_HEALTH_PATH"] = "/models"
        os.environ["GANGQING_LLAMACPP_TIMEOUT_SECONDS"] = "0.2"
        os.environ["GANGQING_LLAMACPP_TRUST_ENV"] = "false"

        from gangqing.common.healthcheck import load_healthcheck_settings, probe_llama_cpp

        dep = probe_llama_cpp(load_healthcheck_settings())
        assert dep.name.value == "llama_cpp"
        assert dep.status.value == "unavailable"
        assert dep.details is not None
        assert dep.details.reason == "timeout"
        assert dep.details.error_class
        assert dep.details.missing_keys is None
    finally:
        stop_event.set()
        thread.join(timeout=1.0)


def test_provider_timeout_dependency_details_are_structured() -> None:
    host, port, thread, stop_event = _start_blackhole_http_server()
    try:
        os.environ["GANGQING_PROVIDER_HEALTHCHECK_URL"] = f"http://{host}:{port}/health"
        os.environ["GANGQING_PROVIDER_TIMEOUT_SECONDS"] = "0.2"
        os.environ["GANGQING_PROVIDER_TRUST_ENV"] = "false"

        from gangqing.common.healthcheck import load_healthcheck_settings, probe_provider

        dep = probe_provider(load_healthcheck_settings())
        assert dep.name.value == "provider"
        assert dep.status.value == "unavailable"
        assert dep.details is not None
        assert dep.details.reason == "timeout"
        assert dep.details.error_class
        assert dep.details.missing_keys is None
    finally:
        stop_event.set()
        thread.join(timeout=1.0)


def test_request_id_is_generated_when_missing() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.get(
        "/api/v1/health",
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1"},
    )

    assert resp.status_code in {200, 503}
    assert resp.headers.get("X-Request-Id")
    assert resp.headers["X-Request-Id"].strip()


def test_request_id_is_echoed_when_provided() -> None:
    app = create_app()
    client = TestClient(app)

    request_id = "rid_test_123"
    resp = client.get(
        "/api/v1/health",
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": request_id,
        },
    )

    assert resp.status_code in {200, 503}
    assert resp.headers.get("X-Request-Id") == request_id


def test_auth_error_uses_provided_request_id() -> None:
    app = create_app()
    client = TestClient(app)

    request_id = "rid_test_456"
    resp = client.get(
        "/api/v1/health",
        headers={
            "X-Project-Id": "p1",
            "X-Request-Id": request_id,
        },
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_ERROR"
    assert body["requestId"] == request_id
    assert resp.headers.get("X-Request-Id") == request_id


def test_structured_log_contains_request_id(capfd) -> None:
    app = create_app()
    client = TestClient(app)

    client.get(
        "/api/v1/health",
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_log_1"},
    )

    out, _ = capfd.readouterr()
    log_lines = [line.strip() for line in out.splitlines() if line.strip()]
    json_lines = []
    for line in log_lines:
        try:
            json_lines.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    http_events = [obj for obj in json_lines if obj.get("event") == "http_request"]
    assert http_events
    assert any(obj.get("requestId") == "rid_log_1" for obj in http_events)
    assert any(obj.get("tenantId") == "t1" for obj in http_events)
    assert any(obj.get("projectId") == "p1" for obj in http_events)


def test_sse_stream_event_sequence_and_request_id() -> None:
    app = create_app()
    client = TestClient(app)

    token, _ = create_access_token(
        user_id="u1",
        role="dispatcher",
        tenant_id="t1",
        project_id="p1",
    )

    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": "rid_sse_1",
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

    assert events
    assert events[0]["type"] == "meta"
    assert events[0]["requestId"] == "rid_sse_1"
    assert events[-1]["type"] == "final"


def test_sse_stream_requires_role() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_sse_2"},
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "AUTH_ERROR"
    assert body["requestId"] == "rid_sse_2"


def test_metrics_endpoint_contains_http_snapshot() -> None:
    app = create_app()
    client = TestClient(app)

    client.get(
        "/api/v1/health",
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_m_1"},
    )

    resp = client.get(
        "/api/v1/metrics",
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_m_2"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "http" in body
    assert "duration" in body["http"]
    assert "count" in body["http"]["duration"]
