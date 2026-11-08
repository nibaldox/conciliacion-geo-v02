import { useTranslation } from 'react-i18next';
import type { ComparisonResultDto } from '../domain/types';
import { hasProposalData } from '../domain';
import { ProposalTable } from '../../ProposalTable';

export interface ProposalPanelProps {
  readonly comparisons: readonly ComparisonResultDto[];
  readonly floorTolerance?: number;
  readonly chartLayerAvailable?: boolean;
}

export function ProposalPanel({
  comparisons,
  floorTolerance = 0.5,
  chartLayerAvailable = false,
}: ProposalPanelProps) {
  const { t } = useTranslation();
  if (comparisons.length === 0) return null;

  return (
    <section
      data-slot="proposal-panel"
      aria-labelledby="proposal-panel-title"
      className="border-t border-border px-4 py-3"
    >
      <details>
        <summary
          id="proposal-panel-title"
          className="cursor-pointer select-none text-sm font-medium text-text-primary hover:text-accent-bright"
        >
          🧪 {t('proposal.title')}
        </summary>
        <div className="pt-3">
          {hasProposalData(comparisons) ? (
            <ProposalTable rows={comparisons} floorTolerance={floorTolerance} />
          ) : (
            <p role="status" className="m-0 text-sm text-text-secondary">
              {t('proposal.notComputedNotice')}
            </p>
          )}
          {!chartLayerAvailable ? (
            <p className="m-0 pt-2 text-xs text-text-muted">{t('proposal.chartLayerUnavailable')}</p>
          ) : null}
        </div>
      </details>
    </section>
  );
}
