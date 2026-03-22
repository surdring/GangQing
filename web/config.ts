import {
  AppConfigSchema,
  FeatureFlagsSchema,
  LoggingConfigSchema,
  WebRuntimeConfigSchema,
  type AppConfig,
  ConfigErrorCode,
  type ConfigError,
} from './schemas/config';

/**
 * Build English error message for missing configuration.
 */
function buildMissingConfigMessage(field: string, envVar: string): string {
  return `[Config Validation Error] Missing required configuration: ${field}. Please set ${envVar} in .env.local or build-time environment variables.`;
}

/**
 * Build English error message for invalid configuration value.
 */
function buildInvalidConfigMessage(field: string, expected: string): string {
  return `[Config Validation Error] Invalid configuration value for ${field}. Expected: ${expected}.`;
}

/**
 * Load and validate application configuration.
 * Throws error with English message if validation fails.
 */
export function loadAppConfig(): AppConfig {
  // Load runtime configuration from environment
  const rawRuntime = {
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
    tenantId: import.meta.env.VITE_TENANT_ID,
    projectId: import.meta.env.VITE_PROJECT_ID,
    sseReconnect: {
      baseDelayMs: import.meta.env.VITE_SSE_RECONNECT_BASE_DELAY_MS ?? '1000',
      maxDelayMs: import.meta.env.VITE_SSE_RECONNECT_MAX_DELAY_MS ?? '30000',
      maxAttempts: import.meta.env.VITE_SSE_RECONNECT_MAX_ATTEMPTS ?? '5',
    },
    sseTimeouts: {
      connectTimeoutMs: import.meta.env.VITE_SSE_CONNECT_TIMEOUT_MS ?? '10000',
      firstProgressTimeoutMs: import.meta.env.VITE_SSE_FIRST_PROGRESS_TIMEOUT_MS ?? '5000',
      idleTimeoutMs: import.meta.env.VITE_SSE_IDLE_TIMEOUT_MS ?? '30000',
    },
  };

  // Parse runtime config
  const runtimeResult = WebRuntimeConfigSchema.safeParse(rawRuntime);
  if (!runtimeResult.success) {
    const errors: ConfigError[] = [];
    const missingKeys: string[] = [];

    // Check for missing required environment variables
    if (!import.meta.env.VITE_API_BASE_URL) {
      missingKeys.push('VITE_API_BASE_URL');
      errors.push({
        code: ConfigErrorCode.CONFIG_MISSING,
        field: 'VITE_API_BASE_URL',
        message: buildMissingConfigMessage('API_BASE_URL', 'VITE_API_BASE_URL'),
      });
    }
    if (!import.meta.env.VITE_TENANT_ID) {
      missingKeys.push('VITE_TENANT_ID');
      errors.push({
        code: ConfigErrorCode.CONFIG_MISSING,
        field: 'VITE_TENANT_ID',
        message: buildMissingConfigMessage('TENANT_ID', 'VITE_TENANT_ID'),
      });
    }
    if (!import.meta.env.VITE_PROJECT_ID) {
      missingKeys.push('VITE_PROJECT_ID');
      errors.push({
        code: ConfigErrorCode.CONFIG_MISSING,
        field: 'VITE_PROJECT_ID',
        message: buildMissingConfigMessage('PROJECT_ID', 'VITE_PROJECT_ID'),
      });
    }

    // Log structured errors to console
    console.error('[Config Validation Failed]');
    errors.forEach((err) => {
      console.error(`  [${err.code}] ${err.field}: ${err.message}`);
    });

    // Throw with English error message
    const missingText = missingKeys.length
      ? ` Missing environment variables: ${missingKeys.join(', ')}.`
      : '';
    throw new Error(
      `Configuration validation failed.${missingText} See .env.example for required variables.`
    );
  }

  // Parse feature flags (with defaults)
  const rawFeatures = {
    enableAudit: parseBooleanEnv(import.meta.env.VITE_FEATURE_AUDIT, true),
    enableIsolation: parseBooleanEnv(import.meta.env.VITE_FEATURE_ISOLATION, true),
    enableEvidencePanel: parseBooleanEnv(import.meta.env.VITE_FEATURE_EVIDENCE_PANEL, true),
    enableStreaming: parseBooleanEnv(import.meta.env.VITE_FEATURE_STREAMING, true),
  };
  const features = FeatureFlagsSchema.parse(rawFeatures);

  // Parse logging config (with defaults)
  const rawLogging = {
    level: (import.meta.env.VITE_LOG_LEVEL ?? 'info').toLowerCase(),
    enableConsole: parseBooleanEnv(import.meta.env.VITE_LOG_ENABLE_CONSOLE, true),
  };
  const logging = LoggingConfigSchema.parse(rawLogging);

  // Build complete app config
  const appConfig: AppConfig = {
    runtime: runtimeResult.data,
    features,
    logging,
  };

  // Final validation
  const finalResult = AppConfigSchema.safeParse(appConfig);
  if (!finalResult.success) {
    console.error('[Config Final Validation Failed]', finalResult.error.format());
    throw new Error('Configuration final validation failed. Check console for details.');
  }

  // Log successful load (in development)
  if (import.meta.env.DEV) {
    console.log('[Config] Application configuration loaded successfully');
    console.log(`  API: ${appConfig.runtime.apiBaseUrl}`);
    console.log(`  Tenant: ${appConfig.runtime.tenantId}, Project: ${appConfig.runtime.projectId}`);
    console.log(`  Features: audit=${appConfig.features.enableAudit}, streaming=${appConfig.features.enableStreaming}`);
  }

  return finalResult.data;
}

/**
 * Parse boolean environment variable with default.
 */
function parseBooleanEnv(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined) return defaultValue;
  const normalized = value.toLowerCase().trim();
  if (normalized === 'true' || normalized === '1' || normalized === 'yes') return true;
  if (normalized === 'false' || normalized === '0' || normalized === 'no') return false;
  return defaultValue;
}

// Singleton instance
let _configInstance: AppConfig | null = null;

/**
 * Get the global configuration instance (singleton).
 * On first call, loads and validates configuration.
 */
export function getConfig(): AppConfig {
  if (_configInstance === null) {
    _configInstance = loadAppConfig();
  }
  return _configInstance;
}

/**
 * Reset configuration cache (useful for testing).
 */
export function resetConfig(): void {
  _configInstance = null;
}

// Re-export types for convenience
export type { AppConfig, ConfigError };
export { ConfigErrorCode };
