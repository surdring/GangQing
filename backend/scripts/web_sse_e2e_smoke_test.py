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

        os.environ[key] = value


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

    raise RuntimeError(
        f"Server did not open port in time: {host}:{port}. Last error: {last_err}"
    )


def _request_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: dict | None = None,
) -> tuple[int, dict]:
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
    message: str,
    timeout_seconds: float,
) -> list[dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    events: list[dict] = []
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
                    if not current_data_lines:
                        continue

                    data_raw = "\n".join(current_data_lines)
                    current_data_lines = []

                    payload = json.loads(data_raw)
                    events.append(payload)

                    if str(payload.get("type") or "") == "final":
                        return events

            return events

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        raise RuntimeError(f"chat.stream failed: status={e.code}, body={raw}") from e


def _read_sse_events_cancel_after_meta(
    *,
    url: str,
    headers: dict[str, str],
    cancel_url: str,
    cancel_headers: dict[str, str],
    request_id_to_cancel: str,
    message: str,
    timeout_seconds: float,
) -> tuple[list[dict], int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    events: list[dict] = []
    deadline = time.time() + timeout_seconds

    cancel_sent = False
    cancel_status: int | None = None
    cancel_body: dict | None = None

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
                    if not current_data_lines:
                        continue

                    data_raw = "\n".join(current_data_lines)
                    current_data_lines = []

                    payload = json.loads(data_raw)
                    events.append(payload)

                    if (not cancel_sent) and str(payload.get("type") or "") == "meta":
                        cancel_status, cancel_body = _request_json(
                            cancel_url,
                            method="POST",
                            headers={
                                **cancel_headers,
                                "Content-Type": "application/json",
                            },
                            body={"requestId": request_id_to_cancel},
                        )
                        cancel_sent = True

                    if str(payload.get("type") or "") == "final":
                        break

            return events, int(cancel_status or 0), dict(cancel_body or {})

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        raise RuntimeError(f"chat.stream failed: status={e.code}, body={raw}") from e


def _request_chat_stream_expect_http_error(
    *,
    url: str,
    headers: dict[str, str],
    message: str,
) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return e.code, json.loads(raw) if raw else {}


def _assert_error_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected error.payload to be object, got: {type(payload)}")

    for required_key in ["code", "message", "retryable", "requestId"]:
        if required_key not in payload:
            raise RuntimeError(f"Missing required key in error.payload: {required_key}")

    msg = str(payload.get("message") or "")
    if any("\u4e00" <= ch <= "\u9fff" for ch in msg):
        raise RuntimeError(f"Expected ErrorResponse.message to be English, got: {msg}")


def _extract_structured_error_from_events(events: list[dict]) -> dict | None:
    for e in events:
        if str(e.get("type") or "") == "error":
            payload = e.get("payload")
            if isinstance(payload, dict):
                return payload

    for e in events:
        if str(e.get("type") or "") != "tool.result":
            continue
        payload = e.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("status") or "") != "failure":
            continue
        err = payload.get("error")
        if isinstance(err, dict):
            return err

    return None


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    host = (os.environ.get("GANGQING_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = int((os.environ.get("GANGQING_API_PORT") or "8000").strip() or "8000")

    tenant_id = (os.environ.get("GANGQING_TENANT_ID") or "t1").strip() or "t1"
    project_id = (os.environ.get("GANGQING_PROJECT_ID") or "p1").strip() or "p1"

    bootstrap_admin_user_id = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_USER_ID") or "").strip()
    bootstrap_admin_password = (os.environ.get("GANGQING_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()

    if not bootstrap_admin_user_id or not bootstrap_admin_password:
        raise RuntimeError(
            "Missing required env vars: GANGQING_BOOTSTRAP_ADMIN_USER_ID/GANGQING_BOOTSTRAP_ADMIN_PASSWORD"
        )

    request_id_success = "rid_web_sse_e2e_success_1"
    request_id_error = "rid_web_sse_e2e_error_1"
    request_id_cancel = "rid_web_sse_e2e_cancel_1"

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
        _wait_for_port(host, port, timeout_seconds=12.0)

        base_headers = {
            "X-Tenant-Id": tenant_id,
            "X-Project-Id": project_id,
            "Content-Type": "application/json",
        }

        login_url = f"http://{host}:{port}/api/v1/auth/login"
        status, body = _request_json(
            login_url,
            method="POST",
            headers={
                **base_headers,
                "X-Request-Id": request_id_success,
            },
            body={"username": bootstrap_admin_user_id, "password": bootstrap_admin_password},
        )
        if status != 200:
            raise RuntimeError(f"Login failed: status={status}, body={body}")

        access_token = (body.get("accessToken") or "").strip()
        if not access_token:
            raise RuntimeError(f"Missing accessToken in login response: {body}")

        chat_url = f"http://{host}:{port}/api/v1/chat/stream"
        cancel_url = f"http://{host}:{port}/api/v1/chat/stream/cancel"

        ok_events = _read_sse_events(
            url=chat_url,
            headers={
                **base_headers,
                "X-Request-Id": request_id_success,
                "Authorization": f"Bearer {access_token}",
            },
            message="query",
            timeout_seconds=25.0,
        )

        if not ok_events:
            raise RuntimeError("Expected non-empty SSE events in success path")

        ok_types = [str(e.get("type") or "") for e in ok_events]
        if ok_types[0] != "meta":
            raise RuntimeError(f"Expected first SSE event type=meta, got: {ok_types[0]}")
        if ok_types[-1] != "final":
            raise RuntimeError(f"Expected last SSE event type=final, got: {ok_types[-1]}")
        if not any(t == "message.delta" for t in ok_types):
            raise RuntimeError(f"Expected success SSE to include message.delta, types={ok_types}")

        final_payload = ok_events[-1].get("payload") or {}
        if (final_payload.get("status") or "") not in {"success", "error", "cancelled"}:
            raise RuntimeError(f"Invalid final.payload.status: {final_payload}")

        err_status, err_body = _request_chat_stream_expect_http_error(
            url=chat_url,
            headers={
                "X-Tenant-Id": tenant_id,
                "X-Request-Id": request_id_error,
                "Authorization": f"Bearer {access_token}",
            },
            message="query",
        )
        if err_status != 401:
            raise RuntimeError(f"Expected missing scope header to return 401, got: {err_status}, body={err_body}")
        _assert_error_payload(err_body)

        cancel_events, cancel_status, cancel_body = _read_sse_events_cancel_after_meta(
            url=chat_url,
            headers={
                **base_headers,
                "X-Request-Id": request_id_cancel,
                "Authorization": f"Bearer {access_token}",
            },
            cancel_url=cancel_url,
            cancel_headers={
                **base_headers,
                "X-Request-Id": request_id_cancel,
                "Authorization": f"Bearer {access_token}",
            },
            request_id_to_cancel=request_id_cancel,
            message="query",
            timeout_seconds=25.0,
        )

        if cancel_status != 200:
            _assert_error_payload(cancel_body)
            raise RuntimeError(f"Cancel API failed: status={cancel_status}, body={cancel_body}")

        if not cancel_events:
            raise RuntimeError("Expected non-empty SSE events in cancel path")

        cancel_types = [str(e.get("type") or "") for e in cancel_events]
        if cancel_types[0] != "meta":
            raise RuntimeError(f"Expected cancel SSE first event type=meta, got: {cancel_types[0]}")
        if cancel_types[-1] != "final":
            raise RuntimeError(f"Expected cancel SSE last event type=final, got: {cancel_types[-1]}")

        cancel_final_payload = cancel_events[-1].get("payload") or {}
        cancel_final_status = str(cancel_final_payload.get("status") or "")
        if cancel_final_status not in {"cancelled", "success", "error"}:
            raise RuntimeError(f"Invalid cancel final.payload.status: {cancel_final_payload}")

        print(
            "web_sse_e2e_smoke_ok",
            {
                "successEventCount": len(ok_events),
                "errorHttpStatus": err_status,
                "cancelEventCount": len(cancel_events),
                "cancelFinalStatus": cancel_final_status,
                "requestIdSuccess": request_id_success,
                "requestIdError": request_id_error,
                "requestIdCancel": request_id_cancel,
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
                deadline = time.time() + 1.5
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
