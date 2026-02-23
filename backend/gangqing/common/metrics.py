from __future__ import annotations

import threading
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DurationSummary:
    count: int
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None


class InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_count = Counter()
        self._status_count = Counter()
        self._durations_ms: deque[float] = deque(maxlen=5000)
        self._isolation_failures = Counter()

    def observe_http_request(self, *, method: str, path: str, status_code: int | None, duration_ms: float) -> None:
        key = f"{method} {path}"
        with self._lock:
            self._request_count[key] += 1
            self._status_count[f"{key} {status_code}"] += 1
            self._durations_ms.append(duration_ms)

    def inc_isolation_failure(self, *, reason: str) -> None:
        key = (reason or "").strip() or "unknown"
        with self._lock:
            self._isolation_failures[key] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = list(self._durations_ms)
            return {
                "http": {
                    "requests": dict(self._request_count),
                    "status": dict(self._status_count),
                    "duration": _summarize_durations(durations).__dict__,
                    "isolationFailures": dict(self._isolation_failures),
                }
            }


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)

    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)
    if f == c:
        return float(values_sorted[f])
    d0 = values_sorted[f] * (c - k)
    d1 = values_sorted[c] * (k - f)
    return float(d0 + d1)


def _summarize_durations(values: list[float]) -> DurationSummary:
    return DurationSummary(
        count=len(values),
        p50_ms=_percentile(values, 50),
        p95_ms=_percentile(values, 95),
        p99_ms=_percentile(values, 99),
    )


METRICS = InMemoryMetrics()
