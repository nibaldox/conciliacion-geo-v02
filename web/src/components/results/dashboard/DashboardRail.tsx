import { ProfilePreview } from './ProfilePreview';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../../stores/session';
import type { ComparisonResult } from '../../../api/types';
import type { BenchStatus } from '../ProfileView/domain/types';
import { formatLocaleNumber, formatLocalePercent, formatLocaleSigned } from '../../../utils/format';
import { StatusDot, statusToneColor } from '../SummaryControls';
import { parameterBars, parameterTone, sectionSummary } from './dashboardSelectors';

export function ParameterBars({ rows }: { rows: readonly ComparisonResult[] }) {
  const { t, i18n } = useTranslation();
  const language = i18n?.resolvedLanguage ?? i18n?.language;
  const bars = parameterBars(rows);
  const comparedCount = Math.max(0, ...bars.map((bar) => bar.ok + bar.warn + bar.nok));
  const tones = ['ok', 'warn', 'nok'] as const;
  return (
    <section className="space-y-3 border-t border-border py-5" data-slot="parameter-bars">
      <h2 className="ui-section-title">{t('dashboard.rail.parameters')}</h2>
      {bars.map((bar) => {
        const count = bar.ok + bar.warn + bar.nok;
        return (
          <div key={bar.parameter}>
            <div className="flex justify-between text-xs">
              <span>{t(`dashboard.parameter.${bar.parameter}`)}</span>
              <span className="tabular-nums">
                {count ? formatLocalePercent((100 * bar.ok) / count, language, 1) : '—'}
              </span>
            </div>
            <div
              className="mt-1 flex h-1.5 w-full"
              aria-label={t('dashboard.rail.bar_counts', { ok: bar.ok, warn: bar.warn, nok: bar.nok, unknown: bar.unknown })}
            >
              {tones.map((tone) => (
                <span
                  key={tone}
                  style={{ width: `${count ? (100 * bar[tone]) / count : 0}%`, backgroundColor: statusToneColor(tone) }}
                />
              ))}
            </div>
          </div>
        );
      })}
      <p className="text-xs text-text-muted">{t('dashboard.rail.denominator', { n: comparedCount })}</p>
    </section>
  );
}

export function SelectedSectionPanel({
  name,
  sectionId,
  rows,
  statuses,
  onClear,
  onOpen,
  canOpen,
}: {
  name: string | null;
  sectionId: string | null;
  rows: readonly ComparisonResult[];
  statuses: ReadonlyMap<string, BenchStatus>;
  onClear: () => void;
  onOpen: () => void;
  canOpen: boolean;
}) {
  const { t, i18n } = useTranslation();
  const language = i18n?.resolvedLanguage ?? i18n?.language;
  const setProfilesMode = useSession((s) => s.setProfilesMode);
  const summary = name ? sectionSummary(rows, name, statuses) : null;
  const scoreText = summary?.score == null ? '—' : `${formatLocaleNumber(summary.score, language, 1)} /100`;

  return (
    <section data-slot="selected-section" className="min-w-0 border-t border-border py-5 text-xs">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="ui-section-title">{t('dashboard.rail.selected')}</h2>
        {summary && (
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={!canOpen}
              onClick={() => {
                setProfilesMode('detail');
                onOpen();
              }}
              className="rounded border border-border px-2 py-0.5 font-medium text-accent transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:text-text-muted"
            >
              {t('dashboard.rail.open_profile')} →
            </button>
            <button type="button" onClick={onClear} className="text-text-secondary hover:text-text-primary">
              {t('dashboard.rail.clear')}
            </button>
          </div>
        )}
      </div>
      {sectionId ? (
        <ProfilePreview
          sectionId={sectionId}
          onOpen={() => {
            setProfilesMode('detail');
            onOpen();
          }}
        />
      ) : (
        <div data-slot="profile-preview-placeholder" className="flex h-[180px] items-center justify-center text-text-muted">
          —
        </div>
      )}
      <div className="mb-3 truncate text-base font-medium text-text-primary">{summary ? name : '—'}</div>
      <div className="grid grid-cols-2 gap-2 tabular-nums text-text-secondary">
        <span>{t('dashboard.rail.score')}: {scoreText}</span>
        <span>{t('dashboard.rail.status')}: {summary ? t(`dashboard.rail.status_${summary.status.toLowerCase()}`) : '—'}</span>
        {(['height_dev', 'angle_dev', 'delta_crest', 'delta_toe'] as const).map((field) => (
          <span key={field}>
            {t(`dashboard.rail.${field}`)}:{' '}
            {formatLocaleSigned(summary?.means[field], language, 1, field === 'angle_dev' ? '°' : ' m')}
          </span>
        ))}
      </div>
      {summary && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead className="text-text-muted">
              <tr className="border-b border-border">
                <th scope="col" className="py-1 pr-2 font-medium">{t('dashboard.rail.bench')}</th>
                <th scope="col" className="py-1 pr-2 font-medium">{t('dashboard.rail.elevation')}</th>
                {(['height', 'angle', 'berm'] as const).map((p) => (
                  <th scope="col" key={p} className="py-1 pr-2 font-medium">{t(`dashboard.parameter.${p}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.benches.map((row, index) => (
                <tr key={`${row.bench_num}-${row.level}-${index}`} className="border-b border-border last:border-b-0">
                  <td className="py-1 pr-2 tabular-nums">{row.bench_num}</td>
                  <td className="py-1 pr-2 tabular-nums">{row.level || '—'}</td>
                  {(['height', 'angle', 'berm'] as const).map((p) => {
                    const tone = parameterTone(row[`${p}_status`]);
                    return (
                      <td key={p} className="py-1 pr-2" aria-label={row[`${p}_status`] || t('dashboard.rail.status_unknown')}>
                        <StatusDot tone={tone === 'unknown' ? 'muted' : tone} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
