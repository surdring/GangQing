import { describe, expect, it } from 'vitest';

import { createSseClientFsm } from '../hooks/sse/fsm';

const metaPayload = (cancellationSupported: boolean) => ({
  capabilities: {
    streaming: true,
    evidenceIncremental: true,
    cancellationSupported,
  },
});

describe('SSE client FSM', () => {
  it('accepts minimal sequence meta -> progress -> message.delta -> final(success)', () => {
    const fsm = createSseClientFsm();
    fsm.startStreaming();

    const a1 = fsm.consumeEnvelope({ type: 'meta', sequence: 1, sessionId: 's1', payload: metaPayload(true) });
    expect(a1[0]?.type).toBe('meta');
    expect(fsm.getState().cancellationSupported).toBe(true);

    const a2 = fsm.consumeEnvelope({ type: 'progress', sequence: 2, payload: { stage: 'tooling', message: 'Calling tool' } });
    expect(a2[0]?.type).toBe('progress');

    const a3 = fsm.consumeEnvelope({ type: 'message.delta', sequence: 3, payload: { delta: 'hello' } });
    expect(a3[0]?.type).toBe('message.delta');

    const a4 = fsm.consumeEnvelope({ type: 'final', sequence: 4, payload: { status: 'success' } });
    expect(a4[0]?.type).toBe('final');
    expect(fsm.getState().phase).toBe('completed');
  });

  it('rejects when first event is not meta', () => {
    const fsm = createSseClientFsm();
    fsm.startStreaming();

    const actions = fsm.consumeEnvelope({
      type: 'progress',
      sequence: 1,
      payload: { stage: 'tooling', message: 'Calling tool' },
    });

    expect(actions[0]?.type).toBe('contract.violation');
    if (actions[0]?.type === 'contract.violation') {
      expect(actions[0].violation.reason).toBe('META_NOT_FIRST');
    }
  });

  it('rejects when meta.sequence is not 1', () => {
    const fsm = createSseClientFsm();
    fsm.startStreaming();

    const actions = fsm.consumeEnvelope({
      type: 'meta',
      sequence: 2,
      payload: metaPayload(true),
    });

    expect(actions[0]?.type).toBe('contract.violation');
    if (actions[0]?.type === 'contract.violation') {
      expect(actions[0].violation.reason).toBe('META_SEQUENCE_NOT_ONE');
    }
  });

  it('rejects when sequence is not strictly +1', () => {
    const fsm = createSseClientFsm();
    fsm.startStreaming();

    fsm.consumeEnvelope({ type: 'meta', sequence: 1, payload: metaPayload(true) });
    const actions = fsm.consumeEnvelope({ type: 'progress', sequence: 3, payload: { stage: 'x', message: 'y' } });

    expect(actions[0]?.type).toBe('contract.violation');
    if (actions[0]?.type === 'contract.violation') {
      expect(actions[0].violation.reason).toBe('SEQUENCE_OUT_OF_ORDER');
      expect(actions[0].violation.details.expectedSequence).toBe(2);
      expect(actions[0].violation.details.receivedSequence).toBe(3);
    }
  });

  it('requires error to be followed by final', () => {
    const fsm = createSseClientFsm();
    fsm.startStreaming();

    fsm.consumeEnvelope({ type: 'meta', sequence: 1, payload: metaPayload(true) });
    const errActions = fsm.consumeEnvelope({ type: 'error', sequence: 2, payload: { code: 'INTERNAL_ERROR' } });
    expect(errActions[0]?.type).toBe('error');

    const next = fsm.consumeEnvelope({ type: 'progress', sequence: 3, payload: { stage: 'x', message: 'y' } });
    expect(next[0]?.type).toBe('contract.violation');
    if (next[0]?.type === 'contract.violation') {
      expect(next[0].violation.reason).toBe('ERROR_NOT_FOLLOWED_BY_FINAL');
    }
  });

  it('rejects any event after final', () => {
    const fsm = createSseClientFsm();
    fsm.startStreaming();

    fsm.consumeEnvelope({ type: 'meta', sequence: 1, payload: metaPayload(true) });
    fsm.consumeEnvelope({ type: 'final', sequence: 2, payload: { status: 'success' } });

    const after = fsm.consumeEnvelope({ type: 'progress', sequence: 3, payload: { stage: 'x', message: 'y' } });
    expect(after[0]?.type).toBe('contract.violation');
    if (after[0]?.type === 'contract.violation') {
      expect(after[0].violation.reason).toBe('FINAL_NOT_LAST');
    }
  });

  it('enters canceled phase when final(status=cancelled)', () => {
    const fsm = createSseClientFsm();
    fsm.startStreaming();

    fsm.consumeEnvelope({ type: 'meta', sequence: 1, payload: metaPayload(true) });
    const a2 = fsm.consumeEnvelope({ type: 'final', sequence: 2, payload: { status: 'cancelled' } });
    expect(a2[0]?.type).toBe('final');
    expect(fsm.getState().phase).toBe('canceled');
  });

  it('allows explicit retrying/timeout phases before final', () => {
    const fsm = createSseClientFsm();
    fsm.setRetrying();
    expect(fsm.getState().phase).toBe('retrying');

    fsm.setTimeout();
    expect(fsm.getState().phase).toBe('timeout');

    fsm.startStreaming();
    expect(fsm.getState().phase).toBe('streaming');
  });
});
