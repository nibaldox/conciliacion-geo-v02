import { useTranslation } from 'react-i18next';
import { formatLocaleNumber, formatLocaleSigned } from '../../../utils/format';
import { statusToneColor } from '../SummaryControls';
import type { PriorityReasonCode, PriorityReviewItem } from './geotechSelectors';

export interface PriorityReviewListProps {
  items: readonly PriorityReviewItem[];
  onOpenBench: (item: PriorityReviewItem) => void;
}

function reasonTone(reason: PriorityReasonCode, item: PriorityReviewItem): 'nok' | 'warn' {
  if (reason === 'effective_berm' || reason === 'berm_below_min') return 'nok';
  if (reason === 'low_score' && item.score !== null && item.score < 50) return 'nok';
  return 'warn';
}

function formatReasonDetail(
  reason: PriorityReasonCode,
  item: PriorityReviewItem,
  lang: string,
): string {
  switch (reason) {
    case 'effective_berm':
      return item.effectiveBerm !== null
        ? ` (${formatLocaleNumber(item.effectiveBerm, lang, 1)} m)`
        : '';
    case 'berm_below_min':
      if (item.bermReal !== null && item.bermDesign !== null) {
        return ` (${formatLocaleNumber(item.bermReal, lang, 1)} / ${formatLocaleNumber(item.bermDesign, lang, 1)} m)`;
      }
      if (item.bermReal !== null) {
        return ` (${formatLocaleNumber(item.bermReal, lang, 1)} m)`;
      }
      return '';
    case 'crest_loss':
      return item.deltaCrest !== null
        ? ` (Δ ${formatLocaleSigned(item.deltaCrest, lang, 1, ' m')})`
        : '';
    case 'low_score':
      return item.score !== null ? ` (${formatLocaleNumber(item.score, lang, 0)}/100)` : '';
  }
}

export function PriorityReviewList({ items, onOpenBench }: PriorityReviewListProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  return (
    <section
      data-slot="priority-review-list"
      className="min-w-0 space-y-2.5 border-t border-border py-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="ui-section-title">{t('dashboard.priority.title')}</h3>
      </div>

      {items.length === 0 ? (
        <p
          data-slot="priority-review-empty"
          className="flex items-center gap-1.5 rounded border border-border bg-surface-muted/40 px-3 py-2 text-xs text-text-muted"
        >
          <span aria-hidden="true" style={{ color: statusToneColor('ok') }}>
            ✓
          </span>
          <span>{t('dashboard.priority.empty')}</span>
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-border text-text-muted">
                <th scope="col" className="py-1.5 pr-2 text-left font-medium">
                  {t('dashboard.priority.section')}
                </th>
                <th scope="col" className="py-1.5 px-1.5 text-left font-medium">
                  {t('dashboard.priority.bench')}
                </th>
                <th scope="col" className="py-1.5 px-1.5 text-right font-medium">
                  {t('dashboard.priority.level')}
                </th>
                <th scope="col" className="py-1.5 px-2 text-left font-medium">
                  {t('dashboard.priority.reason')}
                </th>
                <th scope="col" className="py-1.5 pl-2 text-right font-medium">
                  <span className="sr-only">{t('dashboard.priority.open')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={`${item.section}-${item.benchNum}-${item.level}`}
                  data-section={item.section}
                  data-bench={item.benchNum}
                  className="border-b border-border/70 align-top last:border-b-0"
                >
                  <td className="py-2 pr-2 font-medium text-text-primary whitespace-nowrap">
                    {item.section}
                  </td>
                  <td className="py-2 px-1.5 tabular-nums text-text-primary whitespace-nowrap">
                    {`B${item.benchNum}`}
                  </td>
                  <td className="py-2 px-1.5 text-right tabular-nums text-text-secondary whitespace-nowrap">
                    {item.level || '—'}
                  </td>
                  <td className="py-2 px-2">
                    <div className="flex flex-wrap gap-1">
                      {item.reasons.map((reason) => (
                        <span
                          key={reason}
                          data-reason={reason}
                          data-tone={reasonTone(reason, item)}
                          className="ui-chip text-[11px] leading-tight tabular-nums"
                        >
                          {`${t(`dashboard.priority.reason_${reason}`)}${formatReasonDetail(reason, item, lang)}`}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-2 pl-2 text-right whitespace-nowrap">
                    <button
                      type="button"
                      disabled={item.sectionId === null}
                      aria-label={t('dashboard.priority.open_profile_aria', {
                        section: item.section,
                      })}
                      onClick={() => onOpenBench(item)}
                      className="rounded border border-border px-2 py-0.5 text-xs font-medium text-accent transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:text-text-muted disabled:opacity-50"
                    >
                      {`→ ${t('dashboard.rail.open_profile')}`}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
