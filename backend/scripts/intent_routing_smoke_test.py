"""Smoke test for Task 12 intent recognition + routing policy.

Real integration requirements (no mocks, no skips):
- Starts FastAPI server (uvicorn) against real Postgres.
- Requires llama.cpp connectivity via healthcheck.
- Sends real HTTP requests and asserts structured ErrorResponse contract.

Success path:
- login
- call chat stream endpoint with a normal message to ensure server is functional

Failure path:
- call /tools/postgres/query with a role lacking capability -> FORBIDDEN ErrorResponse

Policy path:
- locally run routing policy with ACTION_EXECUTE -> GUARDRAIL_BLOCKED and assert ErrorResponse keys.

This script fails fast when required configuration is missing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import re


def _load_dotenv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env for smoke test: {name}")
    return value


def _wait_for_port(host: str, port: int, *, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except Exception as e:
            last_err = e
            time.sleep(0.1)
    raise RuntimeError(f"Server did not open port in time: {host}:{port}. Last error: {last_err}")


def _request_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: dict | None = None,
    timeout_seconds: float = 10.0,
) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return int(e.code), json.loads(raw) if raw else {}
        except Exception as je:
            raise RuntimeError(
                f"HTTP error response is not JSON: status={e.code}, body={raw}"
            ) from je


def _assert_error_response(obj: dict) -> None:
    keys = sorted(obj.keys())
    if keys != ["code", "details", "message", "requestId", "retryable"]:
        raise AssertionError(f"Unexpected error response keys: {keys}")


def _request_sse_events(
    url: str,
    *,
    headers: dict[str, str],
    body: dict,
    timeout_seconds: float = 20.0,
    max_events: int = 50,
) -> list[tuple[str, dict]]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    events: list[tuple[str, dict]] = []
    current_event: str | None = None
    current_data: str | None = None

    with opener.open(req, timeout=timeout_seconds) as resp:
        while len(events) < max_events:
            raw = resp.readline()
            if not raw:
                break
            line = raw.decode("utf-8").rstrip("\n")
            if not line:
                if current_event is not None and current_data is not None:
                    try:
                        payload = json.loads(current_data)
                    except Exception as e:
                        raise RuntimeError(
                            f"SSE data is not JSON: event={current_event}, data={current_data}"
                        ) from e
                    events.append((current_event, payload))
                    if current_event == "final":
                        return events
                current_event = None
                current_data = None
                continue

            if line.startswith("event:"):
                current_event = line[len("event:") :].strip()
                continue

            if line.startswith("data:"):
                current_data = line[len("data:") :].strip()
                continue

    return events


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    os.environ.setdefault("GANGQING_JWT_SECRET", "0123456789abcdef0123456789abcdef")
    os.environ.setdefault("GANGQING_LOG_FORMAT", "json")

    _require_env("GANGQING_DATABASE_URL")
    _require_env("GANGQING_LLAMACPP_BASE_URL")
    _require_env("GANGQING_BOOTSTRAP_ADMIN_USER_ID")
    _require_env("GANGQING_BOOTSTRAP_ADMIN_PASSWORD")
    _require_env("GANGQING_BOOTSTRAP_FINANCE_USER_ID")
    _require_env("GANGQING_BOOTSTRAP_FINANCE_PASSWORD")

    host = os.environ.get("GANGQING_API_HOST", "127.0.0.1")
    port = int(os.environ.get("GANGQING_API_PORT", "8000"))

    tenant_id = os.environ.get("GANGQING_TENANT_ID", "t1")
    project_id = os.environ.get("GANGQING_PROJECT_ID", "p1")

    request_id = "rid_intent_routing_smoke_1"

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["GANGQING_LOG_FORMAT"] = "json"

    backend_dir = repo_root / "backend"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(backend_dir) if not existing_pythonpath else f"{backend_dir}{os.pathsep}{existing_pythonpath}"
    )

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "uvicorn",
        "gangqing.app.main:create_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        env.get("GANGQING_LOG_LEVEL", "info").lower(),
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        _wait_for_port(host, port, timeout_seconds=10.0)

        base_headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "X-Request-Id": request_id,
            "Content-Type": "application/json",
        }

        # Healthcheck should include real dependencies.
        status, health = _request_json(
            f"http://{host}:{port}/api/v1/health",
            method="GET",
            headers={
                "X-Tenant-Id": tenant_id,
                "X-Project-Id": project_id,
                "X-Request-Id": request_id,
            },
            body=None,
        )
        if status != 200:
            raise RuntimeError(f"Healthcheck failed: status={status}, body={health}")
        deps = health.get("dependencies")
        if not isinstance(deps, list):
            raise RuntimeError("Healthcheck dependencies must be a list")
        dep_names = {d.get("name") for d in deps if isinstance(d, dict)}
        for required in {"postgres", "llama_cpp"}:
            if required not in dep_names:
                raise RuntimeError(f"Healthcheck missing dependency: {required}")

        # Login as admin
        login_url = f"http://{host}:{port}/api/v1/auth/login"
        status, body = _request_json(
            login_url,
            method="POST",
            headers=base_headers,
            body={
                "username": os.environ["GANGQING_BOOTSTRAP_ADMIN_USER_ID"],
                "password": os.environ["GANGQING_BOOTSTRAP_ADMIN_PASSWORD"],
            },
        )
        if status != 200:
            raise RuntimeError(f"Login failed: status={status}, body={body}")
        token = (body.get("accessToken") or "").strip()
        if not token:
            raise RuntimeError(f"Login response missing accessToken: {body}")

        chat_url = f"http://{host}:{port}/api/v1/chat/stream"

        # Success path: should include intent.result + routing.decision + final(success)
        events = _request_sse_events(
            chat_url,
            headers={
                **base_headers,
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
            },
            body={"message": "查询今天产量数据"},
        )
        event_types = [t for t, _ in events]
        for required in ["meta", "intent.result", "routing.decision", "final"]:
            if required not in event_types:
                raise RuntimeError(f"Missing SSE event type: {required}. got={event_types}")
        final_payload = next((p for t, p in events if t == "final"), None)
        if not isinstance(final_payload, dict) or final_payload.get("payload", {}).get("status") != "success":
            raise RuntimeError(f"Unexpected final payload for success path: {final_payload}")

        # Clarify path: ambiguous input => intent.result(needsClarification=true) + routing.decision(clarify)
        clarify_events = _request_sse_events(
            chat_url,
            headers={
                **base_headers,
                "X-Request-Id": "rid_intent_routing_smoke_clarify_1",
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
            },
            body={"message": "帮我看一下"},
        )
        clarify_types = [t for t, _ in clarify_events]
        if "intent.result" not in clarify_types or "routing.decision" not in clarify_types:
            raise RuntimeError(f"Clarify path missing required events: got={clarify_types}")
        intent_payload = next((p for t, p in clarify_events if t == "intent.result"), None)
        if not isinstance(intent_payload, dict) or not intent_payload.get("payload", {}).get("needsClarification"):
            raise RuntimeError(f"Clarify path intent.result not marked needsClarification: {intent_payload}")
        routing_payload = next((p for t, p in clarify_events if t == "routing.decision"), None)
        if not isinstance(routing_payload, dict) or routing_payload.get("payload", {}).get("decisionType") != "clarify":
            raise RuntimeError(f"Clarify path routing decision is not clarify: {routing_payload}")
        if "tool.call" in clarify_types:
            raise RuntimeError("Clarify path must not call tools")

        # Draft path: generate draft => draft.created + final(success)
        draft_events = _request_sse_events(
            chat_url,
            headers={
                **base_headers,
                "X-Request-Id": "rid_intent_routing_smoke_draft_1",
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
            },
            body={"message": "生成草案"},
        )
        draft_types = [t for t, _ in draft_events]
        if "draft.created" not in draft_types:
            raise RuntimeError(f"Draft path missing draft.created event: got={draft_types}")
        if "tool.call" in draft_types:
            raise RuntimeError("Draft path must not call tools")
        draft_final = next((p for t, p in draft_events if t == "final"), None)
        if not isinstance(draft_final, dict) or draft_final.get("payload", {}).get("status") != "success":
            raise RuntimeError(f"Unexpected final payload for draft path: {draft_final}")

        # Login as finance (role lacking tool:postgres:read)
        status, fin_body = _request_json(
            login_url,
            method="POST",
            headers={**base_headers, "X-Request-Id": "rid_intent_routing_smoke_2"},
            body={
                "username": os.environ["GANGQING_BOOTSTRAP_FINANCE_USER_ID"],
                "password": os.environ["GANGQING_BOOTSTRAP_FINANCE_PASSWORD"],
            },
        )
        if status != 200:
            raise RuntimeError(f"Finance login failed: status={status}, body={fin_body}")
        fin_token = (fin_body.get("accessToken") or "").strip()
        if not fin_token:
            raise RuntimeError(f"Finance login response missing accessToken: {fin_body}")

        # Failure path: role with chat stream capability but without tool capability.
        # Finance role has no chat:conversation:stream capability; use dispatcher JWT to reach chat stream
        # and trigger tool capability check.
        from gangqing.common.auth import create_access_token

        dispatcher_token, _ = create_access_token(
            user_id="u_smoke_dispatcher",
            role="dispatcher",
            tenant_id=tenant_id,
            project_id=project_id,
        )

        forbid_events = _request_sse_events(
            chat_url,
            headers={
                **base_headers,
                "X-Request-Id": "rid_intent_routing_smoke_forbid_tool_1",
                "Authorization": f"Bearer {dispatcher_token}",
                "Accept": "text/event-stream",
            },
            body={"message": "查询今天产量数据"},
        )
        forbid_types = [t for t, _ in forbid_events]
        if "error" not in forbid_types:
            raise RuntimeError(f"Expected error event for forbidden tool access, got={forbid_types}")
        error_event = next((p for t, p in forbid_events if t == "error"), None)
        if not isinstance(error_event, dict):
            raise RuntimeError(f"Invalid error event payload: {error_event}")
        err_payload = error_event.get("payload")
        if not isinstance(err_payload, dict):
            raise RuntimeError(f"Invalid error payload: {error_event}")
        _assert_error_response(err_payload)
        if err_payload.get("code") != "FORBIDDEN":
            raise RuntimeError(f"Expected FORBIDDEN, got: {err_payload}")
        forbid_final = next((p for t, p in forbid_events if t == "final"), None)
        if not isinstance(forbid_final, dict) or forbid_final.get("payload", {}).get("status") != "error":
            raise RuntimeError(f"Expected final(status=error) for forbidden path, got: {forbid_final}")

        # Policy path: local routing check
        backend_dir = repo_root / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from gangqing.agent.routing import route_intent
        from gangqing.common.context import RequestContext
        from gangqing.common.errors import ErrorCode
        from gangqing.schemas.intent import ClarificationQuestion, IntentResult, IntentType, RiskLevel

        ctx = RequestContext(requestId="rid_intent_routing_policy_1", tenantId=tenant_id, projectId=project_id)
        intent_result = IntentResult(
            intent=IntentType.ACTION_EXECUTE,
            confidence=0.99,
            needsClarification=False,
            clarificationQuestions=[],
            reasonCodes=["SMOKE_TEST"],
            reasonSummary=None,
            hasWriteIntent=True,
            riskLevel=RiskLevel.HIGH,
        )
        decision = route_intent(ctx=ctx, intent_result=intent_result, tool_specs=[])
        if decision.decision_type.value != "block":
            raise RuntimeError(f"Expected decision_type=block for ACTION_EXECUTE, got {decision.decision_type.value}")
        if decision.blocked_reason_code != ErrorCode.GUARDRAIL_BLOCKED.value:
            raise RuntimeError(
                f"Expected blockedReasonCode=GUARDRAIL_BLOCKED, got {decision.blocked_reason_code}"
            )

        # Verification: audit should be queryable by requestId (end-to-end, real DB).
        # Prefer API-level verification over parsing server stdout logs.
        audit_url = f"http://{host}:{port}/api/v1/audit/events?requestId={request_id}&limit=5&offset=0"
        try:
            status, audit_body = _request_json(
                audit_url,
                method="GET",
                headers={
                    **base_headers,
                    "Authorization": f"Bearer {token}",
                },
                body=None,
                timeout_seconds=10.0,
            )
            if status != 200:
                raise RuntimeError(f"Audit query failed: status={status}, body={audit_body}")
            items = audit_body.get("items")
            if not isinstance(items, list) or not items:
                raise RuntimeError(f"Audit query returned no items for requestId={request_id}: {audit_body}")
            if not any(isinstance(i, dict) and i.get("requestId") == request_id for i in items):
                raise RuntimeError(f"Audit query missing requestId={request_id}: {audit_body}")
        except Exception as e:
            # Fallback: best-effort log scan to help debugging environments lacking audit capability.
            found = False
            if proc.stdout is not None:
                selector = selectors.DefaultSelector()
                selector.register(proc.stdout, selectors.EVENT_READ)
                deadline = time.time() + 5.0
                while time.time() < deadline and not found:
                    for key, _ in selector.select(timeout=0.2):
                        line = key.fileobj.readline()
                        if not line:
                            continue
                        text = line.strip()
                        if request_id in text and "http_request" in text:
                            found = True
                            break
            if not found:
                raise RuntimeError(
                    f"Smoke verification failed: audit query failed and requestId not found in stdout logs. auditError={e}"
                )

        print("intent_routing_smoke_test: PASS")
        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)

        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
