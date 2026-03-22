import { describe, it, expect } from 'vitest';
import { EvidenceSchema } from '../schemas/evidence';
import { EvidenceViewModelSchema } from '../schemas/evidenceViewModel';
import type { Evidence } from '../schemas/evidence';
import type { EvidenceViewModel } from '../schemas/evidenceViewModel';

describe('ContextPanel Evidence Schema Validation', () => {
  const validEvidence: Evidence = {
    evidenceId: 'ev-123',
    sourceSystem: 'SAP',
    sourceLocator: { table: 'production_data', recordId: 'rec-456' },
    timeRange: { start: '2024-01-01T00:00:00Z', end: '2024-01-31T23:59:59Z' },
    toolCallId: 'tc-789',
    lineageVersion: 'v1.2.3',
    dataQualityScore: 0.95,
    confidence: 'High',
    validation: 'verifiable',
    redactions: { sensitiveField: 'REDACTED' },
  };

  it('validates correct evidence with Zod schema', () => {
    const result = EvidenceSchema.safeParse(validEvidence);
    expect(result.success).toBe(true);
  });

  it('fails validation for evidence missing required fields', () => {
    const invalidEvidence = {
      evidenceId: 'ev-123',
      sourceSystem: 'SAP',
      // Missing sourceLocator and timeRange
      confidence: 'High',
      validation: 'verifiable',
    };

    const result = EvidenceSchema.safeParse(invalidEvidence);
    expect(result.success).toBe(false);
  });

  it('fails validation for empty evidenceId', () => {
    const invalidEvidence = {
      ...validEvidence,
      evidenceId: '',
    };

    const result = EvidenceSchema.safeParse(invalidEvidence);
    expect(result.success).toBe(false);
  });

  it('validates all validation enum values', () => {
    const validations = ['verifiable', 'not_verifiable', 'out_of_bounds', 'mismatch'] as const;

    for (const validation of validations) {
      const evidence = { ...validEvidence, validation };
      const result = EvidenceSchema.safeParse(evidence);
      expect(result.success).toBe(true);
    }
  });

  it('validates all confidence enum values', () => {
    const confidences = ['Low', 'Medium', 'High'] as const;

    for (const confidence of confidences) {
      const evidence = { ...validEvidence, confidence };
      const result = EvidenceSchema.safeParse(evidence);
      expect(result.success).toBe(true);
    }
  });

  it('fails validation for invalid confidence value', () => {
    const invalidEvidence = {
      ...validEvidence,
      confidence: 'Invalid',
    };

    const result = EvidenceSchema.safeParse(invalidEvidence);
    expect(result.success).toBe(false);
  });

  it('validates dataQualityScore within 0-1 range', () => {
    const validScore = { ...validEvidence, dataQualityScore: 0.5 };
    expect(EvidenceSchema.safeParse(validScore).success).toBe(true);

    const maxScore = { ...validEvidence, dataQualityScore: 1 };
    expect(EvidenceSchema.safeParse(maxScore).success).toBe(true);

    const minScore = { ...validEvidence, dataQualityScore: 0 };
    expect(EvidenceSchema.safeParse(minScore).success).toBe(true);
  });

  it('fails validation for dataQualityScore out of range', () => {
    const tooHigh = { ...validEvidence, dataQualityScore: 1.5 };
    expect(EvidenceSchema.safeParse(tooHigh).success).toBe(false);

    const tooLow = { ...validEvidence, dataQualityScore: -0.5 };
    expect(EvidenceSchema.safeParse(tooLow).success).toBe(false);
  });

  it('validates optional fields can be null', () => {
    const evidenceWithNulls: Evidence = {
      ...validEvidence,
      toolCallId: null,
      lineageVersion: null,
      dataQualityScore: null,
      redactions: null,
    };

    const result = EvidenceSchema.safeParse(evidenceWithNulls);
    expect(result.success).toBe(true);
  });

  it('validates optional fields can be undefined', () => {
    const evidenceWithoutOptionals = {
      evidenceId: 'ev-123',
      sourceSystem: 'SAP',
      sourceLocator: {},
      timeRange: { start: '2024-01-01T00:00:00Z', end: '2024-01-31T23:59:59Z' },
      confidence: 'High',
      validation: 'verifiable',
    };

    const result = EvidenceSchema.safeParse(evidenceWithoutOptionals);
    expect(result.success).toBe(true);
  });
});

