import { describe, expect, it } from 'vitest';

import { requestStreamCancel } from '../hooks/sse/cancelApi';

describe('requestStreamCancel', () => {
  it('returns ok:true when response is 200', async () => {
    const fetchFn = async () => {
      return new Response('', { status: 200 });
    };

    const res = await requestStreamCancel({
      fetchFn,
      apiBaseUrl: 'http://localhost:8000',
      tenantId: 't1',
      projectId: 'p1',
      requestId: 'r1',
      accessToken: 'token',
    });

    expect(res).toEqual({ ok: true });
  });

  it('parses structured ErrorResponse when non-2xx response body matches schema', async () => {
    const fetchFn = async () => {
      return new Response(
        JSON.stringify({
          code: 'FORBIDDEN',
          message: 'Forbidden',
          details: null,
          retryable: false,
          requestId: 'r1',
        }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      );
    };

    const res = await requestStreamCancel({
      fetchFn,
      apiBaseUrl: 'http://localhost:8000',
      tenantId: 't1',
      projectId: 'p1',
      requestId: 'r1',
      accessToken: 'token',
    });

    if (res.ok === false) {
      expect(res.error.code).toBe('FORBIDDEN');
      expect(res.error.requestId).toBe('r1');
      return;
    }
    throw new Error('Expected ok=false');
  });

  it('maps invalid error body to CONTRACT_VIOLATION', async () => {
    const fetchFn = async () => {
      return new Response(JSON.stringify({ bad: 'x' }), { status: 500 });
    };

    const res = await requestStreamCancel({
      fetchFn,
      apiBaseUrl: 'http://localhost:8000',
      tenantId: 't1',
      projectId: 'p1',
      requestId: 'r1',
      accessToken: 'token',
    });

    if (res.ok === false) {
      expect(res.error.code).toBe('CONTRACT_VIOLATION');
      expect(String(res.error.message)).toContain('Cancel API');
      return;
    }
    throw new Error('Expected ok=false');
  });

  it('maps fetch failure to CONTRACT_VIOLATION', async () => {
    const fetchFn = async () => {
      throw new Error('network');
    };

    const res = await requestStreamCancel({
      fetchFn,
      apiBaseUrl: 'http://localhost:8000',
      tenantId: 't1',
      projectId: 'p1',
      requestId: 'r1',
      accessToken: 'token',
    });

    if (res.ok === false) {
      expect(res.error.code).toBe('CONTRACT_VIOLATION');
      expect(res.error.message).toBe('Cancel API request failed');
      return;
    }
    throw new Error('Expected ok=false');
  });
});
