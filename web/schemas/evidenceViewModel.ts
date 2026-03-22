import { z } from 'zod';

import { EvidenceSchema, type Evidence } from './evidence';
import { ErrorResponseSchema, type ErrorResponse } from './errorResponse';

const ISODateTimeSchema = z.string().min(1);

export const EvidenceViewModelWarningSchema = z
  .object({
    code: z.string().min(1),
    message: z.string().min(1),
    details: z.record(z.unknown()).nullable().optional(),
    requestId: z.string().min(1),
    timestamp: ISODateTimeSchema,
    sequence: z.number().int().nonnegative(),
  })
  .strict();

export type EvidenceViewModelWarning = z.infer<typeof EvidenceViewModelWarningSchema>;

export const EvidenceViewModelSchema = z
  .object({
    requestId: z.string().min(1),
    tenantId: z.string().min(1),
    projectId: z.string().min(1),
    sessionId: z.string().min(1).nullable().optional(),

    status: z.enum(['empty', 'streaming', 'stable']),
    isFrozen: z.boolean(),

    lastSequence: z.number().int().nonnegative().nullable(),
    lastTimestamp: ISODateTimeSchema.nullable(),

    evidencesById: z.record(EvidenceSchema),
    evidenceOrder: z.array(z.string().min(1)),

    warnings: z.array(EvidenceViewModelWarningSchema),
    error: ErrorResponseSchema.nullable(),

    finalStatus: z.enum(['success', 'error', 'cancelled']).nullable(),
  })
  .strict();

export type EvidenceViewModel = z.infer<typeof EvidenceViewModelSchema>;

export const createEmptyEvidenceViewModel = (args: {
  requestId: string;
  tenantId: string;
  projectId: string;
  sessionId: string | null;
}): EvidenceViewModel => {
  return EvidenceViewModelSchema.parse({
    requestId: args.requestId,
    tenantId: args.tenantId,
    projectId: args.projectId,
    sessionId: args.sessionId,
    status: 'empty',
    isFrozen: false,
    lastSequence: null,
    lastTimestamp: null,
    evidencesById: {},
    evidenceOrder: [],
    warnings: [],
    error: null,
    finalStatus: null,
  });
};

const stableStringify = (v: unknown): string => {
  if (v === null || v === undefined) return String(v);
  if (typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stableStringify).join(',')}]`;
  const obj = v as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`;
};

const isSameInvariantSource = (a: Evidence, b: Evidence): boolean => {
  return (
    a.sourceSystem === b.sourceSystem &&
    stableStringify(a.sourceLocator) === stableStringify(b.sourceLocator) &&
    stableStringify(a.timeRange) === stableStringify(b.timeRange)
  );
};

const mergeNullableKeepOld = <T>(prev: T | null | undefined, next: T | null | undefined): T | null | undefined => {
  if (next === null || next === undefined) {
    return prev;
  }
  return next;
};

export const mergeEvidenceViewModel = (args: {
  prev: EvidenceViewModel;
  incomingEvidences?: Evidence[] | null;
  incomingWarning?: {
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
  } | null;
  incomingError?: ErrorResponse | null;
  incomingFinalStatus?: 'success' | 'error' | 'cancelled' | null;
  meta: {
    requestId: string;
    tenantId: string;
    projectId: string;
    sessionId: string | null;
    sequence: number;
    timestamp: string;
  };
}): EvidenceViewModel => {
  const prev = args.prev;
  if (prev.isFrozen) {
    return prev;
  }

  const next: EvidenceViewModel = {
    ...prev,
    requestId: args.meta.requestId,
    tenantId: args.meta.tenantId,
    projectId: args.meta.projectId,
    sessionId: args.meta.sessionId,
    status: prev.status,
    lastSequence: args.meta.sequence,
    lastTimestamp: args.meta.timestamp,
  };

  if (args.incomingWarning) {
    next.warnings = [
      ...next.warnings,
      EvidenceViewModelWarningSchema.parse({
        code: args.incomingWarning.code,
        message: args.incomingWarning.message,
        details: args.incomingWarning.details ?? null,
        requestId: args.meta.requestId,
        timestamp: args.meta.timestamp,
        sequence: args.meta.sequence,
      }),
    ];
    if (next.status === 'empty') {
      next.status = 'streaming';
    }
  }

  if (args.incomingError) {
    next.error = args.incomingError;
    next.status = 'stable';
  }

  if (args.incomingFinalStatus) {
    next.finalStatus = args.incomingFinalStatus;
    next.status = 'stable';
    next.isFrozen = true;
  }

  if (args.incomingEvidences && args.incomingEvidences.length > 0) {
    if (next.status === 'empty') {
      next.status = 'streaming';
    }

    const evidencesById = { ...next.evidencesById };
    let evidenceOrder = [...next.evidenceOrder];

    for (const incoming of args.incomingEvidences) {
      const prevEvidence = evidencesById[incoming.evidenceId];
      if (!prevEvidence) {
        evidencesById[incoming.evidenceId] = incoming;
        if (!evidenceOrder.includes(incoming.evidenceId)) {
          evidenceOrder.push(incoming.evidenceId);
        }
        continue;
      }

      if (!isSameInvariantSource(prevEvidence, incoming)) {
        const degraded: Evidence = {
          ...prevEvidence,
          validation: 'mismatch',
          confidence: prevEvidence.confidence,
          toolCallId: mergeNullableKeepOld(prevEvidence.toolCallId, incoming.toolCallId),
          lineageVersion: mergeNullableKeepOld(prevEvidence.lineageVersion, incoming.lineageVersion),
          dataQualityScore: mergeNullableKeepOld(prevEvidence.dataQualityScore, incoming.dataQualityScore),
          redactions: mergeNullableKeepOld(prevEvidence.redactions, incoming.redactions),
        };
        evidencesById[incoming.evidenceId] = degraded;
        next.warnings = [
          ...next.warnings,
          EvidenceViewModelWarningSchema.parse({
            code: 'EVIDENCE_MISMATCH',
            message: 'Evidence invariant source fields changed for the same evidenceId',
            details: {
              evidenceId: incoming.evidenceId,
            },
            requestId: args.meta.requestId,
            timestamp: args.meta.timestamp,
            sequence: args.meta.sequence,
          }),
        ];
        continue;
      }

      const merged: Evidence = {
        ...incoming,
        sourceSystem: prevEvidence.sourceSystem,
        sourceLocator: prevEvidence.sourceLocator,
        timeRange: prevEvidence.timeRange,
        toolCallId: mergeNullableKeepOld(prevEvidence.toolCallId, incoming.toolCallId),
        lineageVersion: mergeNullableKeepOld(prevEvidence.lineageVersion, incoming.lineageVersion),
        dataQualityScore: mergeNullableKeepOld(prevEvidence.dataQualityScore, incoming.dataQualityScore),
        redactions: mergeNullableKeepOld(prevEvidence.redactions, incoming.redactions),
      };

      evidencesById[incoming.evidenceId] = merged;
      if (!evidenceOrder.includes(incoming.evidenceId)) {
        evidenceOrder.push(incoming.evidenceId);
      }
    }

    evidenceOrder = evidenceOrder.slice().sort();

    next.evidencesById = evidencesById;
    next.evidenceOrder = evidenceOrder;
  }

  return EvidenceViewModelSchema.parse(next);
};
