import { ProfilePreview } from './ProfilePreview';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../../stores/session';
import type { ComparisonResult } from '../../../api/types';
import type { BenchStatus } from '../ProfileView/domain/types';
import { StatusDot, statusToneColor } from '../SummaryControls';
import { parameterBars, parameterTone, sectionSummary } from './dashboardSelectors';

export function ParameterBars({ rows }: { rows: readonly ComparisonResult[] }) {
  const { t } = useTranslation();
  const bars = parameterBars(rows);
  const tones = ['ok', 'warn', 'nok', 'unknown'] as const;
  return <section className="space-y-3 border-t border-border py-5" data-slot="parameter-bars">
    <h2 className="ui-section-title">{t('dashboard.rail.parameters')}</h2>
    {bars.map((bar) => <div key={bar.parameter}>
      <div className="flex justify-between text-xs"><span>{t(`dashboard.parameter.${bar.parameter}`)}</span><span className="tabular-nums">{rows.length ? `${(100 * bar.ok / rows.length).toFixed(1)}%` : '—'}</span></div>
      <div className="mt-1 flex h-1.5 w-full" aria-label={t('dashboard.rail.bar_counts', { ok: bar.ok, warn: bar.warn, nok: bar.nok, unknown: bar.unknown })}>
        {tones.map((tone) => <span key={tone} style={{ width: `${rows.length ? 100 * bar[tone] / rows.length : 0}%`, backgroundColor: tone === 'unknown' ? 'var(--color-text-muted)' : statusToneColor(tone) }} />)}
      </div>
    </div>)}
    <p className="text-xs text-text-muted">{t('dashboard.rail.denominator')}</p>
  </section>;
}

export function SelectedSectionPanel({ name, sectionId, rows, statuses, onClear, onOpen, canOpen }: { name: string | null; sectionId: string | null; rows: readonly ComparisonResult[]; statuses: ReadonlyMap<string, BenchStatus>; onClear: () => void; onOpen: () => void; canOpen: boolean }) {
  const { t } = useTranslation();
  const setProfilesMode = useSession((s) => s.setProfilesMode);
  const summary = name ? sectionSummary(rows, name, statuses) : null;
  const format = (value: number | null | undefined, unit: string) => value == null ? '—' : `${value.toFixed(1)} ${unit}`;
  return <section data-slot="selected-section" className="border-t border-border py-5 text-xs">
    <h2 className="ui-section-title mb-3">{t('dashboard.rail.selected')}</h2>
    {sectionId ? <ProfilePreview sectionId={sectionId} onOpen={() => { setProfilesMode('detail'); onOpen(); }} /> : <div data-slot="profile-preview-placeholder" className="flex h-[180px] items-center justify-center text-text-muted">—</div>}
    <div className="mb-3 text-base text-text-primary">{summary ? name : '—'}</div>
    <div className="grid grid-cols-2 gap-2 text-text-secondary">
      <span>{t('dashboard.rail.score')}: {format(summary?.score, '/100')}</span>
      <span>{t('dashboard.rail.status')}: {summary ? t(`dashboard.rail.status_${summary.status.toLowerCase()}`) : '—'}</span>
      {(['height_dev', 'angle_dev', 'delta_crest', 'delta_toe'] as const).map((field) => <span key={field}>{t(`dashboard.rail.${field}`)}: {format(summary?.means[field], field === 'angle_dev' ? '°' : 'm')}</span>)}
    </div>
    {summary && <><table className="mt-3 w-full text-left"><thead className="text-text-muted"><tr><th>{t('dashboard.rail.bench')}</th><th>{t('dashboard.rail.elevation')}</th>{(['height', 'angle', 'berm'] as const).map((p) => <th key={p}>{t(`dashboard.parameter.${p}`)}</th>)}</tr></thead><tbody>{summary.benches.map((row, index) => <tr key={`${row.bench_num}-${row.level}-${index}`} className="border-b border-border"><td className="py-1 tabular-nums">{row.bench_num}</td><td className="tabular-nums">{row.level ?? '—'}</td>{(['height', 'angle', 'berm'] as const).map((p) => { const tone = parameterTone(row[`${p}_status`]); return <td key={p} aria-label={row[`${p}_status`] || t('dashboard.rail.status_unknown')}><StatusDot tone={tone === 'unknown' ? 'muted' : tone} /></td>; })}</tr>)}</tbody></table>
      <div className="mt-3 flex gap-4"><button type="button" disabled={!canOpen} onClick={() => { setProfilesMode('detail'); onOpen(); }} className="text-accent disabled:text-text-muted">{t('dashboard.rail.open_profile')} →</button><button type="button" onClick={onClear} className="text-text-secondary">{t('dashboard.rail.clear')}</button></div></>}
  </section>;
}
