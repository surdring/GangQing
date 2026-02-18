import React from 'react';
import { LayoutDashboard, MessageSquareText, FileText, Settings, ShieldAlert, Cpu } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface SidebarProps {
  activeView: string;
  onViewChange: (view: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ activeView, onViewChange }) => {
  const { t } = useTranslation();
  const menuItems = [
    { id: 'dashboard', icon: LayoutDashboard, label: t('sidebar.commandCenter') },
    { id: 'chat', icon: MessageSquareText, label: t('sidebar.agentChat') },
    { id: 'tasks', icon: FileText, label: t('sidebar.workOrders') },
    { id: 'simulation', icon: Cpu, label: t('sidebar.sandbox') },
  ];

  return (
    <div className="w-20 lg:w-64 h-screen bg-steel-900 border-r border-steel-700 flex flex-col justify-between shrink-0 transition-all duration-300">
      <div>
        <div className="h-16 flex items-center justify-center lg:justify-start lg:px-6 border-b border-steel-700">
            <div className="w-8 h-8 bg-molten-500 rounded flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-molten-500/20">
                G
            </div>
            <span className="hidden lg:block ml-3 font-bold text-lg tracking-wide text-slate-100">GangQing</span>
        </div>

        <nav className="mt-6 flex flex-col gap-2 px-2">
          {menuItems.map((item) => {
            const isActive = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`flex items-center p-3 rounded-lg transition-colors duration-200 group ${
                  isActive 
                  ? 'bg-steel-800 text-molten-500 border-l-2 border-molten-500' 
                  : 'text-slate-400 hover:bg-steel-800 hover:text-slate-200 border-l-2 border-transparent'
                }`}
              >
                <item.icon size={20} />
                <span className="hidden lg:block ml-3 font-medium text-sm">{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      <div className="p-4 border-t border-steel-700">
         <div className="flex items-center gap-3 p-2 rounded bg-steel-800/50 border border-steel-700">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-slate-600 to-slate-500 flex items-center justify-center text-xs font-bold">
                JM
            </div>
            <div className="hidden lg:block overflow-hidden">
                <p className="text-sm font-medium truncate">{t('sidebar.userName')}</p>
                <p className="text-xs text-slate-500 truncate">{t('sidebar.userTitle')}</p>
            </div>
         </div>
      </div>
    </div>
  );
};

export default Sidebar;