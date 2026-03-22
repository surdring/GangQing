import { useCallback, useRef, useState } from 'react';

import { ErrorResponseSchema } from '../schemas/errorResponse';
import type { SseReconnectConfig, SseTimeoutConfig } from '../schemas/config';
import { createSseClientFsm } from './sse/fsm';
import { decideShouldRetry } from './sse/retryPolicy';
import { createSseStreamTimeoutController } from './sse/timeouts';
import { requestStreamCancel } from './sse/cancelApi';
import {
  SseEnvelopeSchema,
  SseEvidenceUpdatePayloadSchema,
  SseMessageDeltaPayloadSchema,
  SseProgressPayloadSchema,
  SseFinalEnvelopeSchema,
  SseWarningPayloadSchema,
  SseToolResultPayloadSchema,
  type SseEnvelope,
} from '../schemas/sseEnvelope';
import { parseSseFrames, extractSseData } from '../utils/sseParser';
import type { z } from 'zod';

export type ChatSseStreamError = {
  code:
    | 'AUTH_ERROR'
    | 'FORBIDDEN'
    | 'CHAT_FAILED'
    | 'SSE_STREAM_NOT_READABLE'
    | 'SSE_INVALID_JSON'
    | 'SSE_CONTRACT_VIOLATION';
  httpStatus?: number;
};

export type ChatSseStreamStructuredError = z.infer<typeof ErrorResponseSchema>;

type BaseHeaders = {
  tenantId: string;
  projectId: string;
  requestId: string;
};

type UseChatSseStreamParams = {
  apiBaseUrl: string;
  tenantId: string;
  projectId: string;
  accessToken: string;
  sseReconnect: SseReconnectConfig;
  sseTimeouts: SseTimeoutConfig;
  createRequestId: () => string;
  onMessageDelta: (args: { requestId: string; sessionId: string | null; delta: string }) => void;
  onProgress: (args: { requestId: string; sessionId: string | null; payload: z.infer<typeof SseProgressPayloadSchema> }) => void;
  onWarning?: (args: {
    requestId: string;
    sessionId: string | null;
    sequence: number;
    timestamp: string;
    tenantId: string;
    projectId: string;
    payload: z.infer<typeof SseWarningPayloadSchema>;
  }) => void;
  onFinal: (args: {
    requestId: string;
    sessionId: string | null;
    sequence: number;
    timestamp: string;
    tenantId: string;
    projectId: string;
    payload: z.infer<typeof SseFinalEnvelopeSchema>['payload'];
  }) => void;
  onEvidenceUpdate: (args: {
    requestId: string;
    sessionId: string | null;
    sequence: number;
    timestamp: string;
    tenantId: string;
    projectId: string;
    payload: z.infer<typeof SseEvidenceUpdatePayloadSchema>;
  }) => void;
  onError: (args: {
    requestId: string;
    sessionId: string | null;
    sequence: number;
    timestamp: string;
    tenantId: string;
    projectId: string;
    error: ChatSseStreamStructuredError;
  }) => void;
};

const buildBaseHeaders = (h: BaseHeaders) => ({
  'X-Tenant-Id': h.tenantId,
  'X-Project-Id': h.projectId,
  'X-Request-Id': h.requestId,
});

const getErrorCode = async (res: Response): Promise<string | null> => {
  try {
    const bodyUnknown: unknown = await res.json();
    const parsed = ErrorResponseSchema.safeParse(bodyUnknown);
    return parsed.success ? parsed.data.code : null;
  } catch {
    return null;
  }
};

const buildContractViolationError = (requestId: string, message: string): ChatSseStreamStructuredError => {
  return ErrorResponseSchema.parse({
    code: 'CONTRACT_VIOLATION',
    message,
    details: null,
    retryable: false,
    requestId,
  });
};

const buildContractViolationErrorWithDetails = (
  requestId: string,
  message: string,
  details: Record<string, unknown>,
): ChatSseStreamStructuredError => {
  return ErrorResponseSchema.parse({
    code: 'CONTRACT_VIOLATION',
    message,
    details,
    retryable: false,
    requestId,
  });
};

