export enum UserRole {
  MANAGER = 'manager',
  SCHEDULER = 'scheduler',
  MAINTENANCE = 'maintenance',
}

export interface Evidence {
  id: string;
  source: string;
  timestamp: string;
  confidence: 'High' | 'Medium' | 'Low';
  details: string;
  type: 'SAP' | 'MES' | 'DCS' | 'IoT' | 'Manual';
  dataPoints?: { label: string; value: string | number; change?: number }[];
}

export interface ChartDataPoint {
  name: string;
  value: number;
  type?: 'increase' | 'decrease' | 'total';
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  evidence?: Evidence[]; // The "Trust Pills"
  chartData?: ChartDataPoint[]; // For dynamic visualizations
  chartType?: 'waterfall' | 'spectrum' | 'gantt';
  actions?: { label: string; handlerId: string; style: 'primary' | 'secondary' | 'danger' }[];
  isThinking?: boolean;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  initialMessage: string;
  role: UserRole;
}