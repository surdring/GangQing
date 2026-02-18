import React from 'react';
import { Database, Activity, Server, FileText } from 'lucide-react';
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

  const getConfidenceColor = () => {
    switch (evidence.confidence) {
      case 'High': return 'border-tech-500/50 text-tech-500 bg-tech-500/10 hover:bg-tech-500/20';
      case 'Medium': return 'border-molten-500/50 text-molten-500 bg-molten-500/10 hover:bg-molten-500/20';
      case 'Low': return 'border-alert-500/50 text-alert-500 bg-alert-500/10 hover:bg-alert-500/20';
    }
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
    </button>
  );
};

export default TrustPill;