const sleep = async (ms: number) => {
  await new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });
};

const abortableSleep = async (ms: number, signal: AbortSignal) => {
  await new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new Error('ABORTED'));
      return;
    }
    const t = setTimeout(() => resolve(), ms);
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(t);
        reject(new Error('ABORTED'));
      },
      { once: true },
    );
  });
};

const buildTimeoutError = (
  requestId: string,
  timeoutType: 'connect' | 'first_progress' | 'idle',
  timeoutMs: number,
): ChatSseStreamStructuredError => {
  return ErrorResponseSchema.parse({
    code: 'UPSTREAM_TIMEOUT',
    message: 'SSE stream timeout',
    details: { timeoutType, timeoutMs },
    retryable: true,
    requestId,
  });
};

const buildRetryExhaustedError = (requestId: string, reason: string): ChatSseStreamStructuredError => {
  return ErrorResponseSchema.parse({
    code: 'SERVICE_UNAVAILABLE',
    message: 'SSE retry attempts exhausted',
    details: { reason },
    retryable: false,
    requestId,
  });
};

const computeReconnectDelayMs = (attemptIndex: number, cfg: SseReconnectConfig): number => {
  const base = Math.max(0, cfg.baseDelayMs);
  const max = Math.max(0, cfg.maxDelayMs);
  const exp = base * Math.pow(2, Math.max(0, attemptIndex));
  const jitter = Math.floor(Math.random() * Math.min(250, base + 1));
  return Math.min(max, exp + jitter);
};

