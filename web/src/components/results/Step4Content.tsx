/**
 * Step4Content — the "RESULTADOS" step (MISIÓN 04).
 *
 * Mission Control layout: a row of uppercase mono tabs at the
 * top, the active tab's content fills the rest, and a left-
 * aligned back button at the bottom. The ProfileView is the
 * centerpiece (built earlier with clean architecture; it just
 * needs the new Card/StatusBar atoms which it already uses).
 */

import { Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SectionSelector } from './SectionSelector';
import { ExportPanel } from '../export/ExportPanel';
import {
  LazyResultsTable,
  LazyDashboard,
  LazyBenchEditor,
  LazyAIReporter,
} from '../lazy';
import { LoadingSpinner } from '../LoadingSpinner';
import { ProfileView } from './ProfileView';
import { Button, StatusBar } from '../ui';
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
      {/* Tab bar — uppercase mono, like a console menu */}
      <div
        className="flex gap-1 shrink-0 overflow-x-auto p-1"
        role="tablist"
        aria-label={t('step4.title')}
        style={{
          backgroundColor: 'var(--color-surface-raised)',
          border: '1px solid var(--color-border)',
          borderRadius: '0.5rem',
        }}
      >
        {RESULT_TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className="shrink-0 px-3 py-1.5 text-[11px] uppercase tracking-widest font-semibold rounded transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            style={{
              backgroundColor: activeTab === tab.key
                ? 'var(--color-accent-bg)'
                : 'transparent',
              color: activeTab === tab.key
                ? 'var(--color-accent-bright)'
                : 'var(--color-text-muted)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            <span className="mr-1.5" aria-hidden="true">{tab.icon}</span>
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
            <div className="flex-1 min-h-0">
              <ProfileView />
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

      {/* Sector status — a tiny "site reconciliation" footer that
       *  matches the reference design's 'SECTOR 07: SITE
       *  RECONCILIATION' hero. */}
      <StatusBar
        title="SECTOR · SITE RECONCILIATION"
        entries={[
          { level: 'system', text: 'Secure link established' },
          { level: 'info', text: t('step4.footer_status', { defaultValue: 'Awaiting operator action' }) },
        ]}
      />

      {/* Navigation */}
      <div className="flex justify-start pt-1 pb-1 shrink-0">
        <Button variant="secondary" onClick={prevStep} size="sm">
          {t('step4.prev')}
        </Button>
      </div>
    </div>
  );
}
