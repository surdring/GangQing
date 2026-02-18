import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, ReferenceLine } from 'recharts';
import { ChartDataPoint } from '../../types';
import { useTranslation } from 'react-i18next';

interface Props {
  data: ChartDataPoint[];
}

const CostWaterfall: React.FC<Props> = ({ data }) => {
  const { t } = useTranslation();

  const translateCategory = (name: string) => {
    const map: Record<string, string> = {
      'Base Cost': t('charts.categories.baseCost'),
      'Iron Ore': t('charts.categories.ironOre'),
      'Coke': t('charts.categories.coke'),
      'Flux': t('charts.categories.flux'),
      'Energy': t('charts.categories.energy'),
      'Total': t('charts.categories.total'),
      '基础成本': t('charts.categories.baseCost'),
      '铁矿石': t('charts.categories.ironOre'),
      '焦炭': t('charts.categories.coke'),
      '熔剂': t('charts.categories.flux'),
      '能耗': t('charts.categories.energy'),
      '合计': t('charts.categories.total'),
    };
    return map[name] || name;
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || payload.length === 0) return null;
    const p = payload[0];
    const label = translateCategory(String(p?.payload?.name ?? ''));
    const value = p?.value;
    return (
      <div className="bg-steel-900 border border-steel-700 rounded px-3 py-2 text-slate-200">
        <div className="text-sm font-semibold">{label}</div>
        <div className="text-xs text-slate-400 mt-1">
          {t('charts.valueLabel')}: <span className="font-mono text-slate-100">{value}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="h-64 w-full bg-steel-800/50 rounded-lg p-4 border border-steel-700">
      <h3 className="text-sm text-slate-400 mb-2 font-mono uppercase tracking-wider">{t('charts.costBreakdownTitle')}</h3>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
          <XAxis
            dataKey="name"
            stroke="#94a3b8"
            fontSize={12}
            tickLine={false}
            tickFormatter={(v) => translateCategory(String(v))}
          />
          <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} unit="¥" />
          <Tooltip cursor={{ fill: '#334155', opacity: 0.2 }} content={<CustomTooltip />} />
          <Bar dataKey="value">
            {data.map((entry, index) => {
              let color = '#3B82F6'; // Default Blue
              if (entry.type === 'increase') color = '#EF4444'; // Red for cost increase
              if (entry.type === 'decrease') color = '#22C55E'; // Green for savings
              if (entry.type === 'total') color = '#64748B'; // Slate for totals
              if (entry.name === 'Coke' || entry.name === '焦炭') color = '#F97316'; // Highlight the culprit (Molten Orange)
              
              return <Cell key={`cell-${index}`} fill={color} />;
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default CostWaterfall;