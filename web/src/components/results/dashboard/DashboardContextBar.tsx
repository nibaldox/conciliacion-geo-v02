import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Tolerances } from '../../../api/types';
import { DEFAULT_TOLERANCES } from '../../../utils/constants';
import { formatLocaleNumber } from '../../../utils/format';

export interface DashboardContextChip {
  readonly key: string;
  readonly label: string;
  readonly onRemove: () => void;
}

export interface DashboardContextBarProps {
  readonly designName: string | null;
  readonly topoName: string | null;
  readonly sectionLengthM: number | null;
  readonly tolerances: Tolerances;
  readonly activeChips: readonly DashboardContextChip[];
  readonly onClearAllFilters?: () => void;
  readonly filterTrigger?: ReactNode;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatPairedTolerance(
  range: Record<string, number> | undefined,
  unit: string,
  language: string,
): string {
  if (!range) return '—';
  const neg = range.neg;
  const pos = range.pos;
  if (isFiniteNumber(neg) && isFiniteNumber(pos)) {
    if (Math.abs(neg - pos) < 1e-9) {
      return `±${formatLocaleNumber(pos, language, 1)}${unit}`;
    }
    return `−${formatLocaleNumber(neg, language, 1)} / +${formatLocaleNumber(pos, language, 1)}${unit}`;
  }
  const single = isFiniteNumber(pos) ? pos : isFiniteNumber(neg) ? neg : range.max;
  if (isFiniteNumber(single)) {
    return `±${formatLocaleNumber(single, language, 1)}${unit}`;
  }
  return '—';
}

function formatMinTolerance(
  range: Record<string, number> | undefined,
  unit: string,
  language: string,
): string {
  const min = range?.min;
  if (!isFiniteNumber(min)) return '—';
  return `≥ ${formatLocaleNumber(min, language, 1)}${unit}`;
}

export function DashboardContextBar({
  designName,
  topoName,
  sectionLengthM,
  tolerances,
  activeChips,
  onClearAllFilters,
  filterTrigger,
}: DashboardContextBarProps) {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;

  const heightText = formatPairedTolerance(tolerances.bench_height, ' m', language);
  const angleText = formatPairedTolerance(tolerances.face_angle, '°', language);
  const bermText = formatMinTolerance(tolerances.berm_width, ' m', language);
  const crestToeText = formatPairedTolerance(
    tolerances.crest_toe_deviation ?? DEFAULT_TOLERANCES.crest_toe_deviation,
    ' m',
    language,
  );
  const sectionLengthText =
    sectionLengthM != null && Number.isFinite(sectionLengthM)
      ? `${formatLocaleNumber(sectionLengthM, language, Number.isInteger(sectionLengthM) ? 0 : 1)} m`
      : null;

  return (
    <section
      data-slot="dashboard-context-bar"
      className="space-y-2 border-b border-border pb-3 text-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-text-secondary">
          <span className="inline-flex items-center gap-1.5">
            <span className="text-text-muted">{t('dashboard.context.design')}:</span>
            <strong className="font-medium text-text-primary">{designName || '—'}</strong>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="text-text-muted">{t('dashboard.context.topo')}:</span>
            <strong className="font-medium text-text-primary">{topoName || '—'}</strong>
          </span>
          {sectionLengthText ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="text-text-muted">{t('dashboard.context.section_length')}:</span>
              <strong className="font-medium tabular-nums text-text-primary">{sectionLengthText}</strong>
            </span>
          ) : null}
        </div>
        {filterTrigger ? (
          <div className="flex shrink-0 items-center gap-2">{filterTrigger}</div>
        ) : null}
      </div>

      <div
        data-slot="dashboard-criteria-line"
        className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border pt-2 text-text-secondary"
      >
        <span className="font-medium text-text-muted">{t('dashboard.context.criteria_label')}:</span>
        <span className="tabular-nums">
          {t('dashboard.context.height_tol')}{' '}
          <strong className="font-medium text-text-primary">{heightText}</strong>
        </span>
        <span aria-hidden="true" className="text-text-muted">·</span>
        <span className="tabular-nums">
          {t('dashboard.context.angle_tol')}{' '}
          <strong className="font-medium text-text-primary">{angleText}</strong>
        </span>
        <span aria-hidden="true" className="text-text-muted">·</span>
        <span className="tabular-nums">
          {t('dashboard.context.berm_min')}{' '}
          <strong className="font-medium text-text-primary">{bermText}</strong>
        </span>
        <span aria-hidden="true" className="text-text-muted">·</span>
        <span className="tabular-nums">
          {t('dashboard.context.crest_toe_tol')}{' '}
          <strong className="font-medium text-text-primary">{crestToeText}</strong>
        </span>
        <span aria-hidden="true" className="text-text-muted">·</span>
        <span className="text-text-muted">{t('dashboard.context.formula_short')}</span>
      </div>

      {activeChips.length > 0 ? (
        <div
          data-slot="dashboard-active-filters"
          className="flex flex-wrap items-center gap-1.5 border-t border-border pt-2"
        >
          <span className="mr-1 text-text-muted">{t('dashboard.context.active_filters')}:</span>
          {activeChips.map((chip) => (
            <span key={chip.key} className="ui-chip" data-tone="accent">
              <span>{chip.label}</span>
              <button
                type="button"
                onClick={chip.onRemove}
                aria-label={`${t('dashboard.context.clear_filter')}: ${chip.label}`}
                className="ml-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full text-current hover:bg-surface-muted/40"
              >
                ×
              </button>
            </span>
          ))}
          {onClearAllFilters ? (
            <button
              type="button"
              onClick={onClearAllFilters}
              className="ml-1 text-xs font-medium text-text-muted underline-offset-2 hover:text-text-primary hover:underline"
            >
              {t('dashboard.context.clear_filter')}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
