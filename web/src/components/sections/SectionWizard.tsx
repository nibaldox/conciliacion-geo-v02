import { useState, useCallback } from 'react';
import { SectionAutoForm } from './SectionAutoForm';
import { SectionManualForm } from './SectionManualForm';
import { SectionClickForm } from './SectionClickForm';
import { SectionFileUpload } from './SectionFileUpload';
import { SectionList } from './SectionList';
import { PlanView } from '../mesh/PlanView';
import { useSession } from '../../stores/session';
import { useSections } from '../../api/hooks';

type SectionTab = 'auto' | 'manual' | 'click' | 'file';

const TABS: { key: SectionTab; label: string; icon: string }[] = [
  { key: 'auto', label: 'Automático', icon: '⚡' },
  { key: 'manual', label: 'Manual', icon: '✏️' },
  { key: 'click', label: 'Clic en Mapa', icon: '📍' },
  { key: 'file', label: 'Archivo', icon: '📁' },
];

export function SectionWizard() {
  const [activeTab, setActiveTab] = useState<SectionTab>('auto');
  const [clickHandler, setClickHandler] = useState<((x: number, y: number) => void) | null>(null);
  const { prevStep, nextStep } = useSession();
  const { data: sections } = useSections();

  const sectionCount = sections?.length ?? 0;

  // Adapter: PlanView provides {x, y}, SectionClickForm handler expects (x, y)
  const handlePlanClick = useCallback(
    (coords: { x: number; y: number }) => {
      clickHandler?.(coords.x, coords.y);
    },
    [clickHandler],
  );

  // Callback for SectionClickForm to register its click handler
  const handleRegisterClickHandler = useCallback(
    (handler: ((x: number, y: number) => void) | null) => {
      setClickHandler(handler);
    },
    [],
  );

  const showPlanView = activeTab === 'click';

  return (
    <div className="flex flex-col h-full gap-5">
      {/* Tab bar */}
      <div className="flex gap-2 overflow-x-auto" role="tablist" aria-label="Método de creación de secciones">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`
              shrink-0 px-4 py-2.5 rounded-lg text-sm font-medium transition-all
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue focus-visible:ring-offset-2
              ${
                activeTab === tab.key
                  ? 'bg-mine-blue text-white shadow-sm'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }
            `}
          >
            <span className="mr-1.5">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Main content area — split when click tab is active */}
      <div className={`flex-1 min-h-0 ${showPlanView ? 'flex gap-5' : ''}`}>
        {/* Form panel */}
        <div className={`bg-white rounded-xl border border-gray-200 p-5 overflow-auto ${showPlanView ? 'w-2/5 shrink-0' : ''}`}>
          {activeTab === 'auto' && <SectionAutoForm />}
          {activeTab === 'manual' && <SectionManualForm />}
          {activeTab === 'click' && (
            <SectionClickForm onRegisterClickHandler={handleRegisterClickHandler} />
          )}
          {activeTab === 'file' && <SectionFileUpload />}
        </div>

        {/* PlanView panel — only visible when click tab is active */}
        {showPlanView && (
          <div className="flex-1 min-h-[400px] rounded-xl overflow-hidden border border-gray-200 bg-gray-50">
            <PlanView onPointClick={clickHandler ? handlePlanClick : undefined} />
          </div>
        )}
      </div>

      {/* Existing sections list — uses dedicated SectionList component */}
      <SectionList />

      {/* Navigation */}
      <div className="flex items-center justify-between pt-1 pb-1">
        <button
          onClick={prevStep}
          className="px-5 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          ← Anterior
        </button>
        <button
          onClick={nextStep}
          disabled={sectionCount === 0}
          className={`
            px-6 py-2.5 rounded-lg font-medium text-sm transition-all
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue focus-visible:ring-offset-2
            ${
              sectionCount > 0
                ? 'bg-mine-blue text-white shadow-md hover:bg-blue-800 active:scale-[0.98]'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }
          `}
        >
          Siguiente →
        </button>
      </div>
    </div>
  );
}
