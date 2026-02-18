import React from 'react';
import { Bot, User, CheckCircle2, RotateCcw } from 'lucide-react';
import { Message, Evidence } from '../types';
import TrustPill from './TrustPill';
import CostWaterfall from './charts/CostWaterfall';
import AudioSpectrum from './charts/AudioSpectrum';
import { useTranslation } from 'react-i18next';

interface Props {
  message: Message;
  onEvidenceClick: (evidence: Evidence) => void;
}

const ChatMessage: React.FC<Props> = ({ message, onEvidenceClick }) => {
  const { t } = useTranslation();
  const isAi = message.role === 'assistant';

  return (
    <div className={`flex gap-4 p-6 ${isAi ? 'bg-steel-800/30' : 'bg-transparent'}`}>
      <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
        isAi ? 'bg-molten-500 text-white shadow-lg shadow-molten-500/20' : 'bg-slate-700 text-slate-300'
      }`}>
        {isAi ? <Bot size={20} /> : <User size={20} />}
      </div>
      
      <div className="flex-1 space-y-4">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-slate-200">{isAi ? t('chat.agentName') : t('chat.you')}</span>
          <span className="text-xs text-slate-500">{new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </div>

        {message.isThinking ? (
           <div className="flex items-center gap-2 text-molten-500 text-sm animate-pulse">
             <span className="w-2 h-2 bg-molten-500 rounded-full"></span>
             {t('chat.thinking')}
           </div>
        ) : (
          <>
            <div className="text-slate-300 leading-relaxed whitespace-pre-line">
              {message.content}
            </div>

            {/* Visualizations */}
            {message.chartData && message.chartType === 'waterfall' && (
              <div className="my-4 max-w-2xl">
                <CostWaterfall data={message.chartData} />
              </div>
            )}
             {message.chartData && message.chartType === 'spectrum' && (
              <div className="my-4 max-w-2xl">
                <AudioSpectrum data={message.chartData} />
              </div>
            )}

            {/* Evidence Pills */}
            {message.evidence && message.evidence.length > 0 && (
              <div className="flex flex-wrap items-center mt-2">
                 <span className="text-xs text-slate-500 mr-2 font-mono uppercase">{t('contextPanel.sources')}:</span>
                {message.evidence.map(ev => (
                  <TrustPill key={ev.id} evidence={ev} onClick={onEvidenceClick} />
                ))}
              </div>
            )}

            {/* Interactive Actions */}
            {message.actions && (
              <div className="flex gap-3 mt-4">
                {message.actions.map((action, idx) => (
                  <button 
                    key={idx}
                    className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                      action.style === 'primary' 
                        ? 'bg-molten-600 hover:bg-molten-500 text-white' 
                        : action.style === 'danger'
                        ? 'bg-alert-500/10 text-alert-500 border border-alert-500/50 hover:bg-alert-500/20'
                        : 'bg-steel-700 hover:bg-steel-600 text-slate-200'
                    }`}
                  >
                     {action.style === 'primary' && <CheckCircle2 size={16} />}
                     {action.style === 'danger' && <RotateCcw size={16} />}
                     {action.label}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ChatMessage;