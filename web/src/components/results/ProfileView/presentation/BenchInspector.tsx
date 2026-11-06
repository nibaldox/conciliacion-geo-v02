import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Bench } from '../domain/types';
import { StatusPill } from './atoms/StatusPill';

interface BenchInspectorProps {
  bench: Bench | null;
}

const PLACEHOLDER = '—';

const CELL_DEFAULTS = {
  height: 'Altura',
  angle: 'Ángulo',
  berm: 'Berma',
} as const;

function formatValue(n: number | null | undefined, unit: string): string {
  return n != null && Number.isFinite(n) ? `${n.toFixed(1)} ${unit}` : PLACEHOLDER;
}

interface CellProps {
  readonly label: string;
  readonly value: ReactNode;
  readonly design?: string;
  readonly designLabel?: string;
}

function Cell({ label, value, design, designLabel }: CellProps) {
  return (
    <div data-slot="bench-inspector-cell" className="flex min-w-0 flex-col justify-center gap-0.5 px-3">
      <dt className="truncate text-xs text-text-muted">{label}</dt>
      <dd className="flex h-6 min-w-0 items-center truncate text-base font-semibold tabular-nums text-text-primary">{value}</dd>
      <dd
        className="h-4 truncate text-xs tabular-nums text-text-muted"
        title={designLabel && design !== undefined ? `${designLabel}: ${design}` : undefined}
      >
        {design ?? ' '}
      </dd>
    </div>
  );
}

export function BenchInspector({ bench }: BenchInspectorProps) {
  const { t } = useTranslation();
  const designLabel = t('profileView.inspector.design');
  const hint = t('profileView.inspector.hint');
  const metrics = [
    { key: 'height', actual: bench?.height, design: bench?.designHeight, unit: 'm' },
    { key: 'angle', actual: bench?.faceAngle, design: bench?.designAngle, unit: '°' },
    { key: 'berm', actual: bench?.bermWidth, design: bench?.designBerm, unit: 'm' },
  ] as const;

  return (
    <aside
      data-slot="bench-inspector"
      data-selected={bench ? 'true' : 'false'}
      aria-label={t('profileView.inspector.title')}
      className="flex h-24 shrink-0 flex-col justify-center gap-1 overflow-hidden border-t border-border px-1 py-2"
    >
      <dl className="grid grid-cols-5 divide-x divide-border">
        <Cell
          label={t('profileView.inspector.cell_bench', { defaultValue: 'Banco' })}
          value={bench ? t('profileView.inspector.bench', { number: String(bench.benchNumber).padStart(2, '0') }) : PLACEHOLDER}
        />
        {metrics.map((metric) => (
          <Cell
            key={metric.key}
            label={t(`profileView.inspector.cell_${metric.key}`, { defaultValue: CELL_DEFAULTS[metric.key] })}
            value={bench ? formatValue(metric.actual, metric.unit) : PLACEHOLDER}
            design={bench ? formatValue(metric.design, metric.unit) : undefined}
            designLabel={bench ? designLabel : undefined}
          />
        ))}
        <Cell
          label={t('profileView.inspector.status')}
          value={bench ? <StatusPill status={bench.status} size="sm" label={t(`profileView.status.${bench.status}`)} /> : PLACEHOLDER}
        />
      </dl>
      <p data-slot="bench-inspector-hint" className="h-4 truncate px-3 text-xs text-text-muted" title={bench ? undefined : hint}>
        {bench ? t('profileView.inspector.legend', { defaultValue: 'Valor real arriba · diseño debajo' }) : (
          <>
            <span>{t('profileView.inspector.empty')}</span>
            <span aria-hidden="true"> · </span>
            <span>{hint}</span>
          </>
        )}
      </p>
    </aside>
  );
}
