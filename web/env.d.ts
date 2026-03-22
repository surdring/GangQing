/// <reference types="vite/client" />

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
    readonly VITE_TENANT_ID?: string;
    readonly VITE_PROJECT_ID?: string;
    readonly VITE_SSE_RECONNECT_BASE_DELAY_MS?: string;
    readonly VITE_SSE_RECONNECT_MAX_DELAY_MS?: string;
    readonly VITE_SSE_RECONNECT_MAX_ATTEMPTS?: string;
    readonly VITE_SSE_CONNECT_TIMEOUT_MS?: string;
    readonly VITE_SSE_FIRST_PROGRESS_TIMEOUT_MS?: string;
    readonly VITE_SSE_IDLE_TIMEOUT_MS?: string;
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
}

export {};
