import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { ChartDataPoint } from '../../types';
import { useTranslation } from 'react-i18next';

interface Props {
  data: ChartDataPoint[];
}

const AudioSpectrum: React.FC<Props> = ({ data }) => {
  const { t } = useTranslation();
  return (
    <div className="h-64 w-full bg-steel-800/50 rounded-lg p-4 border border-steel-700 relative overflow-hidden">
       {/* Alert Overlay */}
       <div className="absolute top-4 right-4 z-10 flex items-center gap-2 bg-alert-500/20 text-alert-500 px-3 py-1 rounded border border-alert-500/50 animate-pulse-slow">
         <span className="w-2 h-2 rounded-full bg-alert-500"></span>
         <span className="text-xs font-bold font-mono">{t('charts.anomalyDetected', { freq: '1200Hz' })}</span>
       </div>

      <h3 className="text-sm text-slate-400 mb-2 font-mono uppercase tracking-wider">{t('charts.vibrationSpectrumTitle')}</h3>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="colorVal" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#F97316" stopOpacity={0.8}/>
              <stop offset="95%" stopColor="#F97316" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
          <XAxis dataKey="name" stroke="#94a3b8" fontSize={10} tickLine={false} interval={4} />
          <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} hide />
          <Tooltip 
             contentStyle={{ backgroundColor: '#0F172A', borderColor: '#334155', color: '#E2E8F0' }}
          />
          <Area type="monotone" dataKey="value" stroke="#F97316" fillOpacity={1} fill="url(#colorVal)" />
          <ReferenceLine x="1150Hz" stroke="#EF4444" strokeDasharray="3 3" />
          <ReferenceLine x="1200Hz" stroke="#EF4444" strokeDasharray="3 3" />
          <ReferenceLine x="1250Hz" stroke="#EF4444" strokeDasharray="3 3" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

export default AudioSpectrum;