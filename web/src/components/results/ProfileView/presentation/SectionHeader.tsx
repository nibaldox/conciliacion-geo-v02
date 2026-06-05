/**
 * SectionHeader — the row above the chart with the section's
 * identifying metadata.
 *
 * Visual: small caps tracking-wider labels, metric values inline.
 * Subtitle (bench count, last-run) in muted text below.
 */

import { useTranslation } from 'react-i18next';
import { MetricValue } from './atoms/MetricValue';
import type { SectionMeta } from '../domain/types';
import { formatStatus } from '../domain/status';

export interface SectionHeaderProps {
  readonly section: SectionMeta;
  readonly benchCount: number;
  /** Optional: ISO timestamp of the last successful analysis run. */
  readonly lastRunAt?: string | null;
}

export function SectionHeader({ section, benchCount, lastRunAt }: SectionHeaderProps) {
  const { t } = useTranslation();

  return (
    <header
      data-slot="section-header"
      className="px-3 md:px-6 py-3 border-b flex flex-wrap items-baseline gap-x-4 gap-y-1"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
    >
      <h2
        className="text-sm font-semibold mr-1"
        style={{ color: 'var(--color-text-primary)' }}
        title={section.id}
      >
        {section.name}
      </h2>

      <span
        className="text-[10px] uppercase tracking-wider font-semibold"
        style={{ color: 'var(--color-text-muted)' }}
      >
        ·
      </span>

      <MetricValue
        label={t('profileView.header.azimuth', { defaultValue: 'Az' })}
        value={section.azimuth.toFixed(0)}
        unit="°"
        size="sm"
      />
      <MetricValue
        label={t('profileView.header.sector', { defaultValue: 'Sector' })}
        value={section.sector || '—'}
        size="sm"
      />
      <MetricValue
        label={t('profileView.header.length', { defaultValue: 'Length' })}
        value={section.length.toFixed(1)}
        unit="m"
        size="sm"
      />
      <MetricValue
        label={t('profileView.header.benches', { defaultValue: 'Bancos' })}
        value={benchCount}
        size="sm"
      />

      <div className="flex-1" />

      {lastRunAt && (
        <span
          className="text-[11px] tabular-nums"
          style={{ color: 'var(--color-text-muted)' }}
          title={lastRunAt}
        >
          {t('profileView.header.last_run', {
            defaultValue: 'Último análisis: {{ago}}',
            ago: formatRelativeTime(lastRunAt),
          })}
        </span>
      )}
    </header>
  );
}

// ─── Helper: "hace 2 minutos" / "hace 3 días" ────────────────

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const now = Date.now();
  const diffMs = now - then;
  const sec = Math.round(diffMs / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} min`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} h`;
  const day = Math.round(hr / 24);
  return `${day} d`;
}

// Helper for the `title` attribute, when needed externally.
export { formatRelativeTime };

// Type guard for narrow string unions (kept here as a utility)
export function isSectionStatus(s: string): s is ReturnType<typeof formatStatus> {
  return s === 'CUMPLE' || s === 'FUERA' || s === 'NO_CUMPLE' || s === 'UNKNOWN';
}
