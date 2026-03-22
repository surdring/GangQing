import { z } from 'zod';

const ISODateTimeSchema = z.string().min(1);

export const EvidenceTimeRangeSchema = z
  .object({
    start: ISODateTimeSchema,
    end: ISODateTimeSchema,
  })
  .strict();

export const EvidenceSchema = z
  .object({
    evidenceId: z.string().min(1),
    sourceSystem: z.string().min(1),
    sourceLocator: z.record(z.unknown()),
    timeRange: EvidenceTimeRangeSchema,
    toolCallId: z.string().min(1).nullable().optional(),
    lineageVersion: z.string().min(1).nullable().optional(),
    dataQualityScore: z.number().min(0).max(1).nullable().optional(),
    confidence: z.enum(['Low', 'Medium', 'High']),
    validation: z.enum(['verifiable', 'not_verifiable', 'out_of_bounds', 'mismatch']),
    redactions: z.record(z.unknown()).nullable().optional(),
  })
  .strict();

export type Evidence = z.infer<typeof EvidenceSchema>;
