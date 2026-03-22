from __future__ import annotations

import threading
from dataclasses import dataclass

from gangqing.common.errors import AppError, ErrorCode


@dataclass(frozen=True)
class CancellationScope:
    tenant_id: str
    project_id: str


class CancellationRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_request_id: dict[str, tuple[CancellationScope, threading.Event]] = {}

    def register(self, *, request_id: str, scope: CancellationScope) -> threading.Event:
        with self._lock:
            existing = self._by_request_id.get(request_id)
            if existing is not None:
                existing_scope, existing_event = existing
                if existing_scope != scope:
                    raise AppError(
                        ErrorCode.FORBIDDEN,
                        "Request scope mismatch",
                        request_id=request_id,
                        details={
                            "stage": "chat.stream.register",
                            "reason": "scope_mismatch",
                        },
                        retryable=False,
                    )
                return existing_event

            evt = threading.Event()
            self._by_request_id[request_id] = (scope, evt)
            return evt

    def unregister(self, *, request_id: str) -> None:
        with self._lock:
            self._by_request_id.pop(request_id, None)

    def cancel(self, *, caller_scope: CancellationScope, request_id: str) -> bool:
        with self._lock:
            existing = self._by_request_id.get(request_id)
            if existing is None:
                return False

            scope, evt = existing
            if scope != caller_scope:
                raise AppError(
                    ErrorCode.FORBIDDEN,
                    "Forbidden",
                    request_id=request_id,
                    details={
                        "stage": "chat.stream.cancel",
                        "reason": "scope_mismatch",
                    },
                    retryable=False,
                )

            evt.set()
            return True


cancellation_registry = CancellationRegistry()
