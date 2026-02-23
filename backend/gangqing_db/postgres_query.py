from __future__ import annotations

from urllib.parse import urlparse
from typing import Any

from pydantic import ValidationError
from sqlalchemy import create_engine, text

from gangqing_db.errors import ConfigMissingError, MigrationError, map_db_error
from gangqing_db.settings import load_settings


def safe_extract_database_name(database_url: str) -> str | None:
    value = (database_url or "").strip()
    if not value:
        return None
    try:
        parsed = urlparse(value)
        path = (parsed.path or "").strip("/")
        return path or None
    except Exception:
        return None


def execute_readonly_query(
    *,
    sql: str,
    params: dict[str, Any],
    ctx: Any,
    statement_timeout_ms: int,
) -> list[dict[str, Any]]:
    try:
        settings = load_settings()
    except ValidationError as e:
        raise ConfigMissingError("GANGQING_DATABASE_URL", request_id=getattr(ctx, "request_id", None)) from e

    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": ctx.tenant_id})
                conn.execute(text("SELECT set_config('app.current_project', :p, true)"), {"p": ctx.project_id})
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(
                    text("SELECT set_config('statement_timeout', :v, true)"),
                    {"v": f"{int(statement_timeout_ms)}ms"},
                )

                rows = conn.execute(text(sql), params).mappings().all()
                return [dict(r) for r in rows]

    except MigrationError:
        raise
    except Exception as e:
        raise map_db_error(e, request_id=getattr(ctx, "request_id", None))
