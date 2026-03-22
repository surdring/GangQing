from __future__ import annotations

import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text


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

        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env for smoke test: {name}")
    return value


def _optional_env(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    return value or None


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    _load_dotenv_file(repo_root / ".env.local")

    base_url = _require_env("GANGQING_LLAMACPP_BASE_URL")
    database_url = _require_env("GANGQING_DATABASE_URL")

    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from gangqing.common.context import RequestContext
    from gangqing.common.errors import AppError, ErrorCode
    from gangqing.common.llamacpp_client import LlamaCppClient

    ctx = RequestContext(requestId="rid_llamacpp_smoke_1", tenantId="t_smoke", projectId="p_smoke")
    client = LlamaCppClient()

    models = client.list_models(ctx=ctx)
    if not isinstance(models, dict):
        raise RuntimeError(f"Unexpected response type from llama.cpp /models: {type(models)}")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": ctx.tenant_id})
        conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": ctx.project_id})
        conn.commit()
        rows = conn.execute(
            text(
                """
                SELECT request_id, resource, action_summary
                FROM audit_log
                WHERE tenant_id = :tenant_id
                  AND project_id = :project_id
                  AND request_id = :request_id
                  AND event_type = 'tool_call'
                ORDER BY timestamp DESC
                LIMIT 50
                """
            ),
            {
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "request_id": ctx.request_id,
            },
        ).mappings().all()

    if not rows:
        raise RuntimeError("Expected audit_log tool_call records for llama.cpp, got none")

    llama_rows = [r for r in rows if str(r.get("resource") or "") == "llama_cpp"]
    if not llama_rows:
        raise RuntimeError("Expected audit_log record with resource=llama_cpp")

    action_summary = llama_rows[0].get("action_summary")
    if not isinstance(action_summary, dict):
        raise RuntimeError("Expected audit_log.action_summary to be a JSON object")
    if str(action_summary.get("toolName") or "") != "llama_cpp":
        raise RuntimeError("Expected actionSummary.toolName=llama_cpp")

    args_summary = action_summary.get("argsSummary")
    if not isinstance(args_summary, dict):
        raise RuntimeError("Expected actionSummary.argsSummary to be a JSON object")
    for required_key in ["stage", "durationMs", "timeoutMs", "endpoint"]:
        if required_key not in args_summary:
            raise RuntimeError("Audit argsSummary missing key: " + required_key)

    fail_base_url = _optional_env("GANGQING_LLAMACPP_SMOKE_FAIL_BASE_URL")
    fail_expected_code = _optional_env("GANGQING_LLAMACPP_SMOKE_FAIL_EXPECTED_CODE")
    if fail_base_url and fail_expected_code:
        original = os.environ.get("GANGQING_LLAMACPP_BASE_URL")
        os.environ["GANGQING_LLAMACPP_BASE_URL"] = fail_base_url
        try:
            fail_client = LlamaCppClient()
            fail_ctx = RequestContext(
                requestId="rid_llamacpp_smoke_fail_1",
                tenantId="t_smoke",
                projectId="p_smoke",
            )
            try:
                _ = fail_client.list_models(ctx=fail_ctx)
                raise RuntimeError("Expected llama.cpp failure path, got success")
            except AppError as e:
                expected = str(fail_expected_code).strip().upper()
                if expected not in {
                    ErrorCode.UPSTREAM_TIMEOUT.value,
                    ErrorCode.UPSTREAM_UNAVAILABLE.value,
                    ErrorCode.CONTRACT_VIOLATION.value,
                }:
                    raise RuntimeError(
                        "Invalid expected error code for smoke test: " + expected
                    )
                if e.code.value != expected:
                    raise RuntimeError(f"Expected {expected}, got {e.code.value}")
                payload = e.to_response().model_dump(by_alias=True)
                for key in ["code", "message", "details", "retryable", "requestId"]:
                    if key not in payload:
                        raise RuntimeError("Smoke failure payload missing key: " + key)
        finally:
            if original is None:
                os.environ.pop("GANGQING_LLAMACPP_BASE_URL", None)
            else:
                os.environ["GANGQING_LLAMACPP_BASE_URL"] = original

    print(
        "llamacpp_smoke_ok",
        {
            "requestId": ctx.request_id,
            "baseUrl": base_url,
            "keys": sorted(list(models.keys()))[:20],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
