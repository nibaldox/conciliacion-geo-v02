import { useTranslation } from 'react-i18next';
import type { Bench } from '../domain/types';
import { StatusPill } from './atoms/StatusPill';

interface BenchInspectorProps {
  bench: Bench | null;
}

export function BenchInspector({ bench }: BenchInspectorProps) {
  const { t } = useTranslation();
  const value = (n: number | null | undefined, unit: string) => n != null && Number.isFinite(n) ? `${n.toFixed(1)} ${unit}` : '—';
  const metrics = bench ? [
    { key: 'height', actual: bench.height, design: bench.designHeight, unit: 'm' },
    { key: 'angle', actual: bench.faceAngle, design: bench.designAngle, unit: '°' },
    { key: 'berm', actual: bench.bermWidth, design: bench.designBerm, unit: 'm' },
  ] : [];

  return (
    <aside data-slot="bench-inspector" aria-label={t('profileView.inspector.title')} className="rounded-xl border border-border bg-surface-raised p-5">
      <h3 className="border-b border-border pb-4 text-sm font-semibold text-text-secondary">{t('profileView.inspector.title')}</h3>
      {bench ? (
        <div className="pt-4">
          <p className="mb-5 text-2xl font-semibold">{t('profileView.inspector.bench', { number: String(bench.benchNumber).padStart(2, '0') })}</p>
          <dl className="space-y-4">
            {metrics.map((metric) => (
              <div key={metric.key} className="border-b border-border pb-3">
                <div className="flex items-center justify-between gap-3"><dt className="text-sm text-text-secondary">{t(`profileView.inspector.${metric.key}`)}</dt><dd className="text-sm font-semibold tabular-nums">{value(metric.actual, metric.unit)}</dd></div>
                <div className="mt-1 flex items-center justify-between text-xs text-text-muted"><dt>{t('profileView.inspector.design')}</dt><dd className="tabular-nums">{value(metric.design, metric.unit)}</dd></div>
              </div>
            ))}
            <div className="flex flex-wrap items-center justify-between gap-2"><dt className="text-sm text-text-secondary">{t('profileView.inspector.status')}</dt><dd><StatusPill status={bench.status} label={t(`profileView.status.${bench.status}`)} /></dd></div>
          </dl>
        </div>
      ) : (
        <div className="py-8"><p className="mb-2 text-base font-medium">{t('profileView.inspector.empty')}</p><p className="text-sm leading-relaxed text-text-muted">{t('profileView.inspector.hint')}</p></div>
      )}
    </aside>
  );
}
