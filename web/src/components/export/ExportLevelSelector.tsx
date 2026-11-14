import { useTranslation } from 'react-i18next';
import type { ExportLevel, ExportSectorLevels } from '../../api/hooks';

interface ExportLevelSelectorProps {
  sectors: ExportSectorLevels[];
  selection: Record<string, string[]>;
  warnings: string[];
  disabled?: boolean;
  onToggle: (sector: string, label: string) => void;
}

function formatElevation(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function ExportLevelSelector({ sectors, selection, warnings, disabled = false, onToggle }: ExportLevelSelectorProps) {
  const { t } = useTranslation();
  const showCaption = sectors.length > 1;

  const chipLabel = (level: ExportLevel): string => {
    const min = formatElevation(level.min_level);
    const max = formatElevation(level.max_level);
    return min === max
      ? t('export.levels_chip', { label: level.label, count: level.n_sections })
      : t('export.levels_chip_range', { label: level.label, min, max, count: level.n_sections });
  };

  return (
    <div data-testid="export-level-selector" className="flex flex-col gap-2">
      <div>
        <h4 id="export-levels-title" className="text-sm font-medium text-text-primary">
          {t('export.levels_title')}
        </h4>
        <p className="mt-0.5 text-xs text-text-muted">{t('export.levels_hint')}</p>
      </div>
      {sectors.map((entry) => {
        const caption = entry.sector === ''
          ? t('export.levels_no_sector')
          : t('export.levels_sector', { sector: entry.sector });
        const selected = selection[entry.sector] ?? [];
        return (
          <fieldset
            key={entry.sector}
            data-testid="export-level-sector"
            aria-label={showCaption ? undefined : t('export.levels_title')}
            disabled={disabled}
            className="flex min-w-0 flex-wrap items-center gap-2"
          >
            {showCaption && (
              <legend data-testid="export-level-sector-caption" className="mb-1 text-xs text-text-muted">
                {caption}
              </legend>
            )}
            {entry.levels.map((level) => {
              const checked = selected.includes(level.label);
              return (
                <label
                  key={level.label}
                  className="ui-chip cursor-pointer"
                  data-tone={checked ? 'accent' : undefined}
                >
                  <input
                    type="checkbox"
                    className="accent-[var(--color-accent)]"
                    checked={checked}
                    onChange={() => onToggle(entry.sector, level.label)}
                  />
                  <span className="tabular-nums">{chipLabel(level)}</span>
                </label>
              );
            })}
          </fieldset>
        );
      })}
      {warnings.length > 0 && (
        <ul data-testid="export-level-warnings" role="status" className="flex flex-col gap-0.5 text-xs text-[var(--status-warn-text)]">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
