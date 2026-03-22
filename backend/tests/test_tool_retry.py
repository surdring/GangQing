from __future__ import annotations

import pytest

from gangqing.common.errors import AppError, ErrorCode
from gangqing.tools.retry import RetryPolicy, compute_backoff_ms, should_retry_error


def test_retry_policy_max_attempts_is_retries_plus_one() -> None:
    policy = RetryPolicy(
        max_retries=3,
        backoff_base_ms=200,
        backoff_multiplier=2.0,
        backoff_max_ms=2000,
        backoff_jitter_ratio=0.0,
    )
    assert policy.max_attempts == 4


def test_should_retry_error_only_for_retryable_upstream_codes() -> None:
    err_timeout = AppError(
        ErrorCode.UPSTREAM_TIMEOUT,
        "Upstream request timed out",
        request_id="r1",
        details=None,
        retryable=True,
    )
    assert should_retry_error(error=err_timeout) is True

    err_unavailable = AppError(
        ErrorCode.UPSTREAM_UNAVAILABLE,
        "Upstream service is unavailable",
        request_id="r1",
        details=None,
        retryable=True,
    )
    assert should_retry_error(error=err_unavailable) is True

    err_validation = AppError(
        ErrorCode.VALIDATION_ERROR,
        "Invalid tool parameters",
        request_id="r1",
        details=None,
        retryable=False,
    )
    assert should_retry_error(error=err_validation) is False

    err_not_retryable_timeout = AppError(
        ErrorCode.UPSTREAM_TIMEOUT,
        "Upstream request timed out",
        request_id="r1",
        details=None,
        retryable=False,
    )
    assert should_retry_error(error=err_not_retryable_timeout) is False


def test_compute_backoff_ms_exponential_no_jitter() -> None:
    policy = RetryPolicy(
        max_retries=3,
        backoff_base_ms=200,
        backoff_multiplier=2.0,
        backoff_max_ms=2000,
        backoff_jitter_ratio=0.0,
    )

    assert compute_backoff_ms(policy=policy, attempt=1) == 200
    assert compute_backoff_ms(policy=policy, attempt=2) == 400
    assert compute_backoff_ms(policy=policy, attempt=3) == 800
    assert compute_backoff_ms(policy=policy, attempt=4) == 1600


def test_compute_backoff_ms_is_capped_by_max() -> None:
    policy = RetryPolicy(
        max_retries=3,
        backoff_base_ms=1000,
        backoff_multiplier=10.0,
        backoff_max_ms=1500,
        backoff_jitter_ratio=0.0,
    )

    assert compute_backoff_ms(policy=policy, attempt=1) == 1000
    assert compute_backoff_ms(policy=policy, attempt=2) == 1500


def test_compute_backoff_ms_rejects_invalid_attempt() -> None:
    policy = RetryPolicy(
        max_retries=1,
        backoff_base_ms=0,
        backoff_multiplier=2.0,
        backoff_max_ms=0,
        backoff_jitter_ratio=0.0,
    )

    with pytest.raises(ValueError):
        compute_backoff_ms(policy=policy, attempt=0)
