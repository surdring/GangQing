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


def _read_sse_events(
    *,
    url: str,
    headers: dict[str, str],
    timeout_seconds: float,
) -> list[tuple[str, dict]]:
    req = urllib.request.Request(
        url,
        data=json.dumps({"message": "timeout slow"}).encode("utf-8"),
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    events: list[tuple[str, dict]] = []
    deadline = time.time() + timeout_seconds
    try:
        with opener.open(req, timeout=10.0) as resp:
            if resp.status != 200:
                raise RuntimeError(f"chat.stream failed: status={resp.status}")
            current_data_lines: list[str] = []

            while time.time() < deadline:
                raw = resp.readline()
                if not raw:
                    break

                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if line.endswith("\r"):
                    line = line[:-1]

                if line.startswith("data: "):
                    current_data_lines.append(line[len("data: ") :])
                    continue

                if line == "":
                    if current_data_lines:
                        data_raw = "\n".join(current_data_lines)
                        payload = json.loads(data_raw)
                        evt_type = str(payload.get("type") or "")
                        events.append((evt_type, payload))
                        if evt_type == "final":
                            return events
                    current_data_lines = []

            return events

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        raise RuntimeError(f"chat.stream failed: status={e.code}, body={raw}") from e


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

    request_id = "rid_chat_stream_retry_smoke_1"

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    env["GANGQING_TOOL_MAX_RETRIES"] = "1"
    env["GANGQING_TOOL_BACKOFF_BASE_MS"] = "0"
    env["GANGQING_TOOL_BACKOFF_MAX_MS"] = "0"
    env["GANGQING_TOOL_BACKOFF_JITTER_RATIO"] = "0"

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

        chat_url = f"http://{host}:{port}/api/v1/chat/stream"
        chat_headers = {
            **base_headers,
            "Authorization": f"Bearer {access_token}",
        }

        events = _read_sse_events(url=chat_url, headers=chat_headers, timeout_seconds=20.0)
        if not events:
            raise RuntimeError("Expected non-empty SSE events")

        if events[0][0] != "meta":
            raise RuntimeError(f"Expected first SSE event meta, got: {events[0][0]}")

        if events[-1][0] != "final":
            raise RuntimeError(f"Expected last SSE event final, got: {events[-1][0]}")

        event_types = [t for t, _ in events]
        counts = {
            "meta": sum(1 for t in event_types if t == "meta"),
            "progress": sum(1 for t in event_types if t == "progress"),
            "tool.call": sum(1 for t in event_types if t == "tool.call"),
            "tool.result": sum(1 for t in event_types if t == "tool.result"),
            "warning": sum(1 for t in event_types if t == "warning"),
            "error": sum(1 for t in event_types if t == "error"),
            "final": sum(1 for t in event_types if t == "final"),
        }
        if "tool.call" not in event_types:
            raise RuntimeError(f"Expected SSE to include tool.call. counts={counts}, types={event_types}")
        if "warning" not in event_types:
            raise RuntimeError(f"Expected SSE to include warning for retry. counts={counts}, types={event_types}")

        final_event = events[-1][1]
        final_payload = final_event.get("payload") if isinstance(final_event, dict) else None
        final_status = (
            str(final_payload.get("status") or "")
            if isinstance(final_payload, dict)
            else ""
        )
        if final_status not in {"success", "error"}:
            raise RuntimeError(
                f"Expected final.payload.status to be success|error, got: {final_payload}"
            )

        if final_status == "error" and "error" not in event_types:
            raise RuntimeError(
                f"Expected SSE to include error event when final.status=error. counts={counts}, types={event_types}"
            )

        tool_call_count = sum(1 for t, _ in events if t == "tool.call")
        if tool_call_count < 2:
            raise RuntimeError(f"Expected at least 2 tool.call events for retry, got {tool_call_count}")

        first_tool_call = next((p for t, p in events if t == "tool.call"), None)
        if not isinstance(first_tool_call, dict):
            raise RuntimeError("Expected tool.call payload to be an object")
        call_payload = first_tool_call.get("payload")
        if not isinstance(call_payload, dict):
            raise RuntimeError("Expected tool.call.payload to be an object")
        if not str(call_payload.get("toolCallId") or "").strip():
            raise RuntimeError(f"Expected tool.call.payload.toolCallId, got: {call_payload}")
        if not str(call_payload.get("toolName") or "").strip():
            raise RuntimeError(f"Expected tool.call.payload.toolName, got: {call_payload}")
        if not isinstance(call_payload.get("argsSummary"), dict):
            raise RuntimeError(f"Expected tool.call.payload.argsSummary to be object, got: {call_payload}")

        tool_result = next((p for t, p in reversed(events) if t == "tool.result"), None)
        if tool_result is not None:
            if not isinstance(tool_result, dict):
                raise RuntimeError("Expected tool.result payload to be an object")
            result_payload = tool_result.get("payload")
            if not isinstance(result_payload, dict):
                raise RuntimeError("Expected tool.result.payload to be an object")
            if not str(result_payload.get("toolCallId") or "").strip():
                raise RuntimeError(f"Expected tool.result.payload.toolCallId, got: {result_payload}")
            if not str(result_payload.get("toolName") or "").strip():
                raise RuntimeError(f"Expected tool.result.payload.toolName, got: {result_payload}")
            if str(result_payload.get("status") or "") not in {"success", "failure"}:
                raise RuntimeError(f"Unexpected tool.result.payload.status, got: {result_payload}")
            if str(result_payload.get("status") or "") == "failure":
                err = result_payload.get("error")
                if not isinstance(err, dict) or not str(err.get("code") or "").strip():
                    raise RuntimeError(
                        f"Expected tool.result.payload.error to be ErrorResponse, got: {result_payload}"
                    )

        print(
            "chat_stream_retry_smoke_ok",
            {
                "requestId": request_id,
                "eventCount": len(events),
                "toolCallCount": tool_call_count,
            },
        )
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
                selector = selectors.DefaultSelector()
                selector.register(proc.stdout, selectors.EVENT_READ)
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    for key, _ in selector.select(timeout=0.2):
                        _ = key.fileobj.readline()
        except Exception:
            pass

        try:
            if proc.stdout is not None:
                proc.stdout.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
