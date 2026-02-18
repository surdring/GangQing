import React from 'react';
import { X, ExternalLink, ShieldCheck, AlertTriangle, ArrowRight } from 'lucide-react';
import { Evidence } from '../types';
import { useTranslation } from 'react-i18next';

interface Props {
  evidence: Evidence | null;
  onClose: () => void;
}

const ContextPanel: React.FC<Props> = ({ evidence, onClose }) => {
  const { t } = useTranslation();
  const confidenceLabel = (v: string) => {
    if (v === 'High' || v === 'Medium' || v === 'Low') {
      return t(`contextPanel.confidenceLevels.${v}`);
    }
    return v;
  };
  if (!evidence) {
    return (
      <div className="w-80 border-l border-steel-700 bg-steel-800/20 backdrop-blur-sm p-6 hidden xl:flex flex-col items-center justify-center text-center">
        <ShieldCheck size={48} className="text-steel-700 mb-4" />
        <h3 className="text-slate-400 font-medium">{t('contextPanel.evidenceChain')}</h3>
        <p className="text-sm text-slate-500 mt-2">
          {t('contextPanel.evidenceChainHint')}
        </p>
      </div>
    );
  }

  return (
    <div className="w-80 border-l border-steel-700 bg-steel-900 flex flex-col h-full shadow-2xl animate-in slide-in-from-right duration-300 absolute right-0 top-0 bottom-0 z-20 xl:relative xl:z-0">
      {/* Header */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-steel-700 bg-steel-800">
        <div className="flex items-center gap-2 text-slate-200 font-medium">
            <ShieldCheck size={18} className="text-molten-500" />
            <span>{t('contextPanel.verification')}</span>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
          <X size={20} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        
        {/* Source Meta */}
        <div className="space-y-1">
            <div className="text-xs font-mono uppercase text-slate-500">{t('contextPanel.dataSource')}</div>
            <div className="text-lg font-semibold text-white">{evidence.source}</div>
            <div className="flex items-center gap-2 text-sm text-slate-400">
                <span className={`w-2 h-2 rounded-full ${evidence.confidence === 'High' ? 'bg-safety-500' : 'bg-alert-500'}`}></span>
                {t('contextPanel.confidence')}: {confidenceLabel(evidence.confidence)}
            </div>
        </div>

        {/* Data Points Comparison */}
        {evidence.dataPoints && (
            <div className="bg-steel-800 rounded-lg p-4 border border-steel-700">
                <div className="text-xs font-mono uppercase text-slate-500 mb-3">{t('contextPanel.keyMetrics')}</div>
                {evidence.dataPoints.map((dp, i) => (
                    <div key={i} className="flex justify-between items-center mb-2 last:mb-0">
                        <span className="text-sm text-slate-300">{dp.label}</span>
                        <div className="text-right">
                            <div className="font-mono text-white">{dp.value}</div>
                            {dp.change && (
                                <div className={`text-xs ${dp.change > 0 ? 'text-alert-500' : 'text-safety-500'}`}>
                                    {dp.change > 0 ? '+' : ''}{dp.change}%
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        )}

        {/* Raw Details */}
        <div>
            <div className="text-xs font-mono uppercase text-slate-500 mb-2">{t('contextPanel.rawLogExtract')}</div>
            <div className="bg-black/50 p-3 rounded border border-steel-700 font-mono text-xs text-tech-500 leading-relaxed break-all">
                {`> FETCH FROM ${evidence.type}_DB\n> TIMESTAMP: ${evidence.timestamp}\n> QUERY_ID: ${evidence.id}\n\n${evidence.details}`}
            </div>
        </div>

        {/* Audit Trail */}
        <div className="p-4 bg-molten-500/5 border border-molten-500/20 rounded-lg">
            <div className="flex items-start gap-3">
                <AlertTriangle size={16} className="text-molten-500 mt-0.5" />
                <div>
                    <h4 className="text-sm font-medium text-molten-500">{t('contextPanel.auditTrail')}</h4>
                    <p className="text-xs text-slate-400 mt-1">
                        {t('contextPanel.auditTrailHint')}
                    </p>
                </div>
            </div>
        </div>

        <button className="w-full py-2 flex items-center justify-center gap-2 text-sm font-medium text-slate-300 border border-steel-600 rounded hover:bg-steel-800 transition-colors">
            {t('contextPanel.viewOriginalReport')} <ExternalLink size={14} />
        </button>

      </div>
    </div>
  );
};

export default ContextPanel;