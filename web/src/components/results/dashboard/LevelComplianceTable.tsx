import { useTranslation } from 'react-i18next';
import { formatLocaleNumber, formatLocalePercent } from '../../../utils/format';
import { statusToneColor, type StatusTone } from '../SummaryControls';
import type { LevelComplianceRow } from './geotechSelectors';

export interface LevelComplianceTableProps {
  levels: readonly LevelComplianceRow[];
  activeLevels: readonly string[];
  onToggleLevel: (level: string) => void;
}

function metricTone(value: number | null): StatusTone {
  if (value === null) return 'muted';
  if (value >= 70) return 'ok';
  if (value >= 50) return 'warn';
  return 'nok';
}

export function LevelComplianceTable({
  levels,
  activeLevels,
  onToggleLevel,
}: LevelComplianceTableProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const activeSet = new Set(activeLevels);

  return (
    <section
      data-slot="level-compliance-table"
      className="min-w-0 space-y-2.5 border-t border-border py-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="ui-section-title">{t('dashboard.byLevel.title')}</h3>
      </div>

      {levels.length === 0 ? (
        <p className="text-xs text-text-muted">{t('dashboard.histogram.no_data')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-border text-text-muted">
                <th scope="col" className="py-1.5 pr-2 text-left font-medium">
                  {t('dashboard.byLevel.level')}
                </th>
                <th scope="col" className="py-1.5 px-1.5 text-right font-medium">
                  {t('dashboard.byLevel.compared')}
                </th>
                <th scope="col" className="py-1.5 px-1.5 text-right font-medium">
                  {t('dashboard.byLevel.not_built')}
                </th>
                <th scope="col" className="py-1.5 px-1.5 text-right font-medium">
                  {t('dashboard.byLevel.score')}
                </th>
                <th scope="col" className="py-1.5 px-1.5 text-right font-medium">
                  {t('dashboard.parameter.height')}
                </th>
                <th scope="col" className="py-1.5 px-1.5 text-right font-medium">
                  {t('dashboard.parameter.angle')}
                </th>
                <th scope="col" className="py-1.5 pl-1.5 text-right font-medium">
                  {t('dashboard.parameter.berm')}
                </th>
              </tr>
            </thead>
            <tbody>
              {levels.map((row) => {
                const isActive = activeSet.has(row.level);
                const levelLabel = row.level || '—';
                const smallSampleTitle = row.smallSample
                  ? t('dashboard.byLevel.small_sample', { n: row.compared })
                  : undefined;
                const scoreStyle = row.smallSample
                  ? undefined
                  : { color: statusToneColor(metricTone(row.meanScore)) };
                const pctCellClass = row.smallSample
                  ? 'py-1.5 px-1.5 text-right tabular-nums text-text-muted opacity-60'
                  : 'py-1.5 px-1.5 text-right tabular-nums';

                return (
                  <tr
                    key={row.level || '__empty__'}
                    data-level={row.level}
                    data-active={isActive ? 'true' : 'false'}
                    data-small-sample={row.smallSample ? 'true' : 'false'}
                    onClick={() => onToggleLevel(row.level)}
                    className={`cursor-pointer border-b border-border/70 transition-colors last:border-b-0 ${
                      isActive
                        ? 'bg-surface-muted font-medium ring-1 ring-inset ring-accent'
                        : 'hover:bg-surface-muted/50'
                    }`}
                  >
                    <th scope="row" className="py-1.5 pr-2 text-left font-medium text-text-primary">
                      <button
                        type="button"
                        aria-pressed={isActive}
                        aria-label={`${t('dashboard.byLevel.filter_by_level')}: ${levelLabel}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          onToggleLevel(row.level);
                        }}
                        className="inline-flex items-center gap-1.5 text-left tabular-nums hover:underline"
                      >
                        <span>{levelLabel}</span>
                        {row.smallSample && (
                          <span
                            data-slot="small-sample-badge"
                            title={smallSampleTitle}
                            aria-label={smallSampleTitle}
                            className="rounded border border-border bg-surface-muted px-1 py-0.5 text-[10px] font-normal leading-none tabular-nums text-text-muted"
                          >
                            {`n=${row.compared}`}
                          </span>
                        )}
                      </button>
                    </th>
                    <td className="py-1.5 px-1.5 text-right tabular-nums text-text-primary">
                      {row.compared}
                    </td>
                    <td className="py-1.5 px-1.5 text-right tabular-nums text-text-secondary">
                      {row.notBuilt}
                    </td>
                    <td
                      title={smallSampleTitle}
                      className={pctCellClass}
                      style={scoreStyle}
                    >
                      {formatLocaleNumber(row.meanScore, lang, 1)}
                    </td>
                    <td
                      title={smallSampleTitle}
                      className={pctCellClass}
                      style={
                        row.smallSample
                          ? undefined
                          : { color: statusToneColor(metricTone(row.heightPassPct)) }
                      }
                    >
                      {formatLocalePercent(row.heightPassPct, lang, 1)}
                    </td>
                    <td
                      title={smallSampleTitle}
                      className={pctCellClass}
                      style={
                        row.smallSample
                          ? undefined
                          : { color: statusToneColor(metricTone(row.anglePassPct)) }
                      }
                    >
                      {formatLocalePercent(row.anglePassPct, lang, 1)}
                    </td>
                    <td
                      title={smallSampleTitle}
                      className={
                        row.smallSample
                          ? 'py-1.5 pl-1.5 text-right tabular-nums text-text-muted opacity-60'
                          : 'py-1.5 pl-1.5 text-right tabular-nums'
                      }
                      style={
                        row.smallSample
                          ? undefined
                          : { color: statusToneColor(metricTone(row.bermPassPct)) }
                      }
                    >
                      {formatLocalePercent(row.bermPassPct, lang, 1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
