import { ErrorResponseSchema, type ErrorResponse } from '../../schemas/errorResponse';

export type CancelApiResult =
  | { ok: true }
  | {
      ok: false;
      error: ErrorResponse;
    };

export type CancelApiParams = {
  fetchFn: typeof fetch;
  apiBaseUrl: string;
  tenantId: string;
  projectId: string;
  requestId: string;
  accessToken: string;
};

export const requestStreamCancel = async (params: CancelApiParams): Promise<CancelApiResult> => {
  let res: Response;
  try {
    res = await params.fetchFn(`${params.apiBaseUrl}/api/v1/chat/stream/cancel`, {
      method: 'POST',
      headers: {
        'X-Tenant-Id': params.tenantId,
        'X-Project-Id': params.projectId,
        'X-Request-Id': params.requestId,
        'Content-Type': 'application/json',
        Authorization: `Bearer ${params.accessToken}`,
      },
      body: JSON.stringify({ requestId: params.requestId }),
    });
  } catch {
    return {
      ok: false,
      error: ErrorResponseSchema.parse({
        code: 'CONTRACT_VIOLATION',
        message: 'Cancel API request failed',
        details: null,
        retryable: false,
        requestId: params.requestId,
      }),
    };
  }

  if (res.ok) {
    return { ok: true };
  }

  try {
    const bodyUnknown: unknown = await res.json();
    const parsed = ErrorResponseSchema.safeParse(bodyUnknown);
    if (parsed.success) {
      return { ok: false, error: parsed.data };
    }
  } catch {
    // ignore
  }

  return {
    ok: false,
    error: ErrorResponseSchema.parse({
      code: 'CONTRACT_VIOLATION',
      message: 'Cancel API contract violation',
      details: { httpStatus: res.status },
      retryable: false,
      requestId: params.requestId,
    }),
  };
};
