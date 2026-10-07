import { useTranslation } from 'react-i18next';
import {
  getHorizontalDeviationColor,
  HORIZONTAL_DEVIATION_CATEGORIES,
} from '../../utils/horizontalDeviation';

export interface HorizontalDeviationLegendProps {
  readonly compact?: boolean;
}

export function HorizontalDeviationLegend({ compact = false }: HorizontalDeviationLegendProps) {
  const { t } = useTranslation();

  return (
    <ul
      aria-label={t('horizontalDeviation.legend')}
      className={`grid grid-cols-2 ${compact ? 'gap-x-2 gap-y-1' : 'gap-x-4 gap-y-1.5'}`}
      data-slot="horizontal-deviation-legend"
    >
      {HORIZONTAL_DEVIATION_CATEGORIES.map((category) => (
        <li key={category} className="flex min-w-0 items-start gap-1.5 text-[10px] leading-tight">
          <span
            aria-hidden="true"
            className="h-2.5 w-2.5 shrink-0 rounded-sm"
            style={{ backgroundColor: getHorizontalDeviationColor(category) }}
          />
          <span className="min-w-0 whitespace-normal break-words" style={{ color: 'var(--color-text-secondary)' }}>
            {t(`horizontalDeviation.categories.${category}`)}
          </span>
        </li>
      ))}
    </ul>
  );
}
