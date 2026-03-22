import React, { useState, useMemo } from 'react';
import {
  X,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Database,
  GitBranch,
  Activity,
  EyeOff,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { EvidenceChain } from '../schemas/evidenceChain';
import type { EvidenceViewModel } from '../schemas/evidenceViewModel';
import { EvidenceSchema, type Evidence } from '../schemas/evidence';

interface Props {
  selectedEvidenceId: string | null;
  evidenceViewModel: EvidenceViewModel | null;
  evidenceChain: EvidenceChain | null;
  onClose: () => void;
}

const ContextPanel: React.FC<Props> = ({
  selectedEvidenceId,
  evidenceViewModel,
  evidenceChain,
  onClose,
}) => {
  const { t } = useTranslation();
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

  const toggleSection = (section: string) => {
    // Prevent expansion if frozen (optional UX choice: allow viewing but not interaction)
    // We allow viewing details even when frozen, just don't allow updates
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };
  const confidenceLabel = (v: string) => {
    if (v === 'High' || v === 'Medium' || v === 'Low') {
      return t(`contextPanel.confidenceLevels.${v}`);
    }
    return v;
  };

  const renderWarningList = () => {
    const warnings = evidenceViewModel?.warnings || [];
    if (warnings.length === 0) return null;
    return (
      <div className="bg-molten-500/5 border border-molten-500/20 rounded-lg p-4">
        <div className="text-xs font-mono uppercase text-slate-500 mb-3">
          {t('contextPanel.warningsTitle')}
        </div>
        <div className="space-y-3">
          {warnings.slice(-5).map((w, idx) => (
            <div key={`${w.requestId}:${w.sequence}:${idx}`} className="text-xs text-slate-300">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-slate-200 break-all">{w.code}</span>
                <span className="text-slate-500 font-mono">seq={w.sequence}</span>
              </div>
              <div className="text-slate-400 mt-1 break-words">{w.message}</div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderErrorBlock = () => {
    const err = evidenceViewModel?.error;
    if (!err) return null;

    return (
      <div className="bg-alert-500/10 border border-alert-500/30 rounded-lg p-4">
        <div className="text-xs font-mono uppercase text-slate-500 mb-2">
          {t('contextPanel.errorTitle')}
        </div>
        <div className="text-xs text-alert-400 font-mono break-all">{err.code}</div>
        <div className="text-sm text-slate-200 mt-1 break-words">{err.message}</div>
        <div className="text-xs text-slate-500 font-mono mt-2 break-all">requestId={err.requestId}</div>
      </div>
    );
  };

  const renderStreamStatus = () => {
    if (!evidenceViewModel) return null;
    if (evidenceViewModel.status === 'empty') return null;
    const statusLabel = evidenceViewModel.isFrozen
      ? `stable(${evidenceViewModel.finalStatus || 'unknown'})`
      : 'streaming';
    return (
      <div className="text-xs text-slate-500 font-mono">
        {`status=${statusLabel}${evidenceViewModel.lastSequence != null ? ` seq=${evidenceViewModel.lastSequence}` : ''}`}
      </div>
    );
  };

  // Get full Evidence from EvidenceViewModel by selectedEvidenceId
  const getFullEvidence = (evidenceId: string): Evidence | null => {
    if (!evidenceViewModel) return null;
    return evidenceViewModel.evidencesById[evidenceId] || null;
  };

  // Sanitize sourceLocator to prevent leaking sensitive credentials
  const sanitizeSourceLocator = (locator: Record<string, unknown>): Record<string, unknown> => {
    const sensitiveKeys = ['token', 'apiKey', 'password', 'secret', 'credential', 'auth'];
    const sanitized: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(locator)) {
      const lowerKey = key.toLowerCase();
      const isSensitive = sensitiveKeys.some((sk) => lowerKey.includes(sk.toLowerCase()));
      if (isSensitive) {
        sanitized[key] = '[REDACTED]';
      } else {
        sanitized[key] = value;
      }
    }
    return sanitized;
  };

  const isExpanded = (section: string) => expandedSections.has(section);

  const renderTraceabilitySection = () => {
    if (!selectedEvidenceId) return null;
    const fullEvidence = getFullEvidence(selectedEvidenceId);
    if (!fullEvidence) {
      return (
        <div className="bg-steel-800 rounded-lg p-4 border border-steel-700">
          <div className="text-xs font-mono uppercase text-slate-500 mb-2">{t('contextPanel.traceability')}</div>
          <div className="text-xs text-slate-400">{t('contextPanel.noPermissionToView')}</div>
        </div>
      );
    }

    const sectionKey = 'traceability';
    const expanded = isExpanded(sectionKey);

    return (
      <div className="bg-steel-800 rounded-lg border border-steel-700 overflow-hidden">
        <button
          onClick={() => toggleSection(sectionKey)}
          className="w-full flex items-center justify-between p-4 hover:bg-steel-700/50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Database size={14} className="text-slate-400" />
            <span className="text-xs font-mono uppercase text-slate-500">{t('contextPanel.traceability')}</span>
          </div>
          {expanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
        </button>
        {expanded && (
          <div className="px-4 pb-4 space-y-4 border-t border-steel-700 pt-4">
            {/* Evidence ID */}
            <div className="space-y-1">
              <div className="text-xs text-slate-500 font-mono">{t('contextPanel.fieldNames.evidenceId')}</div>
              <div className="text-xs text-slate-300 font-mono break-all">{fullEvidence.evidenceId}</div>
            </div>

            {/* Source System */}
            <div className="space-y-1">
              <div className="text-xs text-slate-500 font-mono">{t('contextPanel.fieldNames.sourceSystem')}</div>
              <div className="text-xs text-slate-300 font-mono">{fullEvidence.sourceSystem}</div>
            </div>

            {/* Source Locator - Sanitized */}
            <div className="space-y-1">
              <div className="text-xs text-slate-500 font-mono flex items-center gap-1">
                {t('contextPanel.sourceLocator')}
                <span className="text-slate-600">({Object.keys(sanitizeSourceLocator(fullEvidence.sourceLocator)).length} fields)</span>
              </div>
              <div className="bg-black/30 p-2 rounded border border-steel-700">
                <pre className="text-xs text-slate-400 font-mono break-all whitespace-pre-wrap">
                  {JSON.stringify(sanitizeSourceLocator(fullEvidence.sourceLocator), null, 2)}
                </pre>
              </div>
            </div>

            {/* Time Range */}
            <div className="space-y-1">
              <div className="text-xs text-slate-500 font-mono flex items-center gap-1">
                <Clock size={12} />
                {t('contextPanel.timeRange')}
              </div>
              <div className="text-xs text-slate-300 font-mono space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-slate-500">{t('contextPanel.fieldNames.startTime')}:</span>
                  <span>{fullEvidence.timeRange.start}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-slate-500">{t('contextPanel.fieldNames.endTime')}:</span>
                  <span>{fullEvidence.timeRange.end}</span>
                </div>
              </div>
            </div>

            {/* Tool Call ID */}
            {fullEvidence.toolCallId && (
              <div className="space-y-1">
                <div className="text-xs text-slate-500 font-mono">{t('contextPanel.toolCallId')}</div>
                <div className="text-xs text-slate-300 font-mono break-all">{fullEvidence.toolCallId}</div>
              </div>
            )}

            {/* Lineage Version */}
            {fullEvidence.lineageVersion && (
              <div className="space-y-1">
                <div className="text-xs text-slate-500 font-mono flex items-center gap-1">
                  <GitBranch size={12} />
                  {t('contextPanel.lineageVersion')}
                </div>
                <div className="text-xs text-slate-300 font-mono break-all">{fullEvidence.lineageVersion}</div>
              </div>
            )}

            {/* Data Quality Score */}
            {fullEvidence.dataQualityScore != null && (
              <div className="space-y-1">
                <div className="text-xs text-slate-500 font-mono flex items-center gap-1">
                  <Activity size={12} />
                  {t('contextPanel.dataQualityScore')}
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-steel-700 h-2 rounded-full overflow-hidden">
                    <div
                      className="bg-tech-500 h-full rounded-full"
                      style={{ width: `${Math.round(fullEvidence.dataQualityScore * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-300 font-mono">
                    {(fullEvidence.dataQualityScore * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            )}

            {/* Redactions */}
            {fullEvidence.redactions && Object.keys(fullEvidence.redactions).length > 0 && (
              <div className="space-y-2">
                <div className="text-xs text-slate-500 font-mono flex items-center gap-1">
                  <EyeOff size={12} />
                  {t('contextPanel.redactions')}
                </div>
                <div className="text-xs text-slate-500">{t('contextPanel.redactionsHint')}</div>
                <div className="bg-black/30 p-2 rounded border border-steel-700">
                  <pre className="text-xs text-slate-400 font-mono break-all whitespace-pre-wrap">
                    {JSON.stringify(fullEvidence.redactions, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const getValidationInfo = (validation: string) => {
    switch (validation) {
      case 'not_verifiable':
        return {
          icon: <HelpCircle size={14} className="text-slate-400" />,
          label: t('contextPanel.validation.notVerifiable'),
          color: 'text-slate-400',
          bgColor: 'bg-slate-500/10',
          borderColor: 'border-slate-500/30',
        };
      case 'out_of_bounds':
        return {
          icon: <AlertTriangle size={14} className="text-alert-400" />,
          label: t('contextPanel.validation.outOfBounds'),
          color: 'text-alert-400',
          bgColor: 'bg-alert-400/10',
          borderColor: 'border-alert-400/30',
        };
      case 'mismatch':
        return {
          icon: <AlertCircle size={14} className="text-alert-500" />,
          label: t('contextPanel.validation.mismatch'),
          color: 'text-alert-500',
          bgColor: 'bg-alert-500/10',
          borderColor: 'border-alert-500/30',
        };
      default:
        return {
          icon: <ShieldCheck size={14} className="text-tech-500" />,
          label: t('contextPanel.validation.verifiable'),
          color: 'text-tech-500',
          bgColor: 'bg-tech-500/10',
          borderColor: 'border-tech-500/30',
        };
    }
  };

  // Get selected evidence from view model with validation
  const selectedEvidence: Evidence | null = useMemo(() => {
    if (!selectedEvidenceId || !evidenceViewModel) return null;
    const ev = evidenceViewModel.evidencesById[selectedEvidenceId];
    if (!ev) return null;

    // Validate with Zod schema
    const parsed = EvidenceSchema.safeParse(ev);
    if (!parsed.success) {
      console.warn('[ContextPanel] Evidence schema validation failed:', {
        evidenceId: selectedEvidenceId,
        errors: parsed.error.errors,
      });
      return null;
    }

    return parsed.data;
  }, [selectedEvidenceId, evidenceViewModel]);

  if (!selectedEvidence) {
    return (
      <div className="w-80 border-l border-steel-700 bg-steel-800/20 backdrop-blur-sm p-6 hidden xl:flex flex-col items-center justify-center text-center">
        <ShieldCheck size={48} className="text-steel-700 mb-4" />
        <h3 className="text-slate-400 font-medium">{t('contextPanel.evidenceChain')}</h3>
        <p className="text-sm text-slate-500 mt-2">
          {t('contextPanel.evidenceChainHint')}
        </p>
        {evidenceViewModel && (
          <div className="mt-4 w-full text-left space-y-3">
            {renderStreamStatus()}
            {renderErrorBlock()}
            {renderWarningList()}
          </div>
        )}
      </div>
    );
  }

  const validationInfo = getValidationInfo(selectedEvidence.validation);

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
        {renderStreamStatus()}
        {renderErrorBlock()}
        {renderWarningList()}
        
        {/* Source Meta */}
        <div className="space-y-1">
            <div className="text-xs font-mono uppercase text-slate-500">{t('contextPanel.dataSource')}</div>
            <div className="text-lg font-semibold text-white">{selectedEvidence.sourceSystem}</div>
            <div className="flex items-center gap-2 text-sm text-slate-400">
                <span className={`w-2 h-2 rounded-full ${selectedEvidence.confidence === 'High' ? 'bg-safety-500' : 'bg-alert-500'}`}></span>
                {t('contextPanel.confidence')}: {confidenceLabel(selectedEvidence.confidence)}
            </div>
        </div>

        {/* Validation Status */}
        <div className={`p-3 rounded-lg border ${validationInfo.bgColor} ${validationInfo.borderColor}`}>
          <div className="flex items-center gap-2">
            {validationInfo.icon}
            <span className={`text-sm font-medium ${validationInfo.color}`}>{validationInfo.label}</span>
          </div>
          {selectedEvidence.validation !== 'verifiable' && (
            <p className="text-xs text-slate-400 mt-2">
              {t(`contextPanel.validation.${selectedEvidence.validation}Hint`)}
            </p>
          )}
        </div>

        {/* Data Points Comparison - Removed: dataPoints not in Zod schema */}

        {/* Raw Details */}
        <div>
            <div className="text-xs font-mono uppercase text-slate-500 mb-2">{t('contextPanel.rawLogExtract')}</div>
            <div className="bg-black/50 p-3 rounded border border-steel-700 font-mono text-xs text-tech-500 leading-relaxed break-all">
                {selectedEvidence.validation === 'verifiable'
                  ? `evidenceId=${selectedEvidence.evidenceId}\nsourceSystem=${selectedEvidence.sourceSystem}\ntimeRange=${selectedEvidence.timeRange.start} to ${selectedEvidence.timeRange.end}\n\n${t('contextPanel.rawDataPlaceholder')}`
                  : `evidenceId=${selectedEvidence.evidenceId}\nsourceSystem=${selectedEvidence.sourceSystem}\n\n${t('contextPanel.unverifiableEvidenceMarker')}\n${t('contextPanel.rawDataPlaceholder')}`}
            </div>
        </div>

        {/* Traceability Expand Section */}
        {renderTraceabilitySection()}

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

        {evidenceChain?.toolTraces && evidenceChain.toolTraces.length > 0 && (
          <div className="bg-steel-800 rounded-lg p-4 border border-steel-700">
            <div className="text-xs font-mono uppercase text-slate-500 mb-3">{t('contextPanel.toolTraces')}</div>
            <div className="space-y-3">
              {evidenceChain.toolTraces.map((tr) => (
                <div key={tr.toolCallId} className="text-xs text-slate-300">
                  <div className="flex items-center justify-between">
                    <span className="font-mono">{tr.toolName}</span>
                    <span className={tr.status === 'success' ? 'text-safety-500' : 'text-alert-500'}>
                      {tr.status}
                    </span>
                  </div>
                  <div className="text-slate-500 font-mono mt-1 break-all">
                    {`toolCallId=${tr.toolCallId}${tr.durationMs != null ? ` durationMs=${tr.durationMs}` : ''}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {evidenceChain?.citations && evidenceChain.citations.length > 0 && (
          <div className="bg-steel-800 rounded-lg p-4 border border-steel-700">
            <div className="text-xs font-mono uppercase text-slate-500 mb-3">{t('contextPanel.citations')}</div>
            <div className="space-y-2">
              {evidenceChain.citations.map((c) => (
                <div key={c.citationId} className="text-xs text-slate-300 break-all">
                  <div className="font-mono text-slate-200">{c.sourceSystem}</div>
                  <div className="text-slate-500 font-mono">{`evidenceId=${c.evidenceId}`}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {evidenceChain?.lineages && evidenceChain.lineages.length > 0 && (
          <div className="bg-steel-800 rounded-lg p-4 border border-steel-700">
            <div className="text-xs font-mono uppercase text-slate-500 mb-3">{t('contextPanel.lineage')}</div>
            <div className="space-y-2">
              {evidenceChain.lineages.map((l, idx) => (
                <div key={`${l.metricName}:${l.lineageVersion}:${idx}`} className="text-xs text-slate-300 break-all">
                  <div className="font-mono text-slate-200">{l.metricName}</div>
                  <div className="text-slate-500 font-mono">{`lineageVersion=${l.lineageVersion}`}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <button className="w-full py-2 flex items-center justify-center gap-2 text-sm font-medium text-slate-300 border border-steel-600 rounded hover:bg-steel-800 transition-colors">
            {t('contextPanel.viewOriginalReport')} <ExternalLink size={14} />
        </button>

      </div>
    </div>
  );
};

export default ContextPanel;