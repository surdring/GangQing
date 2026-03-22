import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, Paperclip, ChevronDown, RotateCcw } from 'lucide-react';
import ChatMessage from './ChatMessage';
import ContextPanel from './ContextPanel';
import { Message, Evidence, Scenario } from '../types';
import { useTranslation } from 'react-i18next';
import { ErrorResponseSchema } from '../schemas/errorResponse';
import { EvidenceChainSchema } from '../schemas/evidenceChain';
import type { EvidenceChain } from '../schemas/evidenceChain';
import type { Evidence as ContractEvidence } from '../schemas/evidence';
import {
  createEmptyEvidenceViewModel,
  mergeEvidenceViewModel,
  type EvidenceViewModel,
} from '../schemas/evidenceViewModel';
import { loadWebRuntimeConfig } from '../runtimeConfig';
import { useChatSseStream } from '../hooks/useChatSseStream';

interface Props {
  activeScenario: Scenario;
}

 const ChatInterface: React.FC<Props> = ({ activeScenario }) => {
  const { t, i18n } = useTranslation();
  const normalizedLanguage = (i18n.resolvedLanguage || i18n.language || 'zh').startsWith('en') ? 'en' : 'zh';
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null);
  const [activeEvidenceChain, setActiveEvidenceChain] = useState<EvidenceChain | null>(null);
  const [activeEvidenceViewModel, setActiveEvidenceViewModel] = useState<EvidenceViewModel | null>(null);
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [userId, setUserId] = useState<string>('');
  const [attachments, setAttachments] = useState<string[]>([]);
  const [manualRetryMessage, setManualRetryMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastUserMessageRef = useRef<string>('');

  const { apiBaseUrl, tenantId, projectId, sseReconnect, sseTimeouts } = loadWebRuntimeConfig();

  const createRequestId = () => {
    try {
      return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    } catch {
      return `${Date.now()}-${Math.random()}`;
    }
  };

  const handleEvidenceClick = async (ev: Evidence) => {
    setActiveEvidenceId(ev.id);
    setActiveEvidenceChain(null);
    if (!accessToken) return;
    if (!activeRequestId) return;

    try {
      const res = await fetch(`${apiBaseUrl}/api/v1/evidence/chains/${activeRequestId}`, {
        method: 'GET',
        headers: {
          ...buildBaseHeaders(activeRequestId),
          'Authorization': `Bearer ${accessToken}`,
        },
      });
      if (!res.ok) {
        return;
      }
      const body = await res.json();
      const chain = (body as any)?.evidenceChain;
      const parsed = EvidenceChainSchema.safeParse(chain);
      if (!parsed.success) {
        return;
      }
      setActiveEvidenceChain(parsed.data);
    } catch {
      return;
    }
  };

  const buildBaseHeaders = (requestId: string) => ({
    'X-Tenant-Id': tenantId,
    'X-Project-Id': projectId,
    'X-Request-Id': requestId,
  });

  const toUiEvidence = (ev: ContractEvidence): Evidence => {
    const sourceSystem = ev.sourceSystem || 'Unknown';
    const type = sourceSystem === 'SAP' || sourceSystem === 'MES' || sourceSystem === 'DCS' || sourceSystem === 'IoT'
      ? sourceSystem
      : 'Manual';
    return {
      id: ev.evidenceId,
      source: sourceSystem,
      timestamp: ev.timeRange?.end || new Date().toISOString(),
      confidence: ev.confidence,
      details: JSON.stringify(ev.sourceLocator ?? {}),
      type,
      validation: ev.validation,
    };
  };

  const mergeEvidencePills = (existing: Evidence[] | undefined, incoming: Evidence[]): Evidence[] => {
    const byId: Record<string, Evidence> = {};
    const warnings: Array<{ evidenceId: string; field: string; oldValue: string; newValue: string }> = [];
    
    for (const e of existing || []) {
      byId[e.id] = e;
    }
    
    for (const e of incoming) {
      const prev = byId[e.id];
      if (prev) {
        if (prev.source !== e.source) {
          warnings.push({
            evidenceId: e.id,
            field: 'source',
            oldValue: prev.source,
            newValue: e.source,
          });
        }
        if (prev.type !== e.type) {
          warnings.push({
            evidenceId: e.id,
            field: 'type',
            oldValue: prev.type,
            newValue: e.type,
          });
        }
        if (prev.validation === 'verifiable' && e.validation !== 'verifiable') {
          warnings.push({
            evidenceId: e.id,
            field: 'validation',
            oldValue: prev.validation,
            newValue: e.validation,
          });
        }
        if (prev.confidence !== e.confidence) {
          warnings.push({
            evidenceId: e.id,
            field: 'confidence',
            oldValue: prev.confidence,
            newValue: e.confidence,
          });
        }

        const invariantChanged = prev.source !== e.source || prev.type !== e.type;
        byId[e.id] = invariantChanged
          ? {
              ...e,
              source: prev.source,
              type: prev.type,
              validation: 'mismatch',
            }
          : e;
        continue;
      }
      byId[e.id] = e;
    }
    
    if (warnings.length > 0) {
      console.warn('[mergeEvidencePills] Evidence field changes detected:', {
        requestId: activeRequestId,
        warnings,
      });
    }
    
    return Object.keys(byId).sort().map((k) => byId[k]);
  };

  const getErrorCode = async (res: Response): Promise<string | null> => {
    try {
      const bodyUnknown: unknown = await res.json();
      const parsed = ErrorResponseSchema.safeParse(bodyUnknown);
      return parsed.success ? parsed.data.code : null;
    } catch {
      return null;
    }
  };

  const stream = useChatSseStream({
    apiBaseUrl,
    tenantId,
    projectId,
    accessToken: accessToken || '',
    sseReconnect,
    sseTimeouts,
    createRequestId,
    onMessageDelta: ({ requestId, sessionId, delta }) => {
      console.debug('[onMessageDelta]', { requestId, sessionId, deltaLength: delta.length });
      const assistantMessageId = `sse-${requestId}`;
      setMessages(prev => prev.map(m => (
        m.id === assistantMessageId
          ? { ...m, content: (m.content || '') + delta }
          : m
      )));
    },
    onProgress: ({ requestId, sessionId, payload }) => {
      console.debug('[onProgress]', { requestId, sessionId, stage: payload.stage });
      const assistantMessageId = `sse-${requestId}`;
      setMessages(prev => prev.map(m => (
        m.id === assistantMessageId
          ? { ...m, content: (m.content || '') + payload.message }
          : m
      )));
    },
    onWarning: ({ requestId, sessionId, sequence, timestamp, tenantId, projectId, payload }) => {
      console.warn('[onWarning]', { requestId, sessionId, code: payload.code, message: payload.message });
      setActiveEvidenceViewModel((prev) => {
        const base =
          prev ||
          createEmptyEvidenceViewModel({
            requestId,
            tenantId,
            projectId,
            sessionId,
          });
        return mergeEvidenceViewModel({
          prev: base,
          incomingWarning: { code: payload.code, message: payload.message, details: payload.details ?? null },
          meta: { requestId, tenantId, projectId, sessionId, sequence, timestamp },
        });
      });
      setMessages((prev) => ([
        ...prev,
        {
          id: `warn-${Date.now()}`,
          role: 'assistant',
          content: payload.message,
          timestamp: Date.now(),
        },
      ]));
    },
    onFinal: ({ requestId, sessionId, sequence, timestamp, tenantId, projectId, payload }) => {
      console.debug('[onFinal]', { requestId, sessionId, status: payload.status });
      setActiveEvidenceViewModel((prev) => {
        const base =
          prev ||
          createEmptyEvidenceViewModel({
            requestId,
            tenantId,
            projectId,
            sessionId,
          });
        return mergeEvidenceViewModel({
          prev: base,
          incomingFinalStatus: payload.status,
          meta: { requestId, tenantId, projectId, sessionId, sequence, timestamp },
        });
      });
      setAttachments([]);
    },
    onEvidenceUpdate: ({ requestId, sessionId, sequence, timestamp, tenantId, projectId, payload }) => {
      console.debug('[onEvidenceUpdate]', { requestId, sessionId, mode: payload.mode, evidenceCount: payload.evidences?.length });
      if (!payload.evidences || payload.evidences.length === 0) return;

      setActiveEvidenceViewModel((prev) => {
        const base =
          prev ||
          createEmptyEvidenceViewModel({
            requestId,
            tenantId,
            projectId,
            sessionId,
          });
        return mergeEvidenceViewModel({
          prev: base,
          incomingEvidences: payload.evidences,
          meta: { requestId, tenantId, projectId, sessionId, sequence, timestamp },
        });
      });

      const uiEvidences = payload.evidences.map(toUiEvidence);
      const assistantMessageId = `sse-${requestId}`;
      setMessages((prev) => prev.map((m) => (
        m.id === assistantMessageId
          ? { ...m, evidence: mergeEvidencePills(m.evidence, uiEvidences) }
          : m
      )));
    },
    onError: ({ requestId, sessionId, sequence, timestamp, tenantId, projectId, error }) => {
      console.error('[onError]', { requestId, sessionId, code: error.code, message: error.message });
      setActiveEvidenceViewModel((prev) => {
        const base =
          prev ||
          createEmptyEvidenceViewModel({
            requestId,
            tenantId,
            projectId,
            sessionId,
          });
        return mergeEvidenceViewModel({
          prev: base,
          incomingError: error,
          meta: { requestId, tenantId, projectId, sessionId, sequence, timestamp },
        });
      });
      setMessages(prev => ([...prev, {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: String(error.message || 'Request failed'),
        timestamp: Date.now(),
      }]));

      if (error.retryable === false) {
        const lastMsg = (lastUserMessageRef.current || '').trim();
        setManualRetryMessage(lastMsg ? lastMsg : null);
      }
    },
  });

  useEffect(() => {
    // Reset chat when scenario changes
    setMessages([{
        id: 'init',
        role: 'assistant',
        content: `${t('chat.agentName')}\n${t(activeScenario.description)}`,
        timestamp: Date.now()
    }]);
    setInput(t(activeScenario.initialMessage, { lng: normalizedLanguage }));
    setActiveEvidenceId(null);
    setActiveEvidenceViewModel(null);
    try {
      const persisted = localStorage.getItem('gangqing.accessToken');
      setAccessToken(persisted && persisted.trim() ? persisted : null);
    } catch {
      setAccessToken(null);
    }
    setUserId('');
    setAttachments([]);

    const toLoginUser = () => {
      if (activeScenario.role === 'manager') return 'manager';
      if (activeScenario.role === 'scheduler') return 'scheduler';
      return 'maintenance';
    };

    const login = async () => {
      try {
        const username = toLoginUser();
        if (accessToken) {
          setUserId(username);
          return;
        }
        const requestId = createRequestId();
        const res = await fetch(`${apiBaseUrl}/api/v1/auth/login`, {
          method: 'POST',
          headers: {
            ...buildBaseHeaders(requestId),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ username, password: username }),
        });
        if (!res.ok) {
          const code = await getErrorCode(res);
          if (res.status === 401 || code === 'AUTH_ERROR') {
            throw new Error('AUTH_ERROR');
          }
          throw new Error(`LOGIN_FAILED_${res.status}`);
        }
        const dataUnknown: unknown = await res.json();
        const token =
          (typeof dataUnknown === 'object' && dataUnknown && 'accessToken' in dataUnknown)
            ? (dataUnknown as Record<string, unknown>).accessToken
            : null;
        if (typeof token !== 'string' || !token.trim()) {
          throw new Error('MISSING_TOKEN');
        }
        setAccessToken(token);
        setUserId(username);
        try {
          localStorage.setItem('gangqing.accessToken', token);
        } catch {
          // ignore
        }
      } catch (e) {
        const errMsg = String((e as { message?: unknown } | null)?.message || e);
        setMessages(prev => ([...prev, {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: errMsg === 'AUTH_ERROR' ? t('chat.authError') : t('chat.loginError'),
          timestamp: Date.now(),
        }]));
      }
    };

    void login();
  }, [activeScenario]);

  useEffect(() => {
    return () => {
      if (stream.isProcessing) {
        void stream.cancelActiveRequest();
      }
    };
  }, [stream]);

  const handlePickFile = () => {
    fileInputRef.current?.click();
  };

  const handleUploadFile = async (file: File) => {
    if (!accessToken) {
      throw new Error(t('chat.missingToken'));
    }

    const form = new FormData();
    form.append('file', file);

    const requestId = createRequestId();
    const res = await fetch(`${apiBaseUrl}/api/v1/upload`, {
      method: 'POST',
      headers: {
        ...buildBaseHeaders(requestId),
        'Authorization': `Bearer ${accessToken}`,
      },
      body: form,
    });

    if (!res.ok) {
      throw new Error(`Upload failed (${res.status})`);
    }

    const dataUnknown: unknown = await res.json();
    const url =
      (typeof dataUnknown === 'object' && dataUnknown && 'attachment_url' in dataUnknown)
        ? (dataUnknown as Record<string, unknown>).attachment_url
        : null;
    if (typeof url !== 'string' || !url.trim()) {
      throw new Error('UPLOAD_MISSING_ATTACHMENT_URL');
    }
    setAttachments(prev => [...prev, url]);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const createUserMessage = (content: string): Message => ({
    id: Date.now().toString(),
    role: 'user',
    content,
    timestamp: Date.now(),
  });

  const createAssistantMessage = (requestId: string): Message => ({
    id: `sse-${requestId}`,
    role: 'assistant',
    content: '',
    timestamp: Date.now(),
  });

  const createErrorMessage = (content: string): Message => ({
    id: `err-${Date.now()}`,
    role: 'assistant',
    content,
    timestamp: Date.now(),
  });

  const clearAccessToken = () => {
    try {
      localStorage.removeItem('gangqing.accessToken');
    } catch {
      // ignore
    }
    setAccessToken(null);
  };

  const getErrorContent = (errMsg: string): string => {
    if (errMsg === 'AUTH_ERROR') return t('chat.authError');
    if (errMsg === 'FORBIDDEN') return t('chat.forbidden');
    return t('chat.requestError');
  };

  const startStream = async (content: string) => {
    if (!content.trim()) return;

    const userMsg = createUserMessage(content);
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    lastUserMessageRef.current = content;
    setManualRetryMessage(null);

    if (!accessToken) {
      setMessages(prev => [...prev, createErrorMessage(t('chat.missingToken'))]);
      return;
    }

    try {
      const requestId = createRequestId();
      setActiveRequestId(requestId);
      setActiveEvidenceChain(null);
      setMessages(prev => [...prev, createAssistantMessage(requestId)]);

      const result = await stream.sendMessage(userMsg.content, requestId);
      if ('code' in result) {
        if (result.code === 'AUTH_ERROR') throw new Error('AUTH_ERROR');
        if (result.code === 'FORBIDDEN') throw new Error('FORBIDDEN');
        throw new Error('CHAT_FAILED_STREAM');
      }
    } catch (e) {
      const errMsg = String((e as { message?: unknown } | null)?.message || e);
      if (errMsg === 'AUTH_ERROR') clearAccessToken();
      setMessages(prev => [...prev, createErrorMessage(getErrorContent(errMsg))]);
      const lastMsg = (lastUserMessageRef.current || '').trim();
      setManualRetryMessage(lastMsg ? lastMsg : null);
    }
  };

  const handleSend = async () => {
    if (!input.trim()) return;
    await startStream(input);
  };

  const handleManualRetry = async () => {
    const msg = (manualRetryMessage || '').trim();
    if (!msg) return;
    await startStream(msg);
  };

  const handleCancel = async () => {
    await stream.cancelActiveRequest();
    setMessages((prev) => ([
      ...prev,
      {
        id: `cancel-${Date.now()}`,
        role: 'assistant',
        content: t('chat.cancelled'),
        timestamp: Date.now(),
      },
    ]));
  };

  return (
    <div className="flex flex-1 h-full overflow-hidden relative">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full bg-steel-900/50 relative">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {messages.map(msg => (
            <ChatMessage 
                key={msg.id} 
                message={msg} 
                onEvidenceClick={(ev) => { void handleEvidenceClick(ev); }} 
            />
          ))}
          {stream.isProcessing && (
             <div className="p-6">
                <div className="flex items-center gap-2 text-molten-500 text-sm animate-pulse">
                    <span className="w-2 h-2 bg-molten-500 rounded-full"></span>
                    {t('chat.thinking')}
                </div>
             </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 bg-steel-900 border-t border-steel-700">
          <div className="max-w-4xl mx-auto relative">
             {/* Suggestions / Quick Actions could go here */}
            <div className="flex items-end gap-2 bg-steel-800 rounded-xl border border-steel-700 p-2 focus-within:ring-2 focus-within:ring-molten-500/50 transition-all shadow-lg">
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept="image/*,audio/*"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    try {
                      await handleUploadFile(f);
                    } catch {
                      setMessages(prev => ([...prev, {
                        id: `err-${Date.now()}`,
                        role: 'assistant',
                        content: t('chat.requestError'),
                        timestamp: Date.now(),
                      }]));
                    } finally {
                      e.target.value = '';
                    }
                  }}
                />

                <button onClick={handlePickFile} className="p-3 text-slate-400 hover:text-white transition-colors">
                    <Paperclip size={20} />
                </button>
                <textarea 
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSend();
                        }
                    }}
                    placeholder={t('chat.inputPlaceholder')}
                    className="flex-1 bg-transparent border-none text-slate-200 placeholder-slate-500 focus:ring-0 resize-none py-3 max-h-32"
                    rows={1}
                />
                 <button className="p-3 text-slate-400 hover:text-white transition-colors">
                    <Mic size={20} />
                </button>
                <button 
                    onClick={handleSend}
                    disabled={!input.trim() || stream.isProcessing}
                    className="p-3 bg-molten-600 hover:bg-molten-500 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-molten-500/20"
                >
                    <Send size={18} />
                </button>
                {stream.isProcessing && (
                  <button
                    onClick={handleCancel}
                    className="p-3 bg-steel-700 hover:bg-steel-600 text-slate-200 rounded-lg transition-colors"
                  >
                    {t('chat.stop')}
                  </button>
                )}
            </div>
            {manualRetryMessage && !stream.isProcessing && (
              <div className="mt-3 flex justify-end">
                <button
                  onClick={handleManualRetry}
                  className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-steel-700 hover:bg-steel-600 text-slate-200 transition-colors"
                >
                  <RotateCcw size={16} />
                  {t('chat.retry')}
                </button>
              </div>
            )}
            <div className="text-center mt-2">
                 <p className="text-xs text-slate-500">{t('chat.disclaimer')}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel */}
      <ContextPanel
        selectedEvidenceId={activeEvidenceId}
        evidenceViewModel={activeEvidenceViewModel}
        evidenceChain={activeEvidenceChain}
        onClose={() => {
          setActiveEvidenceId(null);
          setActiveEvidenceChain(null);
          setActiveEvidenceViewModel(null);
        }}
      />
    </div>
  );
};

export default ChatInterface;