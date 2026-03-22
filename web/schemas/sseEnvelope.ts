import { z } from 'zod';

import { ErrorResponseSchema } from './errorResponse';
import { EvidenceSchema } from './evidence';

const ISODateTimeSchema = z.string().min(1);

const SseEnvelopeBaseSchema = z
  .object({
    type: z.string().min(1),
    timestamp: ISODateTimeSchema,
    requestId: z.string().min(1),
    tenantId: z.string().min(1),
    projectId: z.string().min(1),
    sessionId: z.string().min(1).nullable().optional(),
    sequence: z.number().int().nonnegative(),
    payload: z.unknown(),
  })
  .strict();

export const SseMetaPayloadSchema = z
  .object({
    capabilities: z
      .object({
        streaming: z.boolean(),
        evidenceIncremental: z.boolean(),
        cancellationSupported: z.boolean(),
      })
      .strict(),
  })
  .strict();

export const SseMetaEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('meta'),
  payload: SseMetaPayloadSchema,
});

export const SseErrorEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('error'),
  payload: ErrorResponseSchema,
});

export const SseFinalEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('final'),
  payload: z
    .object({
      status: z.enum(['success', 'error', 'cancelled']),
    })
    .strict(),
});

export const SseProgressPayloadSchema = z
  .object({
    stage: z.string().min(1),
    message: z.string().min(1),
    stepId: z.string().min(1).optional(),
  })
  .strict();

export const SseProgressEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('progress'),
  payload: SseProgressPayloadSchema,
});

export const SseMessageDeltaPayloadSchema = z
  .object({
    delta: z.string(),
  })
  .strict();

export const SseMessageDeltaEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('message.delta'),
  payload: SseMessageDeltaPayloadSchema,
});

export const SseWarningPayloadSchema = z
  .object({
    code: z.string().min(1),
    message: z.string().min(1),
    details: z.record(z.unknown()).nullable().optional(),
  })
  .strict();

export const SseWarningEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('warning'),
  payload: SseWarningPayloadSchema,
});

export const SseToolCallPayloadSchema = z
  .object({
    toolCallId: z.string().min(1),
    toolName: z.string().min(1),
    argsSummary: z.record(z.unknown()),
  })
  .strict();

export const SseToolCallEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('tool.call'),
  payload: SseToolCallPayloadSchema,
});

export const SseToolResultPayloadSchema = z
  .object({
    toolCallId: z.string().min(1),
    toolName: z.string().min(1),
    status: z.enum(['success', 'failure']),
    resultSummary: z.record(z.unknown()).nullable().optional(),
    error: ErrorResponseSchema.nullable().optional(),
    evidenceRefs: z.array(z.string().min(1)).nullable().optional(),
  })
  .strict();

export const SseToolResultEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('tool.result'),
  payload: SseToolResultPayloadSchema,
});

export const SseEvidenceUpdatePayloadSchema = z
  .object({
    mode: z.enum(['append', 'update', 'reference']),
    evidences: z.array(EvidenceSchema).nullable().optional(),
    evidenceIds: z.array(z.string().min(1)).nullable().optional(),
  })
  .strict()
  .superRefine((obj, ctx) => {
    if (obj.mode === 'append' || obj.mode === 'update') {
      if (!obj.evidences || obj.evidences.length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'evidence.update payload.evidences is required for mode append|update',
          path: ['evidences'],
        });
      }
    }
    if (obj.mode === 'reference') {
      if (!obj.evidenceIds || obj.evidenceIds.length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'evidence.update payload.evidenceIds is required for mode reference',
          path: ['evidenceIds'],
        });
      }
    }
  });

export const SseEvidenceUpdateEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('evidence.update'),
  payload: SseEvidenceUpdatePayloadSchema,
});

const IntentTypeSchema = z.enum([
  'QUERY',
  'ANALYZE',
  'ALERT',
  'ACTION_PREPARE',
  'ACTION_EXECUTE',
]);

const RiskLevelSchema = z.enum(['low', 'medium', 'high']);

export const ClarificationQuestionSchema = z
  .object({
    questionId: z.string().min(1),
    question: z.string().min(1),
  })
  .strict();

export const IntentResultPayloadSchema = z
  .object({
    intent: IntentTypeSchema,
    confidence: z.number().min(0).max(1),
    needsClarification: z.boolean(),
    clarificationQuestions: z.array(ClarificationQuestionSchema),
    reasonCodes: z.array(z.string().min(1)),
    reasonSummary: z.string().min(1).nullable().optional(),
    hasWriteIntent: z.boolean(),
    riskLevel: RiskLevelSchema,
  })
  .strict()
  .superRefine((obj, ctx) => {
    if (obj.needsClarification && obj.clarificationQuestions.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'clarificationQuestions must not be empty when needsClarification is true',
        path: ['clarificationQuestions'],
      });
    }
  });

export const SseIntentResultEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('intent.result'),
  payload: IntentResultPayloadSchema,
});

const RouteDecisionTypeSchema = z.enum(['clarify', 'allow', 'draft', 'block']);

export const ActionDraftSchema = z
  .object({
    draftId: z.string().min(1),
    actionType: z.string().min(1),
    targetResourceSummary: z.string().min(1),
    constraints: z.array(z.string()),
    riskLevel: RiskLevelSchema,
    riskReasonCodes: z.array(z.string().min(1)),
    requiredCapabilities: z.array(z.string().min(1)),
  })
  .strict();

export const RouteDecisionPayloadSchema = z
  .object({
    decisionType: RouteDecisionTypeSchema,
    selectedIntent: IntentTypeSchema,
    allowedToolNames: z.array(z.string().min(1)),
    blockedReasonCode: z.string().min(1).nullable().optional(),
    clarification: z.array(ClarificationQuestionSchema).nullable().optional(),
    draft: ActionDraftSchema.nullable().optional(),
    auditTags: z.record(z.string().min(1)),
  })
  .strict();

export const SseRoutingDecisionEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('routing.decision'),
  payload: RouteDecisionPayloadSchema,
});

export const SseDraftCreatedEnvelopeSchema = SseEnvelopeBaseSchema.extend({
  type: z.literal('draft.created'),
  payload: ActionDraftSchema,
});

export const SseEnvelopeSchema = z.discriminatedUnion('type', [
  SseMetaEnvelopeSchema,
  SseErrorEnvelopeSchema,
  SseIntentResultEnvelopeSchema,
  SseRoutingDecisionEnvelopeSchema,
  SseDraftCreatedEnvelopeSchema,
  SseProgressEnvelopeSchema,
  SseMessageDeltaEnvelopeSchema,
  SseWarningEnvelopeSchema,
  SseToolCallEnvelopeSchema,
  SseToolResultEnvelopeSchema,
  SseEvidenceUpdateEnvelopeSchema,
  SseFinalEnvelopeSchema,
]);

export type SseEnvelope = z.infer<typeof SseEnvelopeSchema>;
