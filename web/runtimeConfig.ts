import { WebRuntimeConfigSchema, type WebRuntimeConfig } from './schemas/config';

export function loadWebRuntimeConfig(): WebRuntimeConfig {
  const rawUnknown: unknown = {
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
    tenantId: import.meta.env.VITE_TENANT_ID,
    projectId: import.meta.env.VITE_PROJECT_ID,
    sseReconnect: {
      baseDelayMs: import.meta.env.VITE_SSE_RECONNECT_BASE_DELAY_MS,
      maxDelayMs: import.meta.env.VITE_SSE_RECONNECT_MAX_DELAY_MS,
      maxAttempts: import.meta.env.VITE_SSE_RECONNECT_MAX_ATTEMPTS,
    },
    sseTimeouts: {
      connectTimeoutMs: import.meta.env.VITE_SSE_CONNECT_TIMEOUT_MS,
      firstProgressTimeoutMs: import.meta.env.VITE_SSE_FIRST_PROGRESS_TIMEOUT_MS,
      idleTimeoutMs: import.meta.env.VITE_SSE_IDLE_TIMEOUT_MS,
    },
  };

  const parsed = WebRuntimeConfigSchema.safeParse(rawUnknown);
  if (!parsed.success) {
    const missingKeys: string[] = [];
    if (!import.meta.env.VITE_API_BASE_URL) missingKeys.push('VITE_API_BASE_URL');
    if (!import.meta.env.VITE_TENANT_ID) missingKeys.push('VITE_TENANT_ID');
    if (!import.meta.env.VITE_PROJECT_ID) missingKeys.push('VITE_PROJECT_ID');
    if (!import.meta.env.VITE_SSE_RECONNECT_BASE_DELAY_MS) missingKeys.push('VITE_SSE_RECONNECT_BASE_DELAY_MS');
    if (!import.meta.env.VITE_SSE_RECONNECT_MAX_DELAY_MS) missingKeys.push('VITE_SSE_RECONNECT_MAX_DELAY_MS');
    if (!import.meta.env.VITE_SSE_RECONNECT_MAX_ATTEMPTS) missingKeys.push('VITE_SSE_RECONNECT_MAX_ATTEMPTS');
    if (!import.meta.env.VITE_SSE_CONNECT_TIMEOUT_MS) missingKeys.push('VITE_SSE_CONNECT_TIMEOUT_MS');
    if (!import.meta.env.VITE_SSE_FIRST_PROGRESS_TIMEOUT_MS) missingKeys.push('VITE_SSE_FIRST_PROGRESS_TIMEOUT_MS');
    if (!import.meta.env.VITE_SSE_IDLE_TIMEOUT_MS) missingKeys.push('VITE_SSE_IDLE_TIMEOUT_MS');

    const missingText = missingKeys.length ? ` Missing: ${missingKeys.join(', ')}.` : '';
    throw new Error(`Web runtime config validation failed.${missingText}`);
  }

  return parsed.data;
}
