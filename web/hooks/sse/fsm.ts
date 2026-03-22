export type SseClientPhase =
  | 'idle'
  | 'connecting'
  | 'retrying'
  | 'streaming'
  | 'timeout'
  | 'completed'
  | 'error'
  | 'canceled';

export type SseContractViolationReason =
  | 'META_NOT_FIRST'
  | 'META_SEQUENCE_NOT_ONE'
  | 'SEQUENCE_OUT_OF_ORDER'
  | 'FINAL_NOT_LAST'
  | 'ERROR_NOT_FOLLOWED_BY_FINAL';

export type SseContractViolation = {
  reason: SseContractViolationReason;
  message: string;
  details: Record<string, unknown>;
};

export type SseClientFsmState = {
  phase: SseClientPhase;
  hasMeta: boolean;
  hasFinal: boolean;
  lastSequence: number | null;
  sessionId: string | null;
  cancellationSupported: boolean | null;
  expectFinalAfterError: boolean;
};

export type SseFsmAction =
  | { type: 'meta'; payload: unknown }
  | { type: 'progress'; payload: unknown }
  | { type: 'warning'; payload: unknown }
  | { type: 'message.delta'; payload: unknown }
  | { type: 'tool.call'; payload: unknown }
  | { type: 'tool.result'; payload: unknown }
  | { type: 'evidence.update'; payload: unknown }
  | { type: 'error'; payload: unknown }
  | { type: 'final'; payload: unknown }
  | { type: 'contract.violation'; violation: SseContractViolation };

const buildViolation = (args: {
  reason: SseContractViolationReason;
  message: string;
  details: Record<string, unknown>;
}): SseContractViolation => ({
  reason: args.reason,
  message: args.message,
  details: args.details,
});

export const createSseClientFsm = (): {
  getState: () => SseClientFsmState;
  setRetrying: () => void;
  setTimeout: () => void;
  startStreaming: () => void;
  consumeEnvelope: (env: {
    type: string;
    sequence: number;
    sessionId?: string | null;
    payload: unknown;
  }) => SseFsmAction[];
} => {
  const state: SseClientFsmState = {
    phase: 'idle',
    hasMeta: false,
    hasFinal: false,
    lastSequence: null,
    sessionId: null,
    cancellationSupported: null,
    expectFinalAfterError: false,
  };

  const getState = () => ({ ...state });

  const setRetrying = () => {
    if (state.hasFinal) return;
    if (state.phase === 'error' || state.phase === 'canceled' || state.phase === 'completed') return;
    state.phase = 'retrying';
  };

  const setTimeout = () => {
    if (state.hasFinal) return;
    if (state.phase === 'error' || state.phase === 'canceled' || state.phase === 'completed') return;
    state.phase = 'timeout';
  };

  const startStreaming = () => {
    state.phase = 'streaming';
  };

  const consumeEnvelope = (env: {
    type: string;
    sequence: number;
    sessionId?: string | null;
    payload: unknown;
  }): SseFsmAction[] => {
    const actions: SseFsmAction[] = [];

    if (state.hasFinal) {
      actions.push({
        type: 'contract.violation',
        violation: buildViolation({
          reason: 'FINAL_NOT_LAST',
          message: 'SSE final event must be the last event',
          details: { eventType: env.type, receivedSequence: env.sequence },
        }),
      });
      state.phase = 'error';
      return actions;
    }

    if (state.lastSequence === null) {
      state.lastSequence = env.sequence;
    } else {
      const expectedSequence = state.lastSequence + 1;
      if (env.sequence !== expectedSequence) {
        actions.push({
          type: 'contract.violation',
          violation: buildViolation({
            reason: 'SEQUENCE_OUT_OF_ORDER',
            message: 'SSE sequence out of order',
            details: {
              lastSequence: state.lastSequence,
              expectedSequence,
              receivedSequence: env.sequence,
              eventType: env.type,
            },
          }),
        });
        state.phase = 'error';
        return actions;
      }
      state.lastSequence = env.sequence;
    }

    if (!state.hasMeta) {
      if (env.type !== 'meta') {
        actions.push({
          type: 'contract.violation',
          violation: buildViolation({
            reason: 'META_NOT_FIRST',
            message: 'SSE meta event must be the first event',
            details: { eventType: env.type, receivedSequence: env.sequence },
          }),
        });
        state.phase = 'error';
        return actions;
      }

      if (env.sequence !== 1) {
        actions.push({
          type: 'contract.violation',
          violation: buildViolation({
            reason: 'META_SEQUENCE_NOT_ONE',
            message: 'SSE meta sequence must be 1',
            details: { receivedSequence: env.sequence },
          }),
        });
        state.phase = 'error';
        return actions;
      }

      state.hasMeta = true;
      state.sessionId = (env.sessionId ?? null) || null;
      state.cancellationSupported = (() => {
        const payload = env.payload as { capabilities?: unknown } | null;
        const caps = payload && typeof payload === 'object' && payload.capabilities && typeof payload.capabilities === 'object'
          ? (payload.capabilities as Record<string, unknown>)
          : null;
        return typeof caps?.cancellationSupported === 'boolean' ? caps.cancellationSupported : null;
      })();

      actions.push({ type: 'meta', payload: env.payload });
      return actions;
    }

    if (state.expectFinalAfterError) {
      if (env.type !== 'final') {
        actions.push({
          type: 'contract.violation',
          violation: buildViolation({
            reason: 'ERROR_NOT_FOLLOWED_BY_FINAL',
            message: 'SSE error must be followed by final(status=error)',
            details: { receivedEventType: env.type, receivedSequence: env.sequence },
          }),
        });
        state.phase = 'error';
        return actions;
      }
      state.expectFinalAfterError = false;
    }

    if (env.sessionId) {
      state.sessionId = env.sessionId;
    }

    if (env.type === 'progress') actions.push({ type: 'progress', payload: env.payload });
    else if (env.type === 'warning') actions.push({ type: 'warning', payload: env.payload });
    else if (env.type === 'tool.call') actions.push({ type: 'tool.call', payload: env.payload });
    else if (env.type === 'tool.result') actions.push({ type: 'tool.result', payload: env.payload });
    else if (env.type === 'message.delta') actions.push({ type: 'message.delta', payload: env.payload });
    else if (env.type === 'evidence.update') actions.push({ type: 'evidence.update', payload: env.payload });
    else if (env.type === 'error') {
      actions.push({ type: 'error', payload: env.payload });
      state.phase = 'error';
      state.expectFinalAfterError = true;
    } else if (env.type === 'final') {
      actions.push({ type: 'final', payload: env.payload });
      state.hasFinal = true;
      const status = (env.payload as { status?: unknown } | null)?.status;
      if (status === 'cancelled') state.phase = 'canceled';
      else if (status === 'error') state.phase = 'error';
      else state.phase = 'completed';
    }

    return actions;
  };

  return { getState, setRetrying, setTimeout, startStreaming, consumeEnvelope };
};
