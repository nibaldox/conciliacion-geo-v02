import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';
import { SectionNavigator } from './SectionNavigator';
import type { SectionMeta } from '../domain/types';
import { formatStatus } from '../domain/status';

export interface SectionHeaderProps {
  readonly section: SectionMeta;
  readonly benchCount: number;
  readonly floorElevation?: number | null;
  readonly crestElevationMax?: number | null;
  readonly lastRunAt?: string | null;
}

interface Fact {
  readonly key: string;
  readonly label: string;
  readonly value: string;
}

export function SectionHeader({ section, benchCount, floorElevation, crestElevationMax, lastRunAt }: SectionHeaderProps) {
  const { t } = useTranslation();

  const facts: Fact[] = [
    { key: 'azimuth', label: t('profileView.header.azimuth', { defaultValue: 'Azimut' }), value: `${section.azimuth.toFixed(0)}°` },
    { key: 'sector', label: t('profileView.header.sector', { defaultValue: 'Sector' }), value: section.sector || '—' },
    { key: 'length', label: t('profileView.header.length', { defaultValue: 'Longitud' }), value: `${section.length.toFixed(1)} m` },
    { key: 'benches', label: t('profileView.header.benches', { defaultValue: 'Bancos' }), value: String(benchCount) },
  ];
  if (floorElevation != null && Number.isFinite(floorElevation)) {
    facts.push({ key: 'floor', label: t('profileView.header.floorElev', { defaultValue: 'Cota piso' }), value: `${floorElevation.toFixed(0)} m` });
  }
  if (crestElevationMax != null && Number.isFinite(crestElevationMax)) {
    facts.push({ key: 'crest', label: t('profileView.header.crestMax', { defaultValue: 'Cota cresta' }), value: `${crestElevationMax.toFixed(0)} m` });
  }

  return (
    <header data-slot="section-header" className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
      <h2 className="truncate text-base font-semibold text-text-primary" title={section.id}>
        {section.name}
      </h2>
      <p data-slot="section-header-facts" className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs text-text-muted">
        {facts.map((fact, index) => (
          <Fragment key={fact.key}>
            {index > 0 && <span aria-hidden="true">·</span>}
            <span data-fact={fact.key} className="whitespace-nowrap">
              {fact.label} <span className="tabular-nums text-text-secondary">{fact.value}</span>
            </span>
          </Fragment>
        ))}
      </p>
      <div className="flex-1" />
      {lastRunAt && (
        <span className="hidden text-xs tabular-nums text-text-muted lg:inline" title={lastRunAt}>
          {t('profileView.header.last_run_short', {
            defaultValue: 'Último análisis hace {{ago}}',
            ago: formatRelativeTime(lastRunAt),
          })}
        </span>
      )}
      <SectionNavigator variant="compact" />
    </header>
  );
}

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

export { formatRelativeTime };

export function isSectionStatus(s: string): s is ReturnType<typeof formatStatus> {
  return s === 'CUMPLE' || s === 'FUERA' || s === 'NO_CUMPLE' || s === 'UNKNOWN';
}
