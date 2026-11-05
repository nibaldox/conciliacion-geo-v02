import { useTranslation } from 'react-i18next';
import type { BlastHoleColorLegend } from './blastHoleColors';

export const BLAST_HOLE_LEGEND_ENTRY_LIMIT = 100;

export interface BlastHoleColorLegendViewProps {
  legend: BlastHoleColorLegend;
  sourceLabel?: string;
  className?: string;
}

export function BlastHoleColorLegendView({ legend, sourceLabel, className }: BlastHoleColorLegendViewProps) {
  const { t } = useTranslation();
  const muted = { color: 'var(--color-text-muted)' };

  if (legend.kind === 'category') {
    const visibleEntries = legend.entries.slice(0, BLAST_HOLE_LEGEND_ENTRY_LIMIT);
    const distinctColors = new Set(legend.entries.map((entry) => entry.color)).size;
    const repeatedCount = legend.entries.length - distinctColors;
    return (
      <div className={className} aria-label={t('blast.colors.legendDiscrete', { defaultValue: 'Leyenda discreta' })}>
        <p className="mb-1 text-xs font-medium">{t('blast.colors.legendDiscrete', { defaultValue: 'Leyenda discreta' })}</p>
        <ul className="grid max-h-48 grid-cols-1 gap-x-3 gap-y-1 overflow-y-auto text-xs sm:grid-cols-2">
          {visibleEntries.map((entry) => <LegendEntry key={entry.label} label={entry.label} color={entry.color} />)}
          {legend.missing && <LegendEntry label={legend.missing.label} color={legend.missing.color} />}
        </ul>
        {legend.entries.length > BLAST_HOLE_LEGEND_ENTRY_LIMIT && <p className="mt-1 text-xs" style={muted}>
          {t('blast.colors.legendLimit', { defaultValue: 'Se muestran {{shown}} de {{total}} categorías', shown: BLAST_HOLE_LEGEND_ENTRY_LIMIT, total: legend.entries.length })}
        </p>}
        {repeatedCount > 0 && <p className="mt-1 text-xs" style={muted}>
          {t('blast.colors.legendRepeat', { defaultValue: 'Hay {{count}} categorías y {{colors}} colores: los colores se repiten; use la búsqueda para identificar una categoría.', count: legend.entries.length, colors: distinctColors })}
        </p>}
      </div>
    );
  }

  const hasNumeric = legend.min !== null && legend.max !== null;
  const belowCount = legend.belowCount ?? 0;
  const aboveCount = legend.aboveCount ?? 0;
  const missingCount = legend.missingCount ?? 0;
  const single = hasNumeric && legend.min === legend.max;
  const sourceText = sourceLabel ?? legend.sourceKey;

  return (
    <div className={className} aria-label={t('blast.colors.legendContinuous', { defaultValue: 'Leyenda continua' })}>
      <p className="mb-1 text-xs font-medium">{t('blast.colors.legendContinuous', { defaultValue: 'Leyenda continua' })} · {legend.palette}</p>
      <ul className="mb-1 flex flex-wrap gap-x-3 text-xs" style={muted}>
        {sourceText && <li>{t('blast.colors.legendSource', { defaultValue: 'Fuente: {{source}}', source: sourceText })}</li>}
        {legend.unit && <li>{t('blast.colors.legendUnit', { defaultValue: 'Unidad: {{unit}}', unit: legend.unit })}</li>}
      </ul>
      {hasNumeric ? (
        <>
          <div className="h-3 rounded" style={{ background: single
            ? legend.stops[Math.floor(legend.stops.length / 2)]?.color
            : `linear-gradient(to right, ${legend.stops.map((stop) => `${stop.color} ${stop.position * 100}%`).join(', ')})` }} />
          {single
            ? <p className="text-xs" style={muted}>{t('blast.colors.legendSingle', { defaultValue: 'Valor único: {{value}}', value: legend.min })}</p>
            : <div className="flex justify-between gap-2 text-xs" style={muted}>
                <span>{legend.min}</span>
                <span>{legend.max}</span>
              </div>}
        </>
      ) : (
        <p className="text-xs" style={muted}>{t('blast.colors.legendNoNumeric', { defaultValue: 'Sin valores numéricos' })}</p>
      )}
      {legend.observedMin != null && legend.observedMax != null && (
        <p className="mt-1 text-xs" style={muted}>
          {t('blast.colors.legendObserved', { defaultValue: 'Observado: {{min}} a {{max}}', min: legend.observedMin, max: legend.observedMax })}
        </p>
      )}
      {(belowCount > 0 || aboveCount > 0) && (
        <p className="mt-1 text-xs" style={muted}>
          {t('blast.colors.legendBelow', { defaultValue: 'Por debajo: {{count}}', count: belowCount })} · {t('blast.colors.legendAbove', { defaultValue: 'Por encima: {{count}}', count: aboveCount })}
          {' '}{t('blast.colors.legendSaturated', { defaultValue: 'Los valores fuera de rango usan el color extremo.' })}
        </p>
      )}
      <ul className="mt-1 text-xs">
        <LegendEntry label={legend.missing.label} color={legend.missing.color} />
        {missingCount > 0 && <li className="ml-5" style={muted}>{t('blast.colors.legendMissingCount', { defaultValue: '{{count}} pozos sin dato', count: missingCount })}</li>}
      </ul>
    </div>
  );
}

function LegendEntry({ label, color }: { label: string; color: string }) {
  return <li className="flex min-w-0 items-center gap-2">
    <span aria-hidden="true" className="h-3 w-3 shrink-0 rounded-full border border-black/20" style={{ backgroundColor: color }} />
    <span className="truncate">{label}</span>
  </li>;
}
