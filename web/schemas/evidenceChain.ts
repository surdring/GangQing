import { z } from 'zod';

import { EvidenceSchema } from './evidence';

export const EvidenceWarningSchema = z
  .object({
    code: z.string().min(1),
    message: z.string().min(1),
    details: z.record(z.unknown()).nullable().optional(),
    requestId: z.string().min(1),
  })
  .strict();

export const ClaimSchema = z
  .object({
    claimId: z.string().min(1),
    claimType: z.enum(['number', 'text', 'table', 'chart', 'boolean']),
    subject: z.string().min(1),
    value: z.unknown(),
    unit: z.string().nullable().optional(),
    evidenceRefs: z.array(z.string().min(1)),
    lineageVersion: z.string().min(1).nullable().optional(),
    isComputed: z.boolean(),
    validation: z.enum(['verifiable', 'not_verifiable', 'out_of_bounds', 'mismatch']),
  })
  .strict();

export const CitationSchema = z
  .object({
    citationId: z.string().min(1),
    evidenceId: z.string().min(1),
    sourceSystem: z.string().min(1),
    sourceLocator: z.record(z.unknown()),
    timeRange: z.record(z.unknown()),
    extractedAt: z.string().min(1).nullable().optional(),
    filtersSummary: z.record(z.unknown()).nullable().optional(),
  })
  .strict();

export const LineageSchema = z
  .object({
    metricName: z.string().min(1),
    lineageVersion: z.string().min(1),
    formulaId: z.string().min(1).nullable().optional(),
    inputs: z.array(z.record(z.unknown())),
  })
  .strict();

export const ToolCallTraceSchema = z
  .object({
    toolCallId: z.string().min(1),
    toolName: z.string().min(1),
    status: z.enum(['success', 'failure']),
    durationMs: z.number().int().nonnegative().nullable().optional(),
    argsSummary: z.record(z.unknown()).nullable().optional(),
    resultSummary: z.record(z.unknown()).nullable().optional(),
    error: z.record(z.unknown()).nullable().optional(),
    evidenceRefs: z.array(z.string().min(1)).nullable().optional(),
  })
  .strict();

export const EvidenceChainSchema = z
  .object({
    requestId: z.string().min(1),
    tenantId: z.string().min(1),
    projectId: z.string().min(1),
    sessionId: z.string().min(1).nullable().optional(),
    claims: z.array(ClaimSchema),
    evidences: z.array(EvidenceSchema),
    citations: z.array(CitationSchema).nullable().optional(),
    lineages: z.array(LineageSchema).nullable().optional(),
    toolTraces: z.array(ToolCallTraceSchema).nullable().optional(),
    warnings: z.array(EvidenceWarningSchema),
  })
  .strict();

export type EvidenceWarning = z.infer<typeof EvidenceWarningSchema>;
export type Claim = z.infer<typeof ClaimSchema>;
export type Citation = z.infer<typeof CitationSchema>;
export type Lineage = z.infer<typeof LineageSchema>;
export type ToolCallTrace = z.infer<typeof ToolCallTraceSchema>;
export type EvidenceChain = z.infer<typeof EvidenceChainSchema>;
