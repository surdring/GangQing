from __future__ import annotations

import os

from fastapi.testclient import TestClient

from gangqing.app.main import create_app
from gangqing.common.auth import create_access_token


def test_maintainer_access_finance_returns_forbidden() -> None:
    os.environ.setdefault("GANGQING_JWT_SECRET", "0123456789abcdef0123456789abcdef")

    app = create_app()
    client = TestClient(app)

    token, _ = create_access_token(
        user_id="u1",
        role="maintainer",
        tenant_id="t1",
        project_id="p1",
    )

    resp = client.get(
        "/api/v1/finance/reports/summary",
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": "rid_rbac_1",
            "Authorization": f"Bearer {token}",
        },
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "FORBIDDEN"
    assert body["requestId"] == "rid_rbac_1"
    assert body["details"]["capability"] == "finance:report:read"
