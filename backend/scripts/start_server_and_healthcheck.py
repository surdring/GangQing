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


def _healthcheck(url: str, *, timeout_seconds: float) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, body


def _safe_body_summary(body: str, *, max_chars: int = 2000) -> str:
    text = (body or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    lowered = text.lower()
    forbidden_fragments = [
        "postgresql://",
        "psycopg://",
        "password",
        "secret",
        "sk-",
        "nvapi-",
        "authorization",
        "x-api-key",
    ]
    for frag in forbidden_fragments:
        if frag in lowered:
            return "[REDACTED]"
    return text


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env for smoke test: {name}")
    return value


def _require_any_env(names: set[str]) -> tuple[str, str]:
    for name in sorted(names):
        value = (os.environ.get(name) or "").strip()
        if value:
            return name, value
    raise RuntimeError(
        "Missing required env for smoke test: expected at least one of: "
        + ", ".join(sorted(names))
    )


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


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    host = (os.environ.get("GANGQING_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = int((os.environ.get("GANGQING_API_PORT") or "8000").strip() or "8000")

    _require_env("GANGQING_DATABASE_URL")
    _require_any_env({"GANGQING_LLAMACPP_BASE_URL", "GANGQING_PROVIDER_HEALTHCHECK_URL"})

    smoke_health_timeout_seconds_raw = (
        os.environ.get("GANGQING_SMOKE_HEALTH_TIMEOUT_SECONDS") or "15.0"
    ).strip()
    try:
        smoke_health_timeout_seconds = float(smoke_health_timeout_seconds_raw)
    except ValueError:
        smoke_health_timeout_seconds = 15.0

    request_id = "rid_smoke_1"

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

        url = f"http://{host}:{port}/api/v1/health"
        headers = {
            "X-Tenant-Id": "t1",
            "X-Project-Id": "p1",
            "X-Request-Id": request_id,
        }
        req = urllib.request.Request(url, headers=headers, method="GET")

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=smoke_health_timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                if resp.status != 200:
                    raise RuntimeError(
                        "Healthcheck failed: expected HTTP 200. "
                        f"status={resp.status}, body={_safe_body_summary(body)}"
                    )
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Healthcheck response is not JSON: {body}") from e
                if obj.get("requestId") != request_id:
                    raise RuntimeError(
                        f"Healthcheck requestId mismatch: expected={request_id}, got={obj.get('requestId')}"
                    )
                if obj.get("status") not in {"healthy", "degraded", "unhealthy"}:
                    raise RuntimeError(
                        f"Healthcheck invalid status value: {obj.get('status')}"
                    )
                if not isinstance(obj.get("dependencies"), list):
                    raise RuntimeError("Healthcheck dependencies must be a list")
                dep_names = {d.get("name") for d in obj.get("dependencies", []) if isinstance(d, dict)}
                for required in {"config", "postgres", "llama_cpp", "provider", "model"}:
                    if required not in dep_names:
                        raise RuntimeError(f"Healthcheck missing dependency item: {required}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(
                "Healthcheck failed: expected HTTP 200. "
                f"status={e.code}, body={_safe_body_summary(body)}"
            ) from e
            try:
                obj = json.loads(body)
            except json.JSONDecodeError as je:
                raise RuntimeError(f"Healthcheck response is not JSON: {body}") from je
            if obj.get("requestId") != request_id:
                raise RuntimeError(
                    f"Healthcheck requestId mismatch: expected={request_id}, got={obj.get('requestId')}"
                )
            if obj.get("status") not in {"healthy", "degraded", "unhealthy"}:
                raise RuntimeError(f"Healthcheck invalid status value: {obj.get('status')}")
            if not isinstance(obj.get("dependencies"), list):
                raise RuntimeError("Healthcheck dependencies must be a list")
            dep_names = {d.get("name") for d in obj.get("dependencies", []) if isinstance(d, dict)}
            for required in {"config", "postgres", "llama_cpp", "provider", "model"}:
                if required not in dep_names:
                    raise RuntimeError(f"Healthcheck missing dependency item: {required}")
        except TimeoutError as e:
            raise RuntimeError(
                "Healthcheck failed: request timed out. "
                f"timeoutSeconds={smoke_health_timeout_seconds}"
            ) from e

        # Failure path: missing required scope header should return structured ErrorResponse.
        req_missing_tenant = urllib.request.Request(
            url,
            headers={"X-Project-Id": "p1", "X-Request-Id": request_id},
            method="GET",
        )
        try:
            with opener.open(req_missing_tenant, timeout=smoke_health_timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                raise RuntimeError(
                    f"Smoke expected 401 for missing X-Tenant-Id, got status={resp.status}, body={body}"
                )
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            if e.code != 401:
                raise RuntimeError(
                    f"Smoke expected 401 for missing X-Tenant-Id, got status={e.code}, body={body}"
                ) from e
            try:
                err = json.loads(body)
            except json.JSONDecodeError as je:
                raise RuntimeError(f"401 response is not JSON: {body}") from je
            for key in ["code", "message", "details", "retryable", "requestId"]:
                if key not in err:
                    raise RuntimeError(f"401 ErrorResponse missing key: {key}")

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
                        if (
                            obj.get("event") == "http_request"
                            and obj.get("requestId") == request_id
                        ):
                            found = True
                            break
                    if found:
                        break

        if not found:
            raise RuntimeError("Smoke log verification failed: requestId not found in http_request logs")

        print("healthcheck_ok")
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
