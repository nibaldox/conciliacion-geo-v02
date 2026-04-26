import { Suspense, useState } from 'react';
import { SectionSelector } from './SectionSelector';
import { ExportPanel } from '../export/ExportPanel';
import {
  LazyProfileChart,
  LazyResultsTable,
  LazyDashboard,
  LazyBenchEditor,
  LazyAIReporter,
} from '../lazy';
import { LoadingSpinner } from '../LoadingSpinner';
import { useSession } from '../../stores/session';

type ResultsTab = 'profiles' | 'table' | 'dashboard' | 'bench-editor' | 'export' | 'ai';

const RESULT_TABS: { key: ResultsTab; label: string; icon: string }[] = [
  { key: 'profiles', label: 'Perfiles', icon: '📈' },
  { key: 'table', label: 'Tabla', icon: '📋' },
  { key: 'dashboard', label: 'Dashboard', icon: '📊' },
  { key: 'bench-editor', label: 'Bancos', icon: '✏️' },
  { key: 'export', label: 'Exportar', icon: '💾' },
  { key: 'ai', label: 'Informe IA', icon: '🤖' },
];

export function Step4Content() {
  const [activeTab, setActiveTab] = useState<ResultsTab>('profiles');
  const { prevStep } = useSession();

  return (
    <div className="flex flex-col h-full gap-5">
      {/* Tab bar */}
      <div className="flex gap-2" role="tablist" aria-label="Vistas de resultados">
        {RESULT_TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`
              px-4 py-2.5 rounded-lg text-sm font-medium transition-all
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

      {/* Tab content */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'profiles' && (
          <div className="space-y-4">
            <SectionSelector />
            <Suspense fallback={<LoadingSpinner message="Cargando perfiles…" />}>
              <LazyProfileChart />
            </Suspense>
          </div>
        )}

        {activeTab === 'table' && (
          <Suspense fallback={<LoadingSpinner message="Cargando tabla…" />}>
            <LazyResultsTable />
          </Suspense>
        )}

        {activeTab === 'dashboard' && (
          <Suspense fallback={<LoadingSpinner message="Cargando dashboard…" />}>
            <LazyDashboard />
          </Suspense>
        )}

        {activeTab === 'bench-editor' && (
          <Suspense fallback={<LoadingSpinner message="Cargando editor de bancos…" />}>
            <LazyBenchEditor />
          </Suspense>
        )}

        {activeTab === 'export' && <ExportPanel />}

        {activeTab === 'ai' && (
          <Suspense fallback={<LoadingSpinner message="Cargando informe IA…" />}>
            <LazyAIReporter />
          </Suspense>
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-start pt-1 pb-1">
        <button
          onClick={prevStep}
          className="px-5 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          ← Anterior
        </button>
      </div>
    </div>
  );
}