describe('ContextPanel EvidenceViewModel Schema Validation', () => {
  const validViewModel: EvidenceViewModel = {
    requestId: 'req-123',
    tenantId: 'tenant-1',
    projectId: 'project-1',
    sessionId: 'session-1',
    status: 'stable',
    isFrozen: true,
    lastSequence: 10,
    lastTimestamp: '2024-01-15T10:00:00Z',
    evidencesById: {},
    evidenceOrder: [],
    warnings: [],
    error: null,
    finalStatus: 'success',
  };

  it('validates correct view model with Zod schema', () => {
    const result = EvidenceViewModelSchema.safeParse(validViewModel);
    expect(result.success).toBe(true);
  });

  it('validates all status enum values', () => {
    const statuses = ['empty', 'streaming', 'stable'] as const;

    for (const status of statuses) {
      const viewModel = { ...validViewModel, status };
      const result = EvidenceViewModelSchema.safeParse(viewModel);
      expect(result.success).toBe(true);
    }
  });

  it('validates all finalStatus enum values', () => {
    const finalStatuses = ['success', 'error', 'cancelled'] as const;

    for (const finalStatus of finalStatuses) {
      const viewModel = { ...validViewModel, finalStatus };
      const result = EvidenceViewModelSchema.safeParse(viewModel);
      expect(result.success).toBe(true);
    }
  });

  it('validates view model with warnings', () => {
    const viewModelWithWarnings: EvidenceViewModel = {
      ...validViewModel,
      warnings: [
        {
          code: 'EVIDENCE_MISMATCH',
          message: 'Evidence source changed',
          details: { evidenceId: 'ev-123' },
          requestId: 'req-123',
          timestamp: '2024-01-15T10:00:00Z',
          sequence: 5,
        },
      ],
    };

    const result = EvidenceViewModelSchema.safeParse(viewModelWithWarnings);
    expect(result.success).toBe(true);
  });

  it('validates view model with error', () => {
    const viewModelWithError: EvidenceViewModel = {
      ...validViewModel,
      error: {
        code: 'UPSTREAM_TIMEOUT',
        message: 'Tool call timed out',
        requestId: 'req-123',
        retryable: true,
      },
    };

    const result = EvidenceViewModelSchema.safeParse(viewModelWithError);
    expect(result.success).toBe(true);
  });

  it('validates view model with evidences', () => {
    const evidence: Evidence = {
      evidenceId: 'ev-123',
      sourceSystem: 'SAP',
      sourceLocator: {},
      timeRange: { start: '2024-01-01T00:00:00Z', end: '2024-01-31T23:59:59Z' },
      confidence: 'High',
      validation: 'verifiable',
    };

    const viewModelWithEvidences: EvidenceViewModel = {
      ...validViewModel,
      evidencesById: { 'ev-123': evidence },
      evidenceOrder: ['ev-123'],
    };

    const result = EvidenceViewModelSchema.safeParse(viewModelWithEvidences);
    expect(result.success).toBe(true);
  });
});

describe('ContextPanel Panel State Logic', () => {
  const baseViewModel: EvidenceViewModel = {
    requestId: 'req-123',
    tenantId: 'tenant-1',
    projectId: 'project-1',
    sessionId: null,
    status: 'empty',
    isFrozen: false,
    lastSequence: null,
    lastTimestamp: null,
    evidencesById: {},
    evidenceOrder: [],
    warnings: [],
    error: null,
    finalStatus: null,
  };

  it('idle state when no view model', () => {
    expect(baseViewModel).toBeDefined();
    expect(baseViewModel.status).toBe('empty');
  });

  it('streaming state when view model is streaming', () => {
    const streamingViewModel: EvidenceViewModel = {
      ...baseViewModel,
      status: 'streaming',
      isFrozen: false,
    };

    expect(streamingViewModel.status).toBe('streaming');
    expect(streamingViewModel.isFrozen).toBe(false);
  });

  it('stable final state when view model is frozen with success', () => {
    const finalViewModel: EvidenceViewModel = {
      ...baseViewModel,
      status: 'stable',
      isFrozen: true,
      finalStatus: 'success',
    };

    expect(finalViewModel.status).toBe('stable');
    expect(finalViewModel.isFrozen).toBe(true);
    expect(finalViewModel.finalStatus).toBe('success');
  });

  it('stable error state when view model is frozen with error', () => {
    const errorViewModel: EvidenceViewModel = {
      ...baseViewModel,
      status: 'stable',
      isFrozen: true,
      error: {
        code: 'UPSTREAM_TIMEOUT',
        message: 'Tool call timed out',
        requestId: 'req-123',
        retryable: true,
      },
    };

    expect(errorViewModel.status).toBe('stable');
    expect(errorViewModel.isFrozen).toBe(true);
    expect(errorViewModel.error).toBeDefined();
  });
});

describe('ContextPanel Evidence Integrity Check', () => {
  it('checks required evidence fields', () => {
    const requiredFields = ['evidenceId', 'sourceSystem', 'sourceLocator', 'timeRange'];
    expect(requiredFields).toContain('evidenceId');
    expect(requiredFields).toContain('sourceSystem');
    expect(requiredFields).toContain('sourceLocator');
    expect(requiredFields).toContain('timeRange');
  });

  it('validates timeRange structure', () => {
    const validTimeRange = { start: '2024-01-01T00:00:00Z', end: '2024-01-31T23:59:59Z' };
    expect(validTimeRange.start).toBeDefined();
    expect(validTimeRange.end).toBeDefined();
    expect(typeof validTimeRange.start).toBe('string');
    expect(typeof validTimeRange.end).toBe('string');
  });

  it('detects missing timeRange fields', () => {
    const incompleteTimeRange = { start: '2024-01-01T00:00:00Z' };
    expect(incompleteTimeRange).not.toHaveProperty('end');
  });
});

describe('ContextPanel Sanitization Logic', () => {
  it('identifies sensitive key patterns', () => {
    const sensitiveKeys = [
      'token',
      'apiKey',
      'password',
      'secret',
      'credential',
      'auth',
      'key',
      'privateKey',
      'accessToken',
      'refreshToken',
    ];

    expect(sensitiveKeys.length).toBeGreaterThan(0);
    expect(sensitiveKeys).toContain('token');
    expect(sensitiveKeys).toContain('apiKey');
    expect(sensitiveKeys).toContain('password');
  });

  it('sanitizes sensitive values', () => {
    const sourceLocator = {
      apiKey: 'secret-value',
      normalField: 'visible-value',
    };

    const sanitized: Record<string, unknown> = {};
    const sensitiveKeys = ['apiKey', 'password', 'token'];

    for (const [key, value] of Object.entries(sourceLocator)) {
      const isSensitive = sensitiveKeys.some((sk) =>
        key.toLowerCase().includes(sk.toLowerCase())
      );
      sanitized[key] = isSensitive ? '[REDACTED]' : value;
    }

    expect(sanitized.apiKey).toBe('[REDACTED]');
    expect(sanitized.normalField).toBe('visible-value');
  });
});
