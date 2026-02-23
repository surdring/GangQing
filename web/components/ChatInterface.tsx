import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, Paperclip, ChevronDown, RotateCcw } from 'lucide-react';
import ChatMessage from './ChatMessage';
import ContextPanel from './ContextPanel';
import { Message, Evidence, Scenario } from '../types';
import { useTranslation } from 'react-i18next';


interface Props {
  activeScenario: Scenario;
}

const ChatInterface: React.FC<Props> = ({ activeScenario }) => {
  const { t, i18n } = useTranslation();
  const normalizedLanguage = (i18n.resolvedLanguage || i18n.language || 'zh').startsWith('en') ? 'en' : 'zh';
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [activeEvidence, setActiveEvidence] = useState<Evidence | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [userId, setUserId] = useState<string>('');
  const [attachments, setAttachments] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const apiBaseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
  const tenantId = (import.meta as any).env?.VITE_TENANT_ID || 't1';
  const projectId = (import.meta as any).env?.VITE_PROJECT_ID || 'p1';

  const createRequestId = () => {
    try {
      return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    } catch {
      return `${Date.now()}-${Math.random()}`;
    }
  };

  const buildBaseHeaders = (requestId: string) => ({
    'X-Tenant-Id': tenantId,
    'X-Project-Id': projectId,
    'X-Request-Id': requestId,
  });

  const getErrorCode = async (res: Response): Promise<string | null> => {
    try {
      const body = await res.json();
      const code = (body as any)?.code;
      return typeof code === 'string' ? code : null;
    } catch {
      return null;
    }
  };

  useEffect(() => {
    // Reset chat when scenario changes
    setMessages([{
        id: 'init',
        role: 'assistant',
        content: `${t('chat.agentName')}\n${t(activeScenario.description)}`,
        timestamp: Date.now()
    }]);
    setInput(t(activeScenario.initialMessage, { lng: normalizedLanguage }));
    setActiveEvidence(null);
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
        const data = await res.json();
        const token = (data as any)?.accessToken;
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
        const errMsg = String((e as any)?.message || e);
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

    const data = await res.json();
    const url = data.attachment_url as string;
    setAttachments(prev => [...prev, url]);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsProcessing(true);

    try {
      if (!accessToken) {
        throw new Error(t('chat.missingToken'));
      }

      const requestId = createRequestId();
      const res = await fetch(`${apiBaseUrl}/api/v1/chat`, {
        method: 'POST',
        headers: {
          ...buildBaseHeaders(requestId),
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          session_id: `web-${activeScenario.id}`,
          message: userMsg.content,
          user_id: userId || 'web-user',
          user_role: activeScenario.role,
          attachments,
          language: normalizedLanguage,
        }),
      });

      if (!res.ok) {
        const code = await getErrorCode(res);
        if (res.status === 401 || code === 'AUTH_ERROR') {
          throw new Error('AUTH_ERROR');
        }
        if (res.status === 403 || code === 'FORBIDDEN') {
          throw new Error('FORBIDDEN');
        }
        throw new Error(`CHAT_FAILED_${res.status}`);
      }

      const data = await res.json();

      const responseMsg: Message = {
        id: data.message_id || (Date.now() + 1).toString(),
        role: 'assistant',
        timestamp: Date.now(),
        content: data.content || '',
        evidence: data.evidence_chain || [],
        chartData: data.chart_data || undefined,
        chartType: data.chart_type || undefined,
        actions: data.actions || undefined,
      };

      setMessages(prev => [...prev, responseMsg]);
      setAttachments([]);
    } catch (e) {
      const errMsg = String((e as any)?.message || e);
      const content =
        errMsg === 'AUTH_ERROR'
          ? t('chat.authError')
          : errMsg === 'FORBIDDEN'
            ? t('chat.forbidden')
            : t('chat.requestError');

      if (errMsg === 'AUTH_ERROR') {
        try {
          localStorage.removeItem('gangqing.accessToken');
        } catch {
          // ignore
        }
        setAccessToken(null);
      }
      setMessages(prev => ([...prev, {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content,
        timestamp: Date.now(),
      }]));
    } finally {
      setIsProcessing(false);
    }
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
                onEvidenceClick={(ev) => setActiveEvidence(ev)} 
            />
          ))}
          {isProcessing && (
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
                    disabled={!input.trim() || isProcessing}
                    className="p-3 bg-molten-600 hover:bg-molten-500 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-molten-500/20"
                >
                    <Send size={18} />
                </button>
            </div>
            <div className="text-center mt-2">
                 <p className="text-xs text-slate-500">{t('chat.disclaimer')}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel */}
      <ContextPanel evidence={activeEvidence} onClose={() => setActiveEvidence(null)} />
    </div>
  );
};

export default ChatInterface;