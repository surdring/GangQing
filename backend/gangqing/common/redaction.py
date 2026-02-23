from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any


_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set-cookie",
)

_REDACTED_VALUE = "[REDACTED]"


def redact_sensitive(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            key_str = str(k)
            if _is_sensitive_key(key_str):
                redacted[key_str] = _REDACTED_VALUE
            else:
                redacted[key_str] = redact_sensitive(v)
        return redacted

    if isinstance(value, (list, tuple)):
        return [redact_sensitive(v) for v in value]

    return value


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(fragment in key_lower for fragment in _get_sensitive_key_fragments())


def _get_sensitive_key_fragments() -> tuple[str, ...]:
    extra = (os.environ.get("GANGQING_REDACTION_SENSITIVE_KEY_FRAGMENTS") or "").strip()
    if not extra:
        return _SENSITIVE_KEY_FRAGMENTS

    parts = [p.strip().lower() for p in extra.split(",") if p.strip()]
    merged = list(_SENSITIVE_KEY_FRAGMENTS)
    for p in parts:
        if p not in merged:
            merged.append(p)
    return tuple(merged)
