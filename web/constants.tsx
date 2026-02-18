import { ChartDataPoint, Evidence, Message, UserRole, Scenario } from './types';
import React from 'react';
import { Factory, Wrench, BarChart3, AlertTriangle } from 'lucide-react';

export const SCENARIOS: Scenario[] = [
  {
    id: 'cost-analysis',
    name: 'scenarios.costAnalysis',
    description: 'scenarios.costAnalysisDesc',
    role: UserRole.MANAGER,
    initialMessage: 'scenarios.costAnalysisInit'
  },
  {
    id: 'maintenance',
    name: 'scenarios.diagnostics',
    description: 'scenarios.diagnosticsDesc',
    role: UserRole.MAINTENANCE,
    initialMessage: 'scenarios.diagnosticsInit'
  },
  {
    id: 'simulation',
    name: 'scenarios.simulation',
    description: 'scenarios.simulationDesc',
    role: UserRole.SCHEDULER,
    initialMessage: 'scenarios.simulationInit'
  }
];

export const MOCK_WATERFALL_DATA: ChartDataPoint[] = [
  { name: 'Base Cost', value: 2400, type: 'total' },
  { name: 'Iron Ore', value: 120, type: 'increase' },
  { name: 'Coke', value: 350, type: 'increase' },
  { name: 'Flux', value: 30, type: 'increase' },
  { name: 'Energy', value: -50, type: 'decrease' },
  { name: 'Total', value: 2850, type: 'total' },
];

export const MOCK_SPECTRUM_DATA: ChartDataPoint[] = Array.from({ length: 40 }, (_, i) => ({
  name: `${i * 50}Hz`,
  value: i === 24 ? 95 : 20 + Math.random() * 30, // Spike at 1200Hz
}));

export const SAMPLE_EVIDENCE: Record<string, Evidence> = {
  'sap-co': {
    id: 'ev-001',
    source: 'SAP-CO Module',
    timestamp: 'Today, 09:00:15',
    confidence: 'High',
    type: 'SAP',
    details: 'Procurement Order PO-99823 shows a 15% price hike in metallurgical coke due to supplier shortages.',
    dataPoints: [
      { label: 'Prev Price', value: '¥2,100/t' },
      { label: 'Curr Price', value: '¥2,415/t', change: 15 },
    ]
  },
  'vib-sensor': {
    id: 'ev-002',
    source: 'IoT Sensor VIB-204',
    timestamp: 'Real-time',
    confidence: 'Medium',
    type: 'IoT',
    details: 'Fourier transform analysis indicates dominant frequency at 1200Hz, characteristic of inner race defects.',
    dataPoints: [
      { label: 'Peak Freq', value: '1200Hz' },
      { label: 'Amplitude', value: '4.2mm/s', change: 120 },
    ]
  }
};