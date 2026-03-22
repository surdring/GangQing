import { describe, expect, it } from 'vitest';

import { decideShouldRetry } from '../hooks/sse/retryPolicy';

describe('decideShouldRetry', () => {
  it('retries when retryable and attempts remain', () => {
    const res = decideShouldRetry({
      attemptIndex: 0,
      maxAttempts: 3,
      isRetryable: true,
      isCancelRequested: false,
    });

    expect(res).toEqual({ shouldRetry: true, reason: 'retryable' });
  });

  it('does not retry when non-retryable', () => {
    const res = decideShouldRetry({
      attemptIndex: 0,
      maxAttempts: 3,
      isRetryable: false,
      isCancelRequested: false,
    });

    expect(res).toEqual({ shouldRetry: false, reason: 'non_retryable' });
  });

  it('does not retry when attempts exhausted', () => {
    const res = decideShouldRetry({
      attemptIndex: 2,
      maxAttempts: 3,
      isRetryable: true,
      isCancelRequested: false,
    });

    expect(res).toEqual({ shouldRetry: false, reason: 'attempts_exhausted' });
  });

  it('does not retry when cancel requested', () => {
    const res = decideShouldRetry({
      attemptIndex: 0,
      maxAttempts: 3,
      isRetryable: true,
      isCancelRequested: true,
    });

    expect(res).toEqual({ shouldRetry: false, reason: 'cancelled' });
  });
});
