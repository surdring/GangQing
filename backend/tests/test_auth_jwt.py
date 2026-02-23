from __future__ import annotations

import time

from fastapi.testclient import TestClient

from gangqing.app.main import create_app
from gangqing.common.auth import create_access_token
from gangqing.common.errors import ErrorCode


def test_login_invalid_credentials_returns_auth_error() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "u1", "password": "bad"},
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_t1"},
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_ERROR.value


def test_protected_endpoint_rejects_non_bearer_scheme() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": "rid_non_bearer_1",
            "Authorization": "Token abc",
        },
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_ERROR.value
    assert body["message"] == "Invalid Authorization header"
    assert body["requestId"] == "rid_non_bearer_1"


def test_missing_tenant_header_returns_auth_error() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "u1", "password": "bad"},
        headers={"X-Project-Id": "p1", "X-Request-Id": "rid_missing_tenant"},
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_ERROR.value
    assert body["requestId"] == "rid_missing_tenant"


def test_missing_project_header_returns_auth_error() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "u1", "password": "bad"},
        headers={"X-Tenant-Id": "t1", "X-Request-Id": "rid_missing_project"},
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_ERROR.value
    assert body["requestId"] == "rid_missing_project"


def test_protected_endpoint_requires_token() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_t2"},
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_ERROR.value


def test_expired_token_returns_auth_error(monkeypatch) -> None:
    app = create_app()
    client = TestClient(app)

    token, exp = create_access_token(
        user_id="admin",
        role="plant_manager",
        tenant_id="t1",
        project_id="p1",
    )
    monkeypatch.setattr(time, "time", lambda: float(exp + 1))

    resp = client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": "rid_t3",
            "Authorization": f"Bearer {token}",
        },
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_ERROR.value
    assert body["message"] in {"Token expired", "Invalid token"}


def test_token_scope_mismatch_returns_auth_error() -> None:
    app = create_app()
    client = TestClient(app)

    token, _ = create_access_token(
        user_id="admin",
        role="plant_manager",
        tenant_id="t_other",
        project_id="p_other",
    )

    resp = client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": "rid_t4",
            "Authorization": f"Bearer {token}",
        },
    )

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_ERROR.value
    assert body["message"] == "Invalid token scope"


def test_login_success_and_access_protected_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("GANGQING_BOOTSTRAP_ADMIN_USER_ID", "admin")
    monkeypatch.setenv("GANGQING_BOOTSTRAP_ADMIN_PASSWORD", "admin_password")

    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin_password"},
        headers={"X-Tenant-Id": "t1", "X-Project-Id": "p1", "X-Request-Id": "rid_t5"},
    )

    assert resp.status_code == 200
    body = resp.json()
    token = body["accessToken"]

    resp2 = client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": "rid_t6",
            "Authorization": f"Bearer {token}",
        },
    )
    assert resp2.status_code == 200
