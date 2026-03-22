import { UserRole, Scenario } from './types';
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