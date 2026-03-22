import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import { ErrorResponseSchema } from '../schemas/errorResponse';
import { EvidenceSchema } from '../schemas/evidence';
import { EvidenceChainSchema } from '../schemas/evidenceChain';
import { SseEnvelopeSchema } from '../schemas/sseEnvelope';
import { SseReconnectConfigSchema, WebRuntimeConfigSchema } from '../schemas/config';

describe('contract schemas', () => {
  it('ErrorResponseSchema parses minimal error response', () => {
    const parsed = ErrorResponseSchema.parse({
      code: 'VALIDATION_ERROR',
      message: 'Invalid tool parameters',
      details: { fieldErrors: [{ path: 'x', reason: 'bad' }] },
      retryable: false,
      requestId: 'r1',
    });

    expect(parsed.code).toBe('VALIDATION_ERROR');
    expect(parsed.requestId).toBe('r1');
  });

  it('SseEnvelopeSchema parses meta/error/final envelopes', () => {
    const meta = SseEnvelopeSchema.parse({
      type: 'meta',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 1,
      payload: {
        capabilities: {
          streaming: true,
          evidenceIncremental: true,
          cancellationSupported: true,
        },
      },
    });

    expect(meta.type).toBe('meta');

    const err = SseEnvelopeSchema.parse({
      type: 'error',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 2,
      payload: {
        code: 'AUTH_ERROR',
        message: 'Missing tenant scope',
        details: null,
        retryable: false,
        requestId: 'r1',
      },
    });

    expect(err.type).toBe('error');

    const progress = SseEnvelopeSchema.parse({
      type: 'progress',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 3,
      payload: { stage: 'tooling', message: 'Calling tool' },
    });

    expect(progress.type).toBe('progress');

    const final = SseEnvelopeSchema.parse({
      type: 'final',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 4,
      payload: { status: 'success' },
    });

    expect(final.type).toBe('final');
  });

  it('SseEnvelopeSchema parses message.delta envelope', () => {
    const evt = SseEnvelopeSchema.parse({
      type: 'message.delta',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 2,
      payload: { delta: 'hello' },
    });

    expect(evt.type).toBe('message.delta');
  });

  it('SseEnvelopeSchema parses guardrail warning and validates hit details', () => {
    const evt = SseEnvelopeSchema.parse({
      type: 'warning',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 2,
      payload: {
        code: 'GUARDRAIL_BLOCKED',
        message: 'Guardrail warning: request will be degraded',
        details: {
          stage: 'guardrail.input',
          hits: [
            {
              ruleId: 'GUARDRAIL_INJ_DIRECT_IGNORE_RULES',
              category: 'prompt_injection',
              hitLocation: 'input',
              reasonSummary: 'Prompt injection pattern detected',
            },
          ],
        },
      },
    });

    expect(evt.type).toBe('warning');

    const GuardrailHitSchema = z
      .object({
        ruleId: z.string().min(1),
        category: z.string().min(1),
        hitLocation: z.string().min(1),
        reasonSummary: z.string().min(1),
      })
      .strict();

    const DetailsSchema = z
      .object({
        stage: z.string().min(1),
        hits: z.array(GuardrailHitSchema).min(1),
      })
      .strict();

    const payloadUnknown: unknown = evt.payload;
    const detailsUnknown: unknown = z
      .object({
        details: z.unknown(),
      })
      .passthrough()
      .parse(payloadUnknown).details;
    const parsedDetails = DetailsSchema.parse(detailsUnknown);
    expect(parsedDetails.hits[0].ruleId).toBe('GUARDRAIL_INJ_DIRECT_IGNORE_RULES');
  });

  it('SseEnvelopeSchema parses guardrail error and validates details.ruleId', () => {
    const evt = SseEnvelopeSchema.parse({
      type: 'error',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 3,
      payload: {
        code: 'GUARDRAIL_BLOCKED',
        message: 'Guardrail blocked unsafe request',
        details: {
          stage: 'guardrail.input',
          ruleId: 'GUARDRAIL_INJ_DIRECT_IGNORE_RULES',
        },
        retryable: false,
        requestId: 'r1',
      },
    });

    expect(evt.type).toBe('error');
    const payloadUnknown: unknown = evt.payload;
    const detailsUnknown: unknown = z
      .object({
        details: z.unknown(),
      })
      .passthrough()
      .parse(payloadUnknown).details;
    const parsedDetails = z
      .object({
        stage: z.string().min(1),
        ruleId: z.string().min(1),
      })
      .passthrough()
      .parse(detailsUnknown);
    expect(parsedDetails.ruleId).toBe('GUARDRAIL_INJ_DIRECT_IGNORE_RULES');
  });

  it('SseEnvelopeSchema parses intent.result and routing.decision', () => {
    const intentResult = SseEnvelopeSchema.parse({
      type: 'intent.result',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 10,
      payload: {
        intent: 'QUERY',
        confidence: 0.9,
        needsClarification: false,
        clarificationQuestions: [],
        reasonCodes: ['UNIT_TEST'],
        reasonSummary: null,
        hasWriteIntent: false,
        riskLevel: 'low',
      },
    });

    expect(intentResult.type).toBe('intent.result');

    const routingDecision = SseEnvelopeSchema.parse({
      type: 'routing.decision',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 11,
      payload: {
        decisionType: 'allow',
        selectedIntent: 'QUERY',
        allowedToolNames: ['postgres_readonly_query'],
        blockedReasonCode: null,
        clarification: null,
        draft: null,
        auditTags: { intent: 'QUERY' },
      },
    });

    expect(routingDecision.type).toBe('routing.decision');
  });

  it('SseEnvelopeSchema parses draft.created envelope', () => {
    const draftCreated = SseEnvelopeSchema.parse({
      type: 'draft.created',
      timestamp: '2026-02-23T00:00:00Z',
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      sequence: 20,
      payload: {
        draftId: 'draft_1',
        actionType: 'unknown',
        targetResourceSummary: 'unknown',
        constraints: [],
        riskLevel: 'medium',
        riskReasonCodes: ['UNIT_TEST'],
        requiredCapabilities: [],
      },
    });

    expect(draftCreated.type).toBe('draft.created');
  });

  it('EvidenceSchema parses evidence with lineageVersion', () => {
    const parsed = EvidenceSchema.parse({
      evidenceId: 'metric_lineage:oee:1.0.0',
      sourceSystem: 'Manual',
      sourceLocator: { table: 'metric_lineage', id: '1' },
      timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
      toolCallId: null,
      lineageVersion: '1.0.0',
      dataQualityScore: null,
      confidence: 'High',
      validation: 'verifiable',
      redactions: null,
    });

    expect(parsed.lineageVersion).toBe('1.0.0');
  });

  it('EvidenceSchema allows lineageVersion to be null', () => {
    const parsed = EvidenceSchema.parse({
      evidenceId: 'raw:1',
      sourceSystem: 'MES',
      sourceLocator: { table: 'fact_production_daily' },
      timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
      toolCallId: null,
      lineageVersion: null,
      dataQualityScore: 1,
      confidence: 'Medium',
      validation: 'verifiable',
      redactions: null,
    });

    expect(parsed.lineageVersion).toBeNull();
  });

  it('EvidenceChainSchema parses minimal evidence chain with tool traces', () => {
    const parsed = EvidenceChainSchema.parse({
      requestId: 'r1',
      tenantId: 't1',
      projectId: 'p1',
      sessionId: null,
      claims: [
        {
          claimId: 'c1',
          claimType: 'number',
          subject: 'oee',
          value: 0.9,
          unit: null,
          evidenceRefs: ['e1'],
          lineageVersion: null,
          isComputed: false,
          validation: 'verifiable',
        },
      ],
      evidences: [
        {
          evidenceId: 'e1',
          sourceSystem: 'Postgres',
          sourceLocator: { tableOrView: 'fact_production_daily' },
          timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
          toolCallId: 'tc1',
          lineageVersion: null,
          dataQualityScore: null,
          confidence: 'High',
          validation: 'verifiable',
          redactions: null,
        },
      ],
      citations: null,
      lineages: null,
      toolTraces: [
        {
          toolCallId: 'tc1',
          toolName: 'tool.postgres_readonly.query',
          status: 'success',
          durationMs: 12,
          argsSummary: { stage: 'tool.execution' },
          resultSummary: { rowCount: 1, truncated: false },
          error: null,
          evidenceRefs: ['e1'],
        },
      ],
      warnings: [
        {
          code: 'EVIDENCE_MISSING',
          message: 'Evidence missing for numeric claim',
          details: { claimId: 'c1' },
          requestId: 'r1',
        },
      ],
    });

    expect(parsed.requestId).toBe('r1');
    expect(parsed.toolTraces?.[0]?.toolCallId).toBe('tc1');
  });

  // 配置校验失败测试
  describe('config schema validation', () => {
    it('SseReconnectConfigSchema rejects maxDelayMs < baseDelayMs', () => {
      const result = SseReconnectConfigSchema.safeParse({
        baseDelayMs: 1000,
        maxDelayMs: 500,
        maxAttempts: 3,
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.some(i => i.path.includes('maxDelayMs'))).toBe(true);
      }
    });

    it('SseReconnectConfigSchema accepts valid config', () => {
      const result = SseReconnectConfigSchema.safeParse({
        baseDelayMs: 100,
        maxDelayMs: 1000,
        maxAttempts: 3,
      });
      expect(result.success).toBe(true);
    });

    it('WebRuntimeConfigSchema rejects invalid apiBaseUrl', () => {
      const result = WebRuntimeConfigSchema.safeParse({
        apiBaseUrl: 'not-a-url',
        tenantId: 't1',
        projectId: 'p1',
        sseReconnect: { baseDelayMs: 100, maxDelayMs: 1000, maxAttempts: 3 },
        sseTimeouts: { connectTimeoutMs: 8000, firstProgressTimeoutMs: 8000, idleTimeoutMs: 15000 },
      });
      expect(result.success).toBe(false);
    });

    it('WebRuntimeConfigSchema accepts valid config', () => {
      const result = WebRuntimeConfigSchema.safeParse({
        apiBaseUrl: 'http://localhost:8000',
        tenantId: 't1',
        projectId: 'p1',
        sseReconnect: { baseDelayMs: 100, maxDelayMs: 1000, maxAttempts: 3 },
        sseTimeouts: { connectTimeoutMs: 8000, firstProgressTimeoutMs: 8000, idleTimeoutMs: 15000 },
      });
      expect(result.success).toBe(true);
    });
  });

  // Evidence validation 字段测试
  describe('Evidence validation field', () => {
    it('EvidenceSchema accepts verifiable validation', () => {
      const result = EvidenceSchema.safeParse({
        evidenceId: 'e1',
        sourceSystem: 'MES',
        sourceLocator: { table: 't1' },
        timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
        confidence: 'High',
        validation: 'verifiable',
      });
      expect(result.success).toBe(true);
    });

    it('EvidenceSchema accepts not_verifiable validation', () => {
      const result = EvidenceSchema.safeParse({
        evidenceId: 'e1',
        sourceSystem: 'Manual',
        sourceLocator: {},
        timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
        confidence: 'Low',
        validation: 'not_verifiable',
      });
      expect(result.success).toBe(true);
    });

    it('EvidenceSchema accepts out_of_bounds validation', () => {
      const result = EvidenceSchema.safeParse({
        evidenceId: 'e1',
        sourceSystem: 'IoT',
        sourceLocator: { sensor: 'temp1' },
        timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
        confidence: 'Medium',
        validation: 'out_of_bounds',
      });
      expect(result.success).toBe(true);
    });

    it('EvidenceSchema accepts mismatch validation', () => {
      const result = EvidenceSchema.safeParse({
        evidenceId: 'e1',
        sourceSystem: 'SAP',
        sourceLocator: { table: 'cost' },
        timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
        confidence: 'Low',
        validation: 'mismatch',
      });
      expect(result.success).toBe(true);
    });

    it('EvidenceSchema rejects invalid validation value', () => {
      const result = EvidenceSchema.safeParse({
        evidenceId: 'e1',
        sourceSystem: 'MES',
        sourceLocator: {},
        timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
        confidence: 'High',
        validation: 'invalid_status',
      });
      expect(result.success).toBe(false);
    });
  });

  // SSE sequence 检查测试
  describe('SSE envelope sequence validation', () => {
    it('SseEnvelopeSchema accepts sequence 0', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'meta',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: 0,
        payload: {
          capabilities: {
            streaming: true,
            evidenceIncremental: true,
            cancellationSupported: true,
          },
        },
      });
      expect(result.success).toBe(true);
    });

    it('SseEnvelopeSchema rejects negative sequence', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'meta',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: -1,
        payload: {
          capabilities: {
            streaming: true,
            evidenceIncremental: true,
            cancellationSupported: true,
          },
        },
      });
      expect(result.success).toBe(false);
    });

    it('SseEnvelopeSchema accepts large sequence number', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'final',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: 999999,
        payload: { status: 'success' },
      });
      expect(result.success).toBe(true);
    });
  });

  // Evidence.update payload 模式测试
  describe('SseEvidenceUpdatePayload validation', () => {
    it('rejects append mode without evidences', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'evidence.update',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: 5,
        payload: {
          mode: 'append',
          evidences: null,
        },
      });
      expect(result.success).toBe(false);
    });

    it('rejects reference mode without evidenceIds', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'evidence.update',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: 5,
        payload: {
          mode: 'reference',
          evidenceIds: null,
        },
      });
      expect(result.success).toBe(false);
    });

    it('accepts append mode with evidences', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'evidence.update',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: 5,
        payload: {
          mode: 'append',
          evidences: [
            {
              evidenceId: 'e1',
              sourceSystem: 'MES',
              sourceLocator: {},
              timeRange: { start: '2026-02-23T00:00:00Z', end: '2026-02-23T00:00:01Z' },
              confidence: 'High',
              validation: 'verifiable',
            },
          ],
        },
      });
      expect(result.success).toBe(true);
    });
  });

  // Intent.result needsClarification 约束测试
  describe('Intent.result clarification validation', () => {
    it('rejects needsClarification=true with empty clarificationQuestions', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'intent.result',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: 10,
        payload: {
          intent: 'QUERY',
          confidence: 0.9,
          needsClarification: true,
          clarificationQuestions: [],
          reasonCodes: ['TEST'],
          hasWriteIntent: false,
          riskLevel: 'low',
        },
      });
      expect(result.success).toBe(false);
    });

    it('accepts needsClarification=true with clarificationQuestions', () => {
      const result = SseEnvelopeSchema.safeParse({
        type: 'intent.result',
        timestamp: '2026-02-23T00:00:00Z',
        requestId: 'r1',
        tenantId: 't1',
        projectId: 'p1',
        sessionId: null,
        sequence: 10,
        payload: {
          intent: 'QUERY',
          confidence: 0.9,
          needsClarification: true,
          clarificationQuestions: [
            { questionId: 'q1', question: 'What is the target?' },
          ],
          reasonCodes: ['TEST'],
          hasWriteIntent: false,
          riskLevel: 'low',
        },
      });
      expect(result.success).toBe(true);
    });
  });
});
