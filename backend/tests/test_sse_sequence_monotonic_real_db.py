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


def test_sse_sequence_is_strictly_monotonic_increasing_real_db() -> None:
    _require_env("GANGQING_DATABASE_URL")

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
        json={"message": "query"},
        headers={
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": "rid_sse_seq_1",
            "Authorization": f"Bearer {token}",
        },
    ) as resp:
        assert resp.status_code == 200
        events: list[dict] = []
        for line in resp.iter_lines():
            if not line:
                continue
            if not line.startswith("data: "):
                continue
            events.append(json.loads(line[len("data: ") :]))

    assert events, "Expected at least one SSE event"

    assert str(events[0].get("type") or "") == "meta"
    assert str(events[-1].get("type") or "") == "final"
    assert any(str(e.get("type") or "") == "message.delta" for e in events)

    sequences: list[int] = []
    for e in events:
        seq = e.get("sequence")
        assert isinstance(seq, int), f"Expected int sequence, got: {type(seq)}"
        sequences.append(seq)

    for prev, cur in zip(sequences, sequences[1:]):
        assert cur > prev, f"Expected strictly increasing sequence, got {prev} -> {cur}"
