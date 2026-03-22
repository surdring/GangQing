export type RetryDecisionInput = {
  attemptIndex: number;
  maxAttempts: number;
  isRetryable: boolean;
  isCancelRequested: boolean;
};

export type RetryDecision = {
  shouldRetry: boolean;
  reason: 'cancelled' | 'non_retryable' | 'attempts_exhausted' | 'retryable';
};

export const decideShouldRetry = (input: RetryDecisionInput): RetryDecision => {
  const attemptIndex = Math.max(0, input.attemptIndex);
  const maxAttempts = Math.max(1, input.maxAttempts);

  if (input.isCancelRequested) {
    return { shouldRetry: false, reason: 'cancelled' };
  }

  if (!input.isRetryable) {
    return { shouldRetry: false, reason: 'non_retryable' };
  }

  if (attemptIndex >= maxAttempts - 1) {
    return { shouldRetry: false, reason: 'attempts_exhausted' };
  }

  return { shouldRetry: true, reason: 'retryable' };
};
