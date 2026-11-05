import { useMemo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Tooltip } from '../ui/Tooltip';
import { useTheme } from '../../stores/theme';
import { readThemeColor } from '../../utils/theme';

export function BlastInfoTip({ children, side = 'bottom' }: { children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  const { t } = useTranslation();
  return (
    <Tooltip content={children} side={side}>
      <button
        type="button"
        aria-label={t('blast.more_info', { defaultValue: 'Más información' })}
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border text-[10px] leading-none text-text-muted hover:text-text-primary"
      >
        i
      </button>
    </Tooltip>
  );
}

export function BlastSectionHeader({
  title,
  info,
  aside,
  as: Heading = 'h3',
}: {
  title: ReactNode;
  info?: ReactNode;
  aside?: ReactNode;
  as?: 'h2' | 'h3' | 'h4';
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
      <div className="flex min-w-0 items-center gap-2">
        <Heading className="ui-section-title">{title}</Heading>
        {info && <BlastInfoTip>{info}</BlastInfoTip>}
      </div>
      {aside}
    </div>
  );
}

export interface BlastChartColors {
  primary: string;
  secondary: string;
  fit: string;
  outline: string;
  muted: string;
}

export function readBlastChartColors(): BlastChartColors {
  return {
    primary: readThemeColor('--color-mine-blue', '#4da5f5'),
    secondary: readThemeColor('--color-mine-yellow', '#e68f19'),
    fit: readThemeColor('--color-text-secondary', '#b3bcc8'),
    outline: readThemeColor('--color-surface', '#07090c'),
    muted: readThemeColor('--color-text-muted', '#8f9aa8'),
  };
}

export function useBlastChartColors(): BlastChartColors {
  const isDark = useTheme((s) => s.isDark);
  return useMemo(() => readBlastChartColors(), [isDark]);
}

export const BLAST_PLOT_LAYOUT_BASE = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { color: 'var(--color-text-secondary)', size: 11 },
  legend: { orientation: 'h', y: -0.22, font: { size: 10 } },
} as const;

export const BLAST_PLOT_AXIS_BASE = {
  gridcolor: 'var(--color-border)',
  linecolor: 'var(--color-border)',
  zeroline: false,
} as const;
