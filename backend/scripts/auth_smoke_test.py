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


def _request_json(url: str, *, method: str, headers: dict[str, str], body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return e.code, json.loads(raw) if raw else {}


def _assert_error_response(obj: dict) -> None:
    keys = sorted(obj.keys())
    if keys != ["code", "details", "message", "requestId", "retryable"]:
        raise AssertionError(f"Unexpected error response keys: {keys}")


def _assert_audit_events_response(obj: dict) -> None:
    keys = sorted(obj.keys())
    if keys != ["items", "total"]:
        raise AssertionError(f"Unexpected audit events response keys: {keys}")
    if not isinstance(obj.get("total"), int):
        raise AssertionError(f"Unexpected audit events total: {obj.get('total')}")
    if not isinstance(obj.get("items"), list):
        raise AssertionError(f"Unexpected audit events items type: {type(obj.get('items'))}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    if not (os.environ.get("GANGQING_DATABASE_URL") or "").strip():
        raise RuntimeError("Missing required env var: GANGQING_DATABASE_URL")

    host = os.environ.get("GANGQING_API_HOST", "127.0.0.1")
    port = int(os.environ.get("GANGQING_API_PORT", "8000"))

    tenant_id = os.environ.get("GANGQING_TENANT_ID", "t1")
    project_id = os.environ.get("GANGQING_PROJECT_ID", "p1")

    bootstrap_admin_user_id = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_USER_ID") or "").strip()
    bootstrap_admin_password = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if not bootstrap_admin_user_id or not bootstrap_admin_password:
        raise RuntimeError(
            "Missing required env vars: GANGQING_BOOTSTRAP_ADMIN_USER_ID/GANGQING_BOOTSTRAP_ADMIN_PASSWORD"
        )

    request_id = "rid_auth_smoke_1"

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    backend_dir = repo_root / "backend"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(backend_dir)
        if not existing_pythonpath
        else f"{backend_dir}{os.pathsep}{existing_pythonpath}"
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

        # 1) login success
        login_url = f"http://{host}:{port}/api/v1/auth/login"
        status, body = _request_json(
            login_url,
            method="POST",
            headers=base_headers,
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed: status={status}, body={body}")
        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in login response: {body}")

        # 2) protected endpoint success
        chat_url = f"http://{host}:{port}/api/v1/chat/stream"
        chat_headers = {
            **base_headers,
            "Authorization": f"Bearer {access_token}",
        }
        req = urllib.request.Request(
            chat_url,
            data=json.dumps({"message": "hello"}).encode("utf-8"),
            headers=chat_headers,
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=10.0) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"chat.stream failed: status={resp.status}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
            raise RuntimeError(f"chat.stream failed: status={e.code}, body={raw}") from e

        # 3) AUTH_ERROR when missing token
        status, err = _request_json(
            f"http://{host}:{port}/api/v1/audit/events",
            method="GET",
            headers=base_headers,
        )
        if status != 401:
            raise RuntimeError(f"Expected 401 for missing token, got {status}: {err}")
        _assert_error_response(err)
        if err.get("code") != "AUTH_ERROR":
            raise RuntimeError(f"Expected AUTH_ERROR, got: {err}")

        # 4) FORBIDDEN when role lacks capability
        finance_user_id = (os.environ.get("GANGQING_BOOTSTRAP_FINANCE_USER_ID") or "").strip()
        finance_password = (os.environ.get("GANGQING_BOOTSTRAP_FINANCE_PASSWORD") or "").strip()
        if not finance_user_id or not finance_password:
            raise RuntimeError(
                "Missing required env vars: GANGQING_BOOTSTRAP_FINANCE_USER_ID/GANGQING_BOOTSTRAP_FINANCE_PASSWORD"
            )

        status, fin_body = _request_json(
            login_url,
            method="POST",
            headers={**base_headers, "X-Request-Id": "rid_auth_smoke_2"},
            body={"username": finance_user_id, "password": finance_password},
        )
        if status != 200:
            raise RuntimeError(f"Finance login failed: status={status}, body={fin_body}")
        fin_token = (fin_body.get("accessToken") or "").strip()
        if not fin_token:
            raise RuntimeError(f"Missing finance accessToken: {fin_body}")

        status, forbid = _request_json(
            f"http://{host}:{port}/api/v1/chat/stream",
            method="POST",
            headers={
                **base_headers,
                "X-Request-Id": "rid_auth_smoke_3",
                "Authorization": f"Bearer {fin_token}",
            },
            body={"message": "hello"},
        )
        if status != 403:
            raise RuntimeError(f"Expected 403 for forbidden, got {status}: {forbid}")
        _assert_error_response(forbid)
        if forbid.get("code") != "FORBIDDEN":
            raise RuntimeError(f"Expected FORBIDDEN, got: {forbid}")

        # 5) verify audit events are queryable (requires admin audit:event:read)
        status, events = _request_json(
            f"http://{host}:{port}/api/v1/audit/events?requestId={request_id}",
            method="GET",
            headers={
                **base_headers,
                "Authorization": f"Bearer {access_token}",
            },
        )
        if status != 200:
            raise RuntimeError(f"Audit query failed: status={status}, body={events}")
        _assert_audit_events_response(events)
        items = events.get("items")
        if not isinstance(items, list) or not items:
            raise RuntimeError(f"Expected non-empty audit items: {events}")

        found_auth_denied = any(
            (isinstance(it, dict) and it.get("eventType") == "auth.denied") for it in items
        )
        if not found_auth_denied:
            raise RuntimeError("Expected auth.denied audit event not found")

        status, forbid_events = _request_json(
            "http://{host}:{port}/api/v1/audit/events?requestId=rid_auth_smoke_3".format(
                host=host, port=port
            ),
            method="GET",
            headers={
                **base_headers,
                "X-Request-Id": "rid_auth_smoke_4",
                "Authorization": f"Bearer {access_token}",
            },
        )
        if status != 200:
            raise RuntimeError(
                f"Audit query for forbidden request failed: status={status}, body={forbid_events}"
            )
        _assert_audit_events_response(forbid_events)
        forbid_items = forbid_events.get("items")
        if not isinstance(forbid_items, list) or not forbid_items:
            raise RuntimeError(f"Expected non-empty forbidden audit items: {forbid_events}")

        found_rbac_denied = any(
            (isinstance(it, dict) and it.get("eventType") == "rbac.denied") for it in forbid_items
        )
        if not found_rbac_denied:
            raise RuntimeError("Expected rbac.denied audit event not found")

        # 5.5) tool_call: admin can run tools/demo and writes tool_call audit
        status, tool_res = _request_json(
            f"http://{host}:{port}/api/v1/tools/demo",
            method="POST",
            headers={
                **base_headers,
                "X-Request-Id": "rid_auth_smoke_tool_1",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            body={"query": "q1"},
        )
        if status != 200:
            raise RuntimeError(f"tools.demo failed: status={status}, body={tool_res}")

        status, tool_events = _request_json(
            "http://{host}:{port}/api/v1/audit/events?requestId=rid_auth_smoke_tool_1".format(
                host=host, port=port
            ),
            method="GET",
            headers={
                **base_headers,
                "X-Request-Id": "rid_auth_smoke_tool_2",
                "Authorization": f"Bearer {access_token}",
            },
        )
        if status != 200:
            raise RuntimeError(
                f"Audit query for tool request failed: status={status}, body={tool_events}"
            )
        _assert_audit_events_response(tool_events)
        tool_items = tool_events.get("items")
        if not isinstance(tool_items, list) or not tool_items:
            raise RuntimeError(f"Expected non-empty tool audit items: {tool_events}")
        found_tool_call = any(
            (isinstance(it, dict) and it.get("eventType") == "tool_call") for it in tool_items
        )
        if not found_tool_call:
            raise RuntimeError("Expected tool_call audit event not found")

        # 6) verify structured logs contain requestId http_request
        found = False
        if proc.stdout is not None:
            selector = selectors.DefaultSelector()
            selector.register(proc.stdout, selectors.EVENT_READ)
            deadline = time.time() + 10.0
            while time.time() < deadline and not found:
                for key, _ in selector.select(timeout=0.2):
                    while True:
                        line = key.fileobj.readline()
                        if not line:
                            break
                        raw = line.strip()
                        if not raw:
                            continue
                        try:
                            obj = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("event") == "http_request" and obj.get("requestId") == request_id:
                            found = True
                            break
                    if found:
                        break

        if not found:
            raise RuntimeError("Smoke log verification failed: requestId not found in http_request logs")

        print("auth_smoke_test: PASS")
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
