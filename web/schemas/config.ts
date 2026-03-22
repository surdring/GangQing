import { z } from 'zod';

export const SseReconnectConfigSchema = z
  .object({
    baseDelayMs: z.coerce.number().int().min(0),
    maxDelayMs: z.coerce.number().int().min(0),
    maxAttempts: z.coerce.number().int().min(0),
  })
  .strict()
  .superRefine((val, ctx) => {
    if (val.maxDelayMs < val.baseDelayMs) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'maxDelayMs must be greater than or equal to baseDelayMs',
        path: ['maxDelayMs'],
      });
    }
  });

export const SseTimeoutConfigSchema = z
  .object({
    connectTimeoutMs: z.coerce.number().int().min(1),
    firstProgressTimeoutMs: z.coerce.number().int().min(1),
    idleTimeoutMs: z.coerce.number().int().min(1),
  })
  .strict();

export const WebRuntimeConfigSchema = z
  .object({
    apiBaseUrl: z.string().url(),
    tenantId: z.string().min(1),
    projectId: z.string().min(1),
    sseReconnect: SseReconnectConfigSchema,
    sseTimeouts: SseTimeoutConfigSchema,
  })
  .strict();

// Feature Flags Configuration
export const FeatureFlagsSchema = z.object({
  enableAudit: z.boolean().default(true),
  enableIsolation: z.boolean().default(true),
  enableEvidencePanel: z.boolean().default(true),
  enableStreaming: z.boolean().default(true),
});

// Logging Configuration
export const LoggingConfigSchema = z.object({
  level: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
  enableConsole: z.boolean().default(true),
});

// Complete Application Configuration
export const AppConfigSchema = z.object({
  runtime: WebRuntimeConfigSchema,
  features: FeatureFlagsSchema,
  logging: LoggingConfigSchema,
});

// Type exports
export type SseReconnectConfig = z.infer<typeof SseReconnectConfigSchema>;
export type SseTimeoutConfig = z.infer<typeof SseTimeoutConfigSchema>;
export type WebRuntimeConfig = z.infer<typeof WebRuntimeConfigSchema>;
export type FeatureFlags = z.infer<typeof FeatureFlagsSchema>;
export type LoggingConfig = z.infer<typeof LoggingConfigSchema>;
export type AppConfig = z.infer<typeof AppConfigSchema>;

// Configuration error codes (aligned with backend)
export const ConfigErrorCode = {
  CONFIG_MISSING: 'CONFIG_MISSING',
  CONFIG_INVALID: 'CONFIG_INVALID',
  CONFIG_TYPE_ERROR: 'CONFIG_TYPE_ERROR',
} as const;

export type ConfigErrorCode = typeof ConfigErrorCode[keyof typeof ConfigErrorCode];

// Configuration error interface
export interface ConfigError {
  code: ConfigErrorCode;
  field: string;
  message: string;
}
