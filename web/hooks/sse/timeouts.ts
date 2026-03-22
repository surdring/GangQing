export type SseTimeoutType = 'connect' | 'first_progress' | 'idle';

export type SseTimeoutConfig = {
  connectTimeoutMs: number;
  firstProgressTimeoutMs: number;
  idleTimeoutMs: number;
};

export type SseTimeoutCallbacks = {
  onTimeout: (args: { type: SseTimeoutType; timeoutMs: number }) => void;
};

export type SseStreamTimeoutController = {
  startFirstProgressTimer: () => void;
  stopFirstProgressTimer: () => void;
  resetIdleTimer: () => void;
  stopIdleTimer: () => void;
  stopAll: () => void;
};

export const createSseStreamTimeoutController = (
  cfg: SseTimeoutConfig,
  cb: SseTimeoutCallbacks,
): SseStreamTimeoutController => {
  let firstProgressTimer: ReturnType<typeof setTimeout> | null = null;
  let idleTimer: ReturnType<typeof setTimeout> | null = null;

  const stopFirstProgressTimer = () => {
    if (firstProgressTimer) {
      clearTimeout(firstProgressTimer);
      firstProgressTimer = null;
    }
  };

  const stopIdleTimer = () => {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
  };

  const startFirstProgressTimer = () => {
    stopFirstProgressTimer();
    const timeoutMs = Math.max(1, cfg.firstProgressTimeoutMs);
    firstProgressTimer = setTimeout(() => {
      cb.onTimeout({ type: 'first_progress', timeoutMs });
    }, timeoutMs);
  };

  const resetIdleTimer = () => {
    stopIdleTimer();
    const timeoutMs = Math.max(1, cfg.idleTimeoutMs);
    idleTimer = setTimeout(() => {
      cb.onTimeout({ type: 'idle', timeoutMs });
    }, timeoutMs);
  };

  const stopAll = () => {
    stopFirstProgressTimer();
    stopIdleTimer();
  };

  return {
    startFirstProgressTimer,
    stopFirstProgressTimer,
    resetIdleTimer,
    stopIdleTimer,
    stopAll,
  };
};
