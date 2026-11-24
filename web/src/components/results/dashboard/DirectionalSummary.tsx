import { useTranslation } from 'react-i18next';
import type { ComparisonResult } from '../../../api/types';
import {
  formatLocaleNumber,
  formatLocalePercent,
  formatLocaleSigned,
} from '../../../utils/format';
import { statusToneColor, type StatusTone } from '../SummaryControls';
import { parameterBars } from './dashboardSelectors';
import type { DirectionalStats } from './geotechSelectors';

export interface DirectionalSummaryProps {
  stats: DirectionalStats;
  rows: readonly ComparisonResult[];
}

const TONE_ICON: Record<StatusTone, string> = {
  ok: '✓',
  warn: '⚠',
  nok: '✗',
  muted: '·',
};

const BAR_TONES = ['ok', 'warn', 'nok'] as const;

function complianceToneFromPct(pct: number | null): StatusTone {
  if (pct === null) return 'muted';
  if (pct >= 70) return 'ok';
  if (pct >= 50) return 'warn';
  return 'nok';
}

function crestStatusTone(crest: DirectionalStats['crest']): StatusTone {
  if (crest.count === 0) return 'muted';
  if (crest.gt3mCount > 0) return 'nok';
  if (crest.gt1mCount > 0) return 'warn';
  return 'ok';
}

export function DirectionalSummary({ stats, rows }: DirectionalSummaryProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const bars = parameterBars(rows);
  const comparedCount = rows.filter((row) => row.type === 'MATCH').length;
  const crestTone = crestStatusTone(stats.crest);

  return (
    <section
      data-slot="directional-summary"
      className="min-w-0 space-y-3 border-t border-border py-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="ui-section-title">{t('dashboard.directional.title')}</h3>
        <span
          data-slot="directional-denominator"
          className="text-xs tabular-nums text-text-muted"
        >
          {t('dashboard.histograms.n_label', { n: comparedCount })}
        </span>
      </div>

      <div className="space-y-3">
        {bars.map((bar) => {
          const total = bar.ok + bar.warn + bar.nok;
          const pct = total > 0 ? (100 * bar.ok) / total : null;
          const tone = complianceToneFromPct(pct);

          return (
            <div key={bar.parameter} data-parameter={bar.parameter} className="space-y-1">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="flex items-center gap-1.5 font-medium text-text-primary">
                  <span
                    aria-hidden="true"
                    data-tone={tone}
                    className="inline-block w-3 text-center font-semibold"
                    style={{ color: statusToneColor(tone) }}
                  >
                    {TONE_ICON[tone]}
                  </span>
                  <span>{t(`dashboard.parameter.${bar.parameter}`)}</span>
                </span>
                <span
                  className="font-medium tabular-nums"
                  style={{ color: statusToneColor(tone) }}
                >
                  {pct === null ? '—' : formatLocalePercent(pct, lang, 1)}
                </span>
              </div>

              <div
                className="flex h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
                aria-label={t('dashboard.rail.bar_counts', {
                  ok: bar.ok,
                  warn: bar.warn,
                  nok: bar.nok,
                  unknown: bar.unknown,
                })}
              >
                {BAR_TONES.map((segmentTone) => (
                  <span
                    key={segmentTone}
                    style={{
                      width: `${total > 0 ? (100 * bar[segmentTone]) / total : 0}%`,
                      backgroundColor: statusToneColor(segmentTone),
                    }}
                  />
                ))}
              </div>

              {bar.parameter === 'height' && stats.height.count > 0 && (
                <p className="text-[11px] tabular-nums text-text-muted">
                  {t('dashboard.directional.height_over_under', {
                    over: stats.height.overTolCount,
                    under: stats.height.underTolCount,
                  })}
                  {stats.height.median !== null && (
                    <>
                      {' · '}
                      {t('dashboard.histograms.median_label', {
                        value: formatLocaleSigned(stats.height.median, lang, 2, ' m'),
                      })}
                    </>
                  )}
                </p>
              )}

              {bar.parameter === 'angle' && stats.angle.count > 0 && (
                <p className="text-[11px] tabular-nums text-text-muted">
                  {t('dashboard.directional.angle_flatter', {
                    count: stats.angle.flatterCount,
                    total: stats.angle.count,
                    median: formatLocaleSigned(stats.angle.median, lang, 1),
                  })}
                  {' · '}
                  {t('dashboard.directional.angle_steeper', {
                    count: stats.angle.steeperCount,
                  })}
                </p>
              )}

              {bar.parameter === 'berm' && (
                <div className="space-y-0.5 text-[11px] tabular-nums text-text-muted">
                  {stats.berm.validDesignCount > 0 && (
                    <p>
                      {stats.berm.meanDeficitVsDesign !== null && (
                        <>
                          {t('dashboard.directional.berm_deficit', {
                            value: formatLocaleSigned(stats.berm.meanDeficitVsDesign, lang, 2),
                          })}
                          {' · '}
                        </>
                      )}
                      {`${stats.berm.belowMinCount} < ${t('dashboard.context.berm_min')} · ${stats.berm.below5mCount} < 5 m`}
                    </p>
                  )}
                  {stats.berm.effectiveEvaluated > 0 && stats.berm.effectivePassPct !== null && (
                    <p>
                      {t('dashboard.directional.berm_effective', {
                        pct: formatLocaleNumber(stats.berm.effectivePassPct, lang, 1),
                        ok: stats.berm.effectivePassCount,
                        total: stats.berm.effectiveEvaluated,
                      })}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}

        <div data-parameter="crest" className="space-y-1 border-t border-border/60 pt-2.5">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="flex items-center gap-1.5 font-medium text-text-primary">
              <span
                aria-hidden="true"
                data-tone={crestTone}
                className="inline-block w-3 text-center font-semibold"
                style={{ color: statusToneColor(crestTone) }}
              >
                {TONE_ICON[crestTone]}
              </span>
              <span>{t('dashboard.parameter.crest')}</span>
            </span>
            <span
              className="font-medium tabular-nums"
              style={{ color: statusToneColor(crestTone) }}
            >
              {stats.crest.mean === null
                ? '—'
                : formatLocaleSigned(stats.crest.mean, lang, 1, ' m')}
            </span>
          </div>

          {stats.crest.count > 0 && stats.crest.mean !== null && (
            <p className="text-[11px] tabular-nums text-text-muted">
              {t('dashboard.directional.crest_loss', {
                value: formatLocaleSigned(stats.crest.mean, lang, 1),
                gt1: stats.crest.gt1mCount,
                gt3: stats.crest.gt3mCount,
              })}
            </p>
          )}
          <p className="text-[11px] text-text-muted">
            {t('dashboard.directional.crest_sign_note')}
          </p>
        </div>
      </div>

      <p className="text-xs text-text-muted">
        {t('dashboard.rail.denominator', { n: comparedCount })}
      </p>
    </section>
  );
}
