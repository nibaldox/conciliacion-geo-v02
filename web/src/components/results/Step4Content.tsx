import { Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
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

const RESULT_TABS: { key: ResultsTab; translationKey: string; icon: string }[] = [
  { key: 'profiles', translationKey: 'step4.tab_profiles', icon: '📈' },
  { key: 'table', translationKey: 'step4.tab_table', icon: '📋' },
  { key: 'dashboard', translationKey: 'step4.tab_dashboard', icon: '📊' },
  { key: 'bench-editor', translationKey: 'step4.tab_bench_editor', icon: '✏️' },
  { key: 'export', translationKey: 'step4.tab_export', icon: '💾' },
  { key: 'ai', translationKey: 'step4.tab_ai', icon: '🤖' },
];

export function Step4Content() {
  const [activeTab, setActiveTab] = useState<ResultsTab>('profiles');
  const { prevStep } = useSession();
  const { t } = useTranslation();

  return (
    <div className="flex flex-col h-full gap-4 min-h-0">
      {/* Tab bar */}
      <div className="flex gap-2 shrink-0 overflow-x-auto" role="tablist" aria-label={t('step4.title')}>
        {RESULT_TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className="shrink-0 px-4 py-2.5 rounded-lg text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue focus-visible:ring-offset-2"
            style={activeTab === tab.key
              ? { backgroundColor: 'var(--color-mine-blue)', color: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }
              : { backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)', border: '1px solid var(--color-border)' }
            }
          >
            <span className="mr-1.5">{tab.icon}</span>
            {t(tab.translationKey)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-auto">
        {activeTab === 'profiles' && (
          <div className="space-y-4 h-full flex flex-col min-h-0">
            <div className="shrink-0">
              <SectionSelector />
            </div>
            <div className="flex-1 min-h-0 bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <Suspense fallback={<LoadingSpinner message={t('step4.loading_profiles')} />}>
                <div className="max-w-4xl mx-auto" style={{ height: '400px' }}>
                  <LazyProfileChart />
                </div>
              </Suspense>
            </div>
          </div>
        )}

        {activeTab === 'table' && (
          <Suspense fallback={<LoadingSpinner message={t('step4.loading_table')} />}>
            <LazyResultsTable />
          </Suspense>
        )}

        {activeTab === 'dashboard' && (
          <Suspense fallback={<LoadingSpinner message={t('step4.loading_dashboard')} />}>
            <LazyDashboard />
          </Suspense>
        )}

        {activeTab === 'bench-editor' && (
          <Suspense fallback={<LoadingSpinner message={t('step4.loading_bench_editor')} />}>
            <LazyBenchEditor />
          </Suspense>
        )}

        {activeTab === 'export' && <ExportPanel />}

        {activeTab === 'ai' && (
          <Suspense fallback={<LoadingSpinner message={t('step4.loading_ai')} />}>
            <LazyAIReporter />
          </Suspense>
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-start pt-1 pb-1 shrink-0">
        <button
          onClick={prevStep}
          className="px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
          style={{ border: '1px solid var(--color-border-strong)', color: 'var(--color-text-secondary)' }}
        >
          ← {t('nav.previous')}
        </button>
      </div>
    </div>
  );
}
