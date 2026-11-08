import { useTranslation } from 'react-i18next';
import type { ComparisonResultDto } from './ProfileView/domain';
import {
  formatFloor,
  formatProposalNumber,
  formatProposalPair,
  hasProposalData,
  toProposalRows,
  type ProposalLang,
} from './ProfileView/domain';

export interface ProposalTableProps {
  readonly rows: readonly ComparisonResultDto[];
  readonly showSection?: boolean;
  readonly floorTolerance?: number;
}

function statusColorVar(status: string | null | undefined): string | undefined {
  const s = (status ?? '').toUpperCase();
  if (s === 'CUMPLE') return 'var(--status-ok-text)';
  if (s.includes('FUERA')) return 'var(--status-warn-text)';
  if (s.includes('NO CUMPLE')) return 'var(--status-nok-text)';
  return undefined;
}

function stateTone(state: string): string | undefined {
  if (state === 'not_excavated' || state === 'section_truncated' || state === 'unmeasured') {
    return 'var(--status-warn-text)';
  }
  if (state === 'split_bench' || state === 'split_fragment') return 'var(--status-info-text, var(--color-accent-bright))';
  return undefined;
}

const SOURCE_LABEL_KEYS: Record<string, string> = {
  current: 'proposal.sourceCurrent',
  guided: 'proposal.sourceGuided',
  mixed: 'proposal.sourceMixed',
};

export function ProposalTable({ rows, showSection = false, floorTolerance = 0.5 }: ProposalTableProps) {
  const { t, i18n } = useTranslation();
  const lang: ProposalLang = i18n.resolvedLanguage?.toLowerCase().startsWith('en') ? 'en' : 'es';
  const locale = lang === 'en' ? 'en-US' : 'es-AR';
  if (!hasProposalData(rows)) {
    return (
      <p role="status" className="m-0 text-sm text-text-secondary">
        {t('proposal.notComputedNotice')}
      </p>
    );
  }
  const proposalRows = toProposalRows(rows);
  const cellClass = 'whitespace-nowrap px-2.5 py-1.5 text-right tabular-nums';

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs" data-slot="proposal-table">
        <thead>
          <tr className="border-b border-border text-text-muted">
            {showSection && (
              <th scope="col" className="px-2.5 py-2 text-left font-medium">
                {t('proposal.columnSection')}
              </th>
            )}
            <th scope="col" className="px-2.5 py-2 text-left font-medium">{t('proposal.columnBench')}</th>
            <th scope="col" className="px-2.5 py-2 text-left font-medium">{t('proposal.columnState')}</th>
            <th scope="col" className="px-2.5 py-2 text-left font-medium">{t('proposal.columnSource')}</th>
            <th scope="col" className={cellClass.replace('text-right', 'text-right font-medium')}>{t('proposal.columnHeight')}</th>
            <th scope="col" className="px-2.5 py-2 text-right font-medium">{t('proposal.columnAngle')}</th>
            <th scope="col" className="px-2.5 py-2 text-right font-medium">{t('proposal.columnDeltaCrest')}</th>
            <th scope="col" className="px-2.5 py-2 text-right font-medium">{t('proposal.columnDeltaToe')}</th>
            <th scope="col" className="px-2.5 py-2 text-right font-medium">{t('proposal.columnBerm')}</th>
            <th scope="col" className="px-2.5 py-2 text-right font-medium">{t('proposal.columnScore')}</th>
            <th scope="col" className="px-2.5 py-2 text-right font-medium">
              {t('proposal.columnFloor', { tol: formatProposalNumber(floorTolerance, lang) })}
            </th>
          </tr>
        </thead>
        <tbody>
          {proposalRows.map((row) => (
            <tr key={row.key} className="border-b border-border last:border-b-0">
              {showSection && <td className="whitespace-nowrap px-2.5 py-1.5 text-text-secondary">{row.section || '—'}</td>}
              <td className="whitespace-nowrap px-2.5 py-1.5 font-medium text-text-primary">
                {row.isExtra
                  ? t('profileView.table.additional_topo', { number: row.benchNumTopo ?? '—' })
                  : row.benchLabel}
              </td>
              <td className="whitespace-nowrap px-2.5 py-1.5 text-text-secondary">
                <span style={stateTone(row.state) ? { color: stateTone(row.state) } : undefined}>
                  {t(`proposal.state.${row.state}`)}
                </span>
                {row.state === 'not_excavated' && row.debtAreaM2 != null ? (
                  <span className="text-text-muted"> · {t('proposal.stateDebt', { area: row.debtAreaM2.toLocaleString(locale) })}</span>
                ) : null}
                {row.error ? <span className="text-text-muted" title={row.error}> ⚠</span> : null}
              </td>
              <td className="whitespace-nowrap px-2.5 py-1.5 text-text-secondary">
                {row.source && SOURCE_LABEL_KEYS[row.source]
                  ? t(SOURCE_LABEL_KEYS[row.source])
                  : t('proposal.sourceNone')}
              </td>
              <td className={cellClass}>{formatProposalPair(row.height, lang)}</td>
              <td className={cellClass}>{formatProposalPair(row.angle, lang)}</td>
              <td className={cellClass}>{formatProposalPair(row.deltaCrest, lang)}</td>
              <td className={cellClass}>{formatProposalPair(row.deltaToe, lang)}</td>
              <td className={cellClass}>{formatProposalPair(row.berm, lang)}</td>
              <td className={cellClass}>{formatProposalPair(row.score, lang)}</td>
              <td className={cellClass}>
                <span
                  style={
                    row.floorStatus && row.floorStatus !== '-'
                      ? { color: statusColorVar(row.floorStatus) }
                      : undefined
                  }
                >
                  {row.floorStatus === '-'
                    ? t('proposal.floorUnmeasured')
                    : formatFloor(row.floorOffsetM, row.floorStatus, lang)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="m-0 pt-2 text-xs text-text-muted">{t('proposal.officialUnchanged')}</p>
      <p className="m-0 pt-1 text-xs text-text-muted">{t('proposal.sourceLegend')}</p>
    </div>
  );
}
