import React from 'react';
import { Database, Activity, Server, FileText, AlertTriangle, AlertCircle, HelpCircle } from 'lucide-react';
import { Evidence } from '../types';

interface TrustPillProps {
  evidence: Evidence;
  onClick: (evidence: Evidence) => void;
}

const TrustPill: React.FC<TrustPillProps> = ({ evidence, onClick }) => {
  const getIcon = () => {
    switch (evidence.type) {
      case 'SAP': return <Database size={12} />;
      case 'IoT': return <Activity size={12} />;
      case 'DCS': return <Server size={12} />;
      default: return <FileText size={12} />;
    }
  };

  const getValidationIcon = () => {
    switch (evidence.validation) {
      case 'not_verifiable': return <HelpCircle size={12} className="text-slate-400" />;
      case 'out_of_bounds': return <AlertTriangle size={12} className="text-alert-400" />;
      case 'mismatch': return <AlertCircle size={12} className="text-alert-500" />;
      default: return null;
    }
  };

  const getConfidenceColor = () => {
    if (evidence.validation !== 'verifiable') {
      switch (evidence.validation) {
        case 'not_verifiable':
          return 'border-slate-500/50 text-slate-400 bg-slate-500/10 hover:bg-slate-500/20';
        case 'out_of_bounds':
          return 'border-alert-400/50 text-alert-400 bg-alert-400/10 hover:bg-alert-400/20';
        case 'mismatch':
          return 'border-alert-500/50 text-alert-500 bg-alert-500/10 hover:bg-alert-500/20';
      }
    }
    switch (evidence.confidence) {
      case 'High': return 'border-tech-500/50 text-tech-500 bg-tech-500/10 hover:bg-tech-500/20';
      case 'Medium': return 'border-molten-500/50 text-molten-500 bg-molten-500/10 hover:bg-molten-500/20';
      case 'Low': return 'border-alert-500/50 text-alert-500 bg-alert-500/10 hover:bg-alert-500/20';
    }
  };

  const getValidationBadge = () => {
    if (evidence.validation === 'verifiable') return null;
    const labels: Record<string, string> = {
      not_verifiable: 'N/V',
      out_of_bounds: 'O/B',
      mismatch: 'MIS',
    };
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-black/20">
        {labels[evidence.validation]}
      </span>
    );
  };

  return (
    <button
      onClick={() => onClick(evidence)}
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-mono transition-all duration-200 cursor-pointer ${getConfidenceColor()} mb-2 mr-2`}
    >
      {getIcon()}
      <span>{evidence.source}</span>
      <span className="opacity-50">|</span>
      <span>{evidence.timestamp}</span>
      {getValidationIcon()}
      {getValidationBadge()}
    </button>
  );
};

export default TrustPill;