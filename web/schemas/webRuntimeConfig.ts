import { z } from 'zod';

export const WebRuntimeConfigSchema = z
  .object({
    apiBaseUrl: z.string().url(),
    tenantId: z.string().min(1),
    projectId: z.string().min(1),
  })
  .strict();

export type WebRuntimeConfig = z.infer<typeof WebRuntimeConfigSchema>;
