import { describe, expect, it, vi } from 'vitest';

import { createSseStreamTimeoutController } from '../hooks/sse/timeouts';

describe('SSE stream timeout controller', () => {
  it('fires first_progress timeout when not stopped', () => {
    vi.useFakeTimers();
    const onTimeout = vi.fn();

    const ctrl = createSseStreamTimeoutController(
      { connectTimeoutMs: 1, firstProgressTimeoutMs: 10, idleTimeoutMs: 50 },
      { onTimeout },
    );

    ctrl.startFirstProgressTimer();
    vi.advanceTimersByTime(9);
    expect(onTimeout).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(onTimeout).toHaveBeenCalledWith({ type: 'first_progress', timeoutMs: 10 });

    vi.useRealTimers();
  });

  it('does not fire first_progress timeout after stopped', () => {
    vi.useFakeTimers();
    const onTimeout = vi.fn();

    const ctrl = createSseStreamTimeoutController(
      { connectTimeoutMs: 1, firstProgressTimeoutMs: 10, idleTimeoutMs: 50 },
      { onTimeout },
    );

    ctrl.startFirstProgressTimer();
    ctrl.stopFirstProgressTimer();
    vi.advanceTimersByTime(20);
    expect(onTimeout).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('fires idle timeout after reset when no further resets occur', () => {
    vi.useFakeTimers();
    const onTimeout = vi.fn();

    const ctrl = createSseStreamTimeoutController(
      { connectTimeoutMs: 1, firstProgressTimeoutMs: 10, idleTimeoutMs: 50 },
      { onTimeout },
    );

    ctrl.resetIdleTimer();
    vi.advanceTimersByTime(49);
    expect(onTimeout).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(onTimeout).toHaveBeenCalledWith({ type: 'idle', timeoutMs: 50 });

    vi.useRealTimers();
  });

  it('idle timer is extended by subsequent resets', () => {
    vi.useFakeTimers();
    const onTimeout = vi.fn();

    const ctrl = createSseStreamTimeoutController(
      { connectTimeoutMs: 1, firstProgressTimeoutMs: 10, idleTimeoutMs: 50 },
      { onTimeout },
    );

    ctrl.resetIdleTimer();
    vi.advanceTimersByTime(40);
    ctrl.resetIdleTimer();
    vi.advanceTimersByTime(40);
    expect(onTimeout).not.toHaveBeenCalled();

    vi.advanceTimersByTime(10);
    expect(onTimeout).toHaveBeenCalledWith({ type: 'idle', timeoutMs: 50 });

    vi.useRealTimers();
  });
});