export function useChatSseStream(params: UseChatSseStreamParams) {
  const [isProcessing, setIsProcessing] = useState(false);
  const activeRequestIdRef = useRef<string | null>(null);
  const activeSessionIdRef = useRef<string | null>(null);
  const lastEnvelopeMetaRef = useRef<{
    sequence: number;
    timestamp: string;
    tenantId: string;
    projectId: string;
  } | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const cancellationSupportedRef = useRef<boolean | null>(null);
  const cancelRequestedRef = useRef<boolean>(false);

  const sendMessage = useCallback(
    async (message: string, requestIdOverride?: string): Promise<{ requestId: string } | ChatSseStreamError> => {
      if (!message.trim()) {
        return { code: 'CHAT_FAILED' };
      }

      const requestId = (requestIdOverride || '').trim() || params.createRequestId();
      activeRequestIdRef.current = requestId;
      cancelRequestedRef.current = false;
      setIsProcessing(true);

      try {
        const maxAttempts = Math.max(1, params.sseReconnect.maxAttempts || 1);

        let lastErrorRetryable: boolean | null = null;

        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
          if (abortControllerRef.current) {
            abortControllerRef.current.abort();
          }
          const abortController = new AbortController();
          abortControllerRef.current = abortController;
          const fsm = createSseClientFsm();

          if (attempt > 0) {
            fsm.setRetrying();
            const delayMs = computeReconnectDelayMs(attempt - 1, params.sseReconnect);
            params.onProgress({
              requestId,
              sessionId: activeSessionIdRef.current,
              payload: { stage: 'retrying', message: `Retrying (${attempt + 1}/${maxAttempts})` },
            });
            await sleep(delayMs);
          }

          const connectTimeoutMs = Math.max(1, params.sseTimeouts.connectTimeoutMs);
          const firstProgressTimeoutMs = Math.max(1, params.sseTimeouts.firstProgressTimeoutMs);
          const idleTimeoutMs = Math.max(1, params.sseTimeouts.idleTimeoutMs);

          let res: Response;
          try {
            res = await Promise.race([
              fetch(`${params.apiBaseUrl}/api/v1/chat/stream`, {
                method: 'POST',
                signal: abortController.signal,
                headers: {
                  ...buildBaseHeaders({
                    tenantId: params.tenantId,
                    projectId: params.projectId,
                    requestId,
                  }),
                  'Content-Type': 'application/json',
                  Authorization: `Bearer ${params.accessToken}`,
                  Accept: 'text/event-stream',
                },
                body: JSON.stringify({ message }),
              }),
              (async () => {
                await abortableSleep(connectTimeoutMs, abortController.signal);
                throw new Error('SSE_CONNECT_TIMEOUT');
              })(),
            ]);
          } catch (e) {
            const errMsg = String((e as { message?: unknown } | null)?.message || e);
            if (errMsg === 'SSE_CONNECT_TIMEOUT') {
              fsm.setTimeout();
              params.onProgress({ requestId, sessionId: activeSessionIdRef.current, payload: { stage: 'timeout', message: 'SSE connect timeout' } });
              params.onError({
                requestId,
                sessionId: activeSessionIdRef.current,
                sequence: Number.MAX_SAFE_INTEGER,
                timestamp: new Date().toISOString(),
                tenantId: params.tenantId,
                projectId: params.projectId,
                error: buildTimeoutError(requestId, 'connect', connectTimeoutMs),
              });
              lastErrorRetryable = true;
              abortController.abort();
              if (attempt === maxAttempts - 1) {
                params.onError({
                  requestId,
                  sessionId: activeSessionIdRef.current,
                  sequence: Number.MAX_SAFE_INTEGER,
                  timestamp: new Date().toISOString(),
                  tenantId: params.tenantId,
                  projectId: params.projectId,
                  error: buildRetryExhaustedError(requestId, 'connect_timeout'),
                });
                return { code: 'CHAT_FAILED' };
              }
              continue;
            }

            lastErrorRetryable = true;
            if (attempt === maxAttempts - 1) {
              return { code: 'CHAT_FAILED' };
            }
            continue;
          }

          if (!res.ok) {
            const code = await getErrorCode(res);
            if (res.status === 401 || code === 'AUTH_ERROR') {
              return { code: 'AUTH_ERROR', httpStatus: res.status };
            }
            if (res.status === 403 || code === 'FORBIDDEN') {
              return { code: 'FORBIDDEN', httpStatus: res.status };
            }
            return { code: 'CHAT_FAILED', httpStatus: res.status };
          }

          const reader = res.body?.getReader();
          if (!reader) {
            return { code: 'SSE_STREAM_NOT_READABLE' };
          }

          fsm.startStreaming();

          const decoder = new TextDecoder('utf-8');
          let buffer = '';

          let receivedBusinessEvent = false;

          const timeoutController = createSseStreamTimeoutController(
            {
              connectTimeoutMs,
              firstProgressTimeoutMs,
              idleTimeoutMs,
            },
            {
              onTimeout: ({ type, timeoutMs }) => {
                fsm.setTimeout();
                if (type === 'first_progress' && receivedBusinessEvent) {
                  return;
                }
                const timeoutMessage =
                  type === 'idle'
                    ? 'SSE idle timeout'
                    : type === 'first_progress'
                      ? 'SSE first-progress timeout'
                      : 'SSE connect timeout';

                params.onProgress({
                  requestId,
                  sessionId: activeSessionIdRef.current,
                  payload: { stage: 'timeout', message: timeoutMessage },
                });
                params.onError({
                  requestId,
                  sessionId: activeSessionIdRef.current,
                  sequence: Number.MAX_SAFE_INTEGER,
                  timestamp: new Date().toISOString(),
                  tenantId: params.tenantId,
                  projectId: params.projectId,
                  error: buildTimeoutError(requestId, type, timeoutMs),
                });
                lastErrorRetryable = true;
                abortController.abort();
              },
            },
          );

          timeoutController.startFirstProgressTimer();
          timeoutController.resetIdleTimer();

          try {
            for (;;) {
              const { value, done } = await reader.read();
              if (done) break;
              const text = decoder.decode(value, { stream: true });
              const parsedFrames = parseSseFrames(text, buffer);
              buffer = parsedFrames.buffer;

              for (const frame of parsedFrames.frames) {
                const data = extractSseData(frame);
                if (data === null) continue;

                timeoutController.resetIdleTimer();

                let jsonObj: unknown;
                try {
                  jsonObj = JSON.parse(data);
                } catch {
                  params.onError({
                    requestId,
                    sessionId: activeSessionIdRef.current,
                    sequence: Number.MAX_SAFE_INTEGER,
                    timestamp: new Date().toISOString(),
                    tenantId: params.tenantId,
                    projectId: params.projectId,
                    error: buildContractViolationError(requestId, 'SSE event JSON parse failed'),
                  });
                  throw new Error('SSE_INVALID_JSON');
                }

                const parsedEnvelope = SseEnvelopeSchema.safeParse(jsonObj);
                if (!parsedEnvelope.success) {
                  params.onError({
                    requestId,
                    sessionId: activeSessionIdRef.current,
                    sequence: Number.MAX_SAFE_INTEGER,
                    timestamp: new Date().toISOString(),
                    tenantId: params.tenantId,
                    projectId: params.projectId,
                    error: buildContractViolationError(requestId, 'SSE event contract violation'),
                  });
                  throw new Error('SSE_CONTRACT_VIOLATION');
                }

                const env: SseEnvelope = parsedEnvelope.data;

                lastEnvelopeMetaRef.current = {
                  sequence: env.sequence,
                  timestamp: env.timestamp,
                  tenantId: env.tenantId,
                  projectId: env.projectId,
                };

                const fsmActions = fsm.consumeEnvelope({
                  type: env.type,
                  sequence: env.sequence,
                  sessionId: env.sessionId ?? null,
                  payload: env.payload,
                });

                if (env.sessionId) {
                  activeSessionIdRef.current = env.sessionId;
                }

                const sessionId = activeSessionIdRef.current;

                for (const action of fsmActions) {
                  if (cancelRequestedRef.current) {
                    if (action.type === 'final') {
                      timeoutController.stopAll();
                      params.onFinal({
                        requestId,
                        sessionId: activeSessionIdRef.current,
                        sequence: env.sequence,
                        timestamp: env.timestamp,
                        tenantId: env.tenantId,
                        projectId: env.projectId,
                        payload: { status: 'cancelled' },
                      });
                      return { requestId };
                    }
                    continue;
                  }

                  if (action.type === 'meta') {
                    const st = fsm.getState();
                    cancellationSupportedRef.current = st.cancellationSupported;
                    continue;
                  }

                  if (action.type === 'contract.violation') {
                    params.onError({
                      requestId,
                      sessionId,
                      sequence: env.sequence,
                      timestamp: env.timestamp,
                      tenantId: env.tenantId,
                      projectId: env.projectId,
                      error: buildContractViolationErrorWithDetails(requestId, action.violation.message, {
                        ...action.violation.details,
                        reason: action.violation.reason,
                      }),
                    });
                    throw new Error('SSE_CONTRACT_VIOLATION');
                  }

                  if (action.type === 'progress') {
                    receivedBusinessEvent = true;
                    timeoutController.stopFirstProgressTimer();
                    params.onProgress({ requestId, sessionId, payload: SseProgressPayloadSchema.parse(action.payload) });
                    continue;
                  }

                  if (action.type === 'message.delta') {
                    receivedBusinessEvent = true;
                    timeoutController.stopFirstProgressTimer();
                    const parsedPayload = SseMessageDeltaPayloadSchema.parse(action.payload);
                    params.onMessageDelta({ requestId, sessionId, delta: String(parsedPayload.delta ?? '') });
                    continue;
                  }

                  if (action.type === 'warning') {
                    receivedBusinessEvent = true;
                    timeoutController.stopFirstProgressTimer();
                    if (params.onWarning) {
                      const parsedWarning = SseWarningPayloadSchema.parse(action.payload);
                      params.onWarning({
                        requestId,
                        sessionId,
                        sequence: env.sequence,
                        timestamp: env.timestamp,
                        tenantId: env.tenantId,
                        projectId: env.projectId,
                        payload: parsedWarning,
                      });
                    }
                    continue;
                  }

                  if (action.type === 'tool.call') {
                    receivedBusinessEvent = true;
                    timeoutController.stopFirstProgressTimer();
                    continue;
                  }

                  if (action.type === 'tool.result') {
                    receivedBusinessEvent = true;
                    timeoutController.stopFirstProgressTimer();
                    const parsedPayload = SseToolResultPayloadSchema.parse(action.payload);
                    if (parsedPayload.status === 'failure' && parsedPayload.error) {
                      lastErrorRetryable = Boolean(parsedPayload.error.retryable);
                      params.onError({
                        requestId,
                        sessionId,
                        sequence: env.sequence,
                        timestamp: env.timestamp,
                        tenantId: env.tenantId,
                        projectId: env.projectId,
                        error: parsedPayload.error,
                      });
                    }
                    continue;
                  }

                  if (action.type === 'evidence.update') {
                    receivedBusinessEvent = true;
                    timeoutController.stopFirstProgressTimer();
                    const parsedPayload = SseEvidenceUpdatePayloadSchema.parse(action.payload);
                    params.onEvidenceUpdate({
                      requestId,
                      sessionId,
                      sequence: env.sequence,
                      timestamp: env.timestamp,
                      tenantId: env.tenantId,
                      projectId: env.projectId,
                      payload: parsedPayload,
                    });
                    continue;
                  }

                  if (action.type === 'error') {
                    receivedBusinessEvent = true;
                    timeoutController.stopFirstProgressTimer();
                    const parsedErr = ErrorResponseSchema.parse(action.payload);
                    lastErrorRetryable = Boolean(parsedErr.retryable);
                    params.onError({
                      requestId,
                      sessionId,
                      sequence: env.sequence,
                      timestamp: env.timestamp,
                      tenantId: env.tenantId,
                      projectId: env.projectId,
                      error: parsedErr,
                    });
                    continue;
                  }

                  if (action.type === 'final') {
                    receivedBusinessEvent = true;
                    timeoutController.stopAll();
                    const parsedFinalPayload = SseFinalEnvelopeSchema.shape.payload.parse(action.payload);
                    params.onFinal({
                      requestId,
                      sessionId,
                      sequence: env.sequence,
                      timestamp: env.timestamp,
                      tenantId: env.tenantId,
                      projectId: env.projectId,
                      payload: parsedFinalPayload,
                    });

                    const payload = action.payload as { status?: unknown } | null;
                    const status = payload?.status;
                    if (status === 'error') {
                      const decision = decideShouldRetry({
                        attemptIndex: attempt,
                        maxAttempts,
                        isRetryable: lastErrorRetryable === true,
                        isCancelRequested: cancelRequestedRef.current,
                      });

                      if (decision.shouldRetry) {
                        params.onProgress({
                          requestId,
                          sessionId,
                          payload: { stage: 'retrying', message: 'SSE error retry scheduled' },
                        });
                        break;
                      }

                      if (decision.reason === 'attempts_exhausted') {
                        params.onError({
                          requestId,
                          sessionId,
                          sequence: env.sequence,
                          timestamp: env.timestamp,
                          tenantId: env.tenantId,
                          projectId: env.projectId,
                          error: buildRetryExhaustedError(requestId, 'retryable_error'),
                        });
                      }
                      return { code: 'CHAT_FAILED' };
                    }
                    if (status === 'cancelled') {
                      return { requestId };
                    }
                    return { requestId };
                  }
                }

                if (abortController.signal.aborted) {
                  throw new Error('SSE_ABORTED');
                }
              }

              if (abortController.signal.aborted) {
                throw new Error('SSE_ABORTED');
              }
            }

            timeoutController.stopAll();

            const st = fsm.getState();
            if (st.expectFinalAfterError) {
              const meta =
                lastEnvelopeMetaRef.current ||
                ({
                  sequence: Number.MAX_SAFE_INTEGER,
                  timestamp: new Date().toISOString(),
                  tenantId: params.tenantId,
                  projectId: params.projectId,
                } as const);
              params.onError({
                requestId,
                sessionId: activeSessionIdRef.current,
                sequence: meta.sequence,
                timestamp: meta.timestamp,
                tenantId: meta.tenantId,
                projectId: meta.projectId,
                error: buildContractViolationError(requestId, 'SSE error must be followed by final(status=error)'),
              });
              if (receivedBusinessEvent) {
                throw new Error('SSE_CONTRACT_VIOLATION');
              }

              params.onFinal({
                requestId,
                sessionId: activeSessionIdRef.current,
                sequence: Number.MAX_SAFE_INTEGER,
                timestamp: new Date().toISOString(),
                tenantId: params.tenantId,
                projectId: params.projectId,
                payload: { status: 'cancelled' },
              });
              return { requestId };
            }

            if (attempt === maxAttempts - 1) {
              return { code: 'CHAT_FAILED' };
            }
          } catch (e) {
            const errMsg = String((e as { message?: unknown } | null)?.message || e);
            const aborted = abortController.signal.aborted;
            const meta =
              lastEnvelopeMetaRef.current ||
              ({
                sequence: Number.MAX_SAFE_INTEGER,
                timestamp: new Date().toISOString(),
                tenantId: params.tenantId,
                projectId: params.projectId,
              } as const);

            if (aborted) {
              timeoutController.stopAll();
              params.onFinal({
                requestId,
                sessionId: activeSessionIdRef.current,
                sequence: meta.sequence,
                timestamp: meta.timestamp,
                tenantId: meta.tenantId,
                projectId: meta.projectId,
                payload: { status: 'cancelled' },
              });

              if (errMsg === 'SSE_ABORTED') {
                const decision = decideShouldRetry({
                  attemptIndex: attempt,
                  maxAttempts,
                  isRetryable: true,
                  isCancelRequested: cancelRequestedRef.current,
                });

                if (decision.shouldRetry) {
                  continue;
                }

                if (decision.reason === 'attempts_exhausted') {
                  params.onError({
                    requestId,
                    sessionId: activeSessionIdRef.current,
                    sequence: meta.sequence,
                    timestamp: meta.timestamp,
                    tenantId: meta.tenantId,
                    projectId: meta.projectId,
                    error: buildRetryExhaustedError(requestId, 'aborted'),
                  });
                }
              }

              return { requestId };
            }

            if (attempt === maxAttempts - 1) {
              if (errMsg === 'SSE_INVALID_JSON') {
                return { code: 'SSE_INVALID_JSON' };
              }
              if (errMsg === 'SSE_CONTRACT_VIOLATION') {
                return { code: 'SSE_CONTRACT_VIOLATION' };
              }
              return { code: 'CHAT_FAILED' };
            }

            continue;
          }
        }

        return { code: 'CHAT_FAILED' };
      } finally {
        setIsProcessing(false);
      }
    },
    [params],
  );

  const cancelActiveRequest = useCallback(async (): Promise<void> => {
    const requestId = activeRequestIdRef.current;
    if (!requestId) return;

    cancelRequestedRef.current = true;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    if (cancellationSupportedRef.current !== true) {
      return;
    }

    const result = await requestStreamCancel({
      fetchFn: fetch,
      apiBaseUrl: params.apiBaseUrl,
      tenantId: params.tenantId,
      projectId: params.projectId,
      requestId,
      accessToken: params.accessToken,
    });

    if (result.ok === false) {
      params.onError({
        requestId,
        sessionId: activeSessionIdRef.current,
        sequence: Number.MAX_SAFE_INTEGER,
        timestamp: new Date().toISOString(),
        tenantId: params.tenantId,
        projectId: params.projectId,
        error: result.error,
      });
    }
  }, [params]);

  return {
    isProcessing,
    activeRequestId: activeRequestIdRef.current,
    sendMessage,
    cancelActiveRequest,
  };
}
