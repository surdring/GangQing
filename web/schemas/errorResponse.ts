import { z } from 'zod';

export const ErrorResponseSchema = z
  .object({
    code: z.string().min(1),
    message: z.string().min(1),
    details: z.record(z.unknown()).nullable().optional(),
    retryable: z.boolean(),
    requestId: z.string().min(1),
  })
  .strict();

export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;
