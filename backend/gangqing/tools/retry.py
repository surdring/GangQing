from __future__ import annotations

import random
from dataclasses import dataclass

from gangqing.common.errors import AppError, ErrorCode


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    backoff_base_ms: int
    backoff_multiplier: float
    backoff_max_ms: int
    backoff_jitter_ratio: float

    @property
    def max_attempts(self) -> int:
        return int(self.max_retries) + 1


def should_retry_error(*, error: AppError) -> bool:
    if not bool(getattr(error, "retryable", False)):
        return False

    retryable_codes = {
        ErrorCode.UPSTREAM_TIMEOUT,
        ErrorCode.UPSTREAM_UNAVAILABLE,
    }
    return error.code in retryable_codes


def compute_backoff_ms(*, policy: RetryPolicy, attempt: int) -> int:
    """Compute backoff in milliseconds for the *next* retry.

    attempt: 1-based attempt number of the failed attempt.
    Example:
    - attempt=1 (first failure) => base delay
    - attempt=2 => base*multiplier
    """

    if attempt < 1:
        raise ValueError("attempt must be >= 1")

    base = max(0, int(policy.backoff_base_ms))
    max_ms = max(0, int(policy.backoff_max_ms))

    delay = int(round(base * (float(policy.backoff_multiplier) ** max(0, attempt - 1))))
    delay = min(delay, max_ms)

    jitter_ratio = float(policy.backoff_jitter_ratio)
    jitter_ratio = min(max(jitter_ratio, 0.0), 1.0)

    if delay <= 0 or jitter_ratio <= 0:
        return delay

    jitter = int(round(delay * jitter_ratio))
    if jitter <= 0:
        return delay

    low = max(0, delay - jitter)
    high = delay + jitter
    return int(random.randint(low, high))
