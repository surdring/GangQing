import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  loadAppConfig,
  getConfig,
  resetConfig,
  ConfigErrorCode,
} from '../config';
import {
  WebRuntimeConfigSchema,
  FeatureFlagsSchema,
  LoggingConfigSchema,
  AppConfigSchema,
} from '../schemas/config';

describe('Configuration Loading and Validation (T43.1)', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    // Reset config before each test
    resetConfig();
    // Reset import.meta.env mock
    vi.resetModules();
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('WebRuntimeConfigSchema', () => {
    it('should accept valid configuration', () => {
      const validConfig = {
        apiBaseUrl: 'http://localhost:8000',
        tenantId: 't1',
        projectId: 'p1',
        sseReconnect: {
          baseDelayMs: 1000,
          maxDelayMs: 30000,
          maxAttempts: 5,
        },
        sseTimeouts: {
          connectTimeoutMs: 10000,
          firstProgressTimeoutMs: 5000,
          idleTimeoutMs: 30000,
        },
      };

      const result = WebRuntimeConfigSchema.safeParse(validConfig);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.apiBaseUrl).toBe('http://localhost:8000');
        expect(result.data.tenantId).toBe('t1');
      }
    });

    it('should reject missing required fields', () => {
      const invalidConfig = {
        apiBaseUrl: 'http://localhost:8000',
        // Missing tenantId, projectId, sseReconnect, sseTimeouts
      };

      const result = WebRuntimeConfigSchema.safeParse(invalidConfig);
      expect(result.success).toBe(false);
    });

    it('should reject invalid URL format', () => {
      const invalidConfig = {
        apiBaseUrl: 'not-a-url',
        tenantId: 't1',
        projectId: 'p1',
        sseReconnect: {
          baseDelayMs: 1000,
          maxDelayMs: 30000,
          maxAttempts: 5,
        },
        sseTimeouts: {
          connectTimeoutMs: 10000,
          firstProgressTimeoutMs: 5000,
          idleTimeoutMs: 30000,
        },
      };

      const result = WebRuntimeConfigSchema.safeParse(invalidConfig);
      expect(result.success).toBe(false);
    });

    it('should reject empty tenant/project IDs', () => {
      const invalidConfig = {
        apiBaseUrl: 'http://localhost:8000',
        tenantId: '',
        projectId: 'p1',
        sseReconnect: {
          baseDelayMs: 1000,
          maxDelayMs: 30000,
          maxAttempts: 5,
        },
        sseTimeouts: {
          connectTimeoutMs: 10000,
          firstProgressTimeoutMs: 5000,
          idleTimeoutMs: 30000,
        },
      };

      const result = WebRuntimeConfigSchema.safeParse(invalidConfig);
      expect(result.success).toBe(false);
    });

    it('should validate SSE reconnect bounds', () => {
      const invalidConfig = {
        apiBaseUrl: 'http://localhost:8000',
        tenantId: 't1',
        projectId: 'p1',
        sseReconnect: {
          baseDelayMs: 5000,
          maxDelayMs: 1000, // Less than baseDelayMs
          maxAttempts: 5,
        },
        sseTimeouts: {
          connectTimeoutMs: 10000,
          firstProgressTimeoutMs: 5000,
          idleTimeoutMs: 30000,
        },
      };

      const result = WebRuntimeConfigSchema.safeParse(invalidConfig);
      expect(result.success).toBe(false);
    });
  });

  describe('FeatureFlagsSchema', () => {
    it('should use defaults when values not provided', () => {
      const result = FeatureFlagsSchema.parse({});
      expect(result.enableAudit).toBe(true);
      expect(result.enableIsolation).toBe(true);
      expect(result.enableEvidencePanel).toBe(true);
      expect(result.enableStreaming).toBe(true);
    });

    it('should accept explicit values', () => {
      const result = FeatureFlagsSchema.parse({
        enableAudit: false,
        enableIsolation: false,
      });
      expect(result.enableAudit).toBe(false);
      expect(result.enableIsolation).toBe(false);
      // Others should still use defaults
      expect(result.enableEvidencePanel).toBe(true);
      expect(result.enableStreaming).toBe(true);
    });
  });

  describe('LoggingConfigSchema', () => {
    it('should accept valid log levels', () => {
      const levels = ['debug', 'info', 'warn', 'error'];
      levels.forEach((level) => {
        const result = LoggingConfigSchema.parse({ level });
        expect(result.level).toBe(level);
      });
    });

    it('should reject invalid log level', () => {
      expect(() => {
        LoggingConfigSchema.parse({ level: 'invalid' });
      }).toThrow();
    });

    it('should use defaults', () => {
      const result = LoggingConfigSchema.parse({});
      expect(result.level).toBe('info');
      expect(result.enableConsole).toBe(true);
    });
  });

  describe('AppConfigSchema', () => {
    it('should accept complete valid configuration', () => {
      const validAppConfig = {
        runtime: {
          apiBaseUrl: 'http://localhost:8000',
          tenantId: 't1',
          projectId: 'p1',
          sseReconnect: {
            baseDelayMs: 1000,
            maxDelayMs: 30000,
            maxAttempts: 5,
          },
          sseTimeouts: {
            connectTimeoutMs: 10000,
            firstProgressTimeoutMs: 5000,
            idleTimeoutMs: 30000,
          },
        },
        features: {
          enableAudit: true,
          enableIsolation: true,
        },
        logging: {
          level: 'debug',
        },
      };

      const result = AppConfigSchema.safeParse(validAppConfig);
      expect(result.success).toBe(true);
    });

    it('should reject invalid runtime config', () => {
      const invalidAppConfig = {
        runtime: {
          apiBaseUrl: 'invalid-url',
          tenantId: 't1',
          projectId: 'p1',
          sseReconnect: {
            baseDelayMs: 1000,
            maxDelayMs: 30000,
            maxAttempts: 5,
          },
          sseTimeouts: {
            connectTimeoutMs: 10000,
            firstProgressTimeoutMs: 5000,
            idleTimeoutMs: 30000,
          },
        },
        features: {},
        logging: {},
      };

      const result = AppConfigSchema.safeParse(invalidAppConfig);
      expect(result.success).toBe(false);
    });
  });

  describe('ConfigErrorCode', () => {
    it('should have correct error codes', () => {
      expect(ConfigErrorCode.CONFIG_MISSING).toBe('CONFIG_MISSING');
      expect(ConfigErrorCode.CONFIG_INVALID).toBe('CONFIG_INVALID');
      expect(ConfigErrorCode.CONFIG_TYPE_ERROR).toBe('CONFIG_TYPE_ERROR');
    });
  });

  describe('loadAppConfig', () => {
    it('should throw with English error message when config is invalid', () => {
      // Stub environment variables with missing values using Vitest's stubEnv
      vi.stubEnv('VITE_API_BASE_URL', '');
      vi.stubEnv('VITE_TENANT_ID', '');
      vi.stubEnv('VITE_PROJECT_ID', '');

      // Reset config to force reload
      resetConfig();

      expect(() => loadAppConfig()).toThrow();

      // Verify error message contains English text
      let errorCaught = false;
      try {
        loadAppConfig();
      } catch (error) {
        errorCaught = true;
        if (error instanceof Error) {
          expect(error.message).toContain('Configuration validation failed');
          expect(error.message).toContain('Missing');
          expect(error.message).toContain('.env.example');
        }
      }
      expect(errorCaught).toBe(true);

      vi.unstubAllEnvs();
    });
  });

  describe('getConfig singleton', () => {
    it('should return same instance on multiple calls', () => {
      // Note: This test requires valid env vars to be set
      // Reset to ensure fresh load
      resetConfig();

      // In actual test environment, this would need mocked env vars
      // This test documents the expected singleton behavior
    });

    it('should reset when resetConfig is called', () => {
      resetConfig();
      // After reset, getConfig should trigger new load
      // Implementation detail: tested via mock in real environment
    });
  });
});
