import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { SCENARIOS } from './constants';
import { Scenario } from './types';
import { FlaskConical } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function App() {
  const { t, i18n } = useTranslation();
  const normalizedLanguage = (i18n.resolvedLanguage || i18n.language || 'zh').startsWith('en') ? 'en' : 'zh';
  const [activeView, setActiveView] = useState('chat');
  const [activeScenario, setActiveScenario] = useState<Scenario>(SCENARIOS[0]);
  const [isSandboxMode, setIsSandboxMode] = useState(false);

  return (
    <div className={`flex h-screen w-full overflow-hidden ${isSandboxMode ? 'border-8 border-yellow-500/30' : ''}`}>
      <Sidebar activeView={activeView} onViewChange={setActiveView} />
      
      <main className="flex-1 flex flex-col min-w-0 bg-gradient-to-br from-steel-900 via-steel-900 to-steel-800">
        
        {/* Top Bar for Scenario Selection (Demo Purpose) */}
        <div className="h-14 border-b border-steel-700 flex items-center justify-between px-6 bg-steel-900/80 backdrop-blur z-10">
            <div className="flex items-center gap-4">
                <span className="text-slate-500 text-sm font-medium">{t('scenarios.activeScenario')}</span>
                <div className="flex gap-2">
                    {SCENARIOS.map(s => (
                        <button
                            key={s.id}
                            onClick={() => {
                                setActiveScenario(s);
                                setIsSandboxMode(s.id === 'simulation');
                                setActiveView('chat');
                            }}
                            className={`px-3 py-1 rounded text-xs font-medium border transition-colors ${
                                activeScenario.id === s.id 
                                ? 'bg-steel-700 text-white border-steel-600' 
                                : 'text-slate-500 border-transparent hover:bg-steel-800'
                            }`}
                        >
                            {t(s.name)}
                        </button>
                    ))}
                </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1 text-xs">
                <button
                  onClick={() => i18n.changeLanguage('zh')}
                  className={`px-2 py-1 rounded border ${normalizedLanguage === 'zh' ? 'border-molten-500 text-molten-500' : 'border-steel-700 text-slate-400 hover:text-slate-200'}`}
                >
                  {t('language.zh')}
                </button>
                <button
                  onClick={() => i18n.changeLanguage('en')}
                  className={`px-2 py-1 rounded border ${normalizedLanguage === 'en' ? 'border-molten-500 text-molten-500' : 'border-steel-700 text-slate-400 hover:text-slate-200'}`}
                >
                  {t('language.en')}
                </button>
              </div>

            {isSandboxMode && (
                <div className="flex items-center gap-2 px-3 py-1 bg-yellow-500/10 border border-yellow-500/40 rounded text-yellow-500 text-xs font-bold animate-pulse">
                    <FlaskConical size={14} />
                    {t('app.simulationMode')}
                </div>
            )}
            </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 relative">
             {activeView === 'chat' ? (
                 <ChatInterface activeScenario={activeScenario} />
             ) : (
                 <div className="flex flex-col items-center justify-center h-full text-slate-500">
                     <h2 className="text-2xl font-light mb-2">{t('app.workInProgress')}</h2>
                     <p>{t('app.moduleNotAvailable')}</p>
                     <button 
                        onClick={() => setActiveView('chat')}
                        className="mt-6 px-4 py-2 bg-steel-800 hover:bg-steel-700 rounded text-slate-300"
                     >
                        {t('app.returnToAgent')}
                     </button>
                 </div>
             )}
        </div>
      </main>
    </div>
  );
}