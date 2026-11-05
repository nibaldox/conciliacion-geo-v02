import { useTranslation } from 'react-i18next';
import {
  useDesignAchievement,
  type DesignAchievementResponse,
  type DesignAchievementSummary,
} from '../../api/designAchievement';
import { EMPTY_RESULT_FILTERS, type ResultFilterState } from './resultFilters.utils';

const TEXT = {
  title: { es: 'Logro de diseño', en: 'Design achievement' },
  loading: { es: 'Cargando logro de diseño…', en: 'Loading design achievement…' },
  loadError: { es: 'No se pudo cargar el logro de diseño', en: 'Failed to load design achievement' },
  retry: { es: 'Reintentar', en: 'Retry' },
  demoUnavailable: {
    es: 'Logro de diseño no disponible en la demo por ahora.',
    en: 'Design achievement is not available in the demo yet.',
  },
  noData: { es: 'Sin datos', en: 'No data' },
  rowsTotal: { es: 'filas', en: 'rows' },
  globalScore: { es: 'Puntaje de Logro Diseño', en: 'Design achievement score' },
  scoreScale: { es: 'escala 0–100', en: 'scale 0–100' },
  weights: {
    es: 'Pesos de Logro Diseño: cresta 40 % · pata 30 % · berma 30 %, con crédito parcial por elemento.',
    en: 'Design achievement weights: crest 40 % · toe 30 % · berm 30 %, with partial credit per element.',
  },
  weighingNote: {
    es: 'Nota: en la fila evaluable los elementos faltantes aportan 0 al puntaje global; los porcentajes y medias de cada elemento excluyen las ausencias de su propio denominador. Una fila parcial no equivale a una medición completa.',
    en: 'Note: on an evaluable row missing elements contribute 0 to the global score; each element’s percentages and means exclude absences from its own denominator. A partial row is not a complete measurement.',
  },
  evaluableCounts: { es: 'evaluables', en: 'evaluable' },
  crest: { es: 'Cresta', en: 'Crest' },
  toe: { es: 'Pata', en: 'Toe' },
  berm: { es: 'Berma', en: 'Berm' },
  meanCorrection: { es: 'Media de corrección', en: 'Mean correction' },
  sector: { es: 'Sector', en: 'Sector' },
  noSector: { es: 'Sin sector', en: 'No sector' },
  nEvaluable: { es: 'n evaluables', en: 'n evaluable' },
  achievement: { es: 'Logro (%)', en: 'Achievement (%)' },
  tolerances: { es: 'Tolerancia', en: 'Tolerance' },
  tolSourceCoreDefault: { es: 'predeterminada', en: 'default' },
  tolSourceSession: { es: 'sesión', en: 'session' },
  provenanceSource: { es: 'Fuente', en: 'Source' },
  statusComputed: { es: 'calculado', en: 'computed' },
  statusNoData: { es: 'sin datos', en: 'no data' },
} as const;

const WARNING_TEXT: Record<string, { es: string; en: string }> = {
  no_results: {
    es: 'No hay resultados procesados en esta sesión.',
    en: 'There are no processed results in this session.',
  },
  all_rows_filtered_out: {
    es: 'Todas las filas quedaron fuera por los filtros activos.',
    en: 'All rows were excluded by the active filters.',
  },
  no_evaluable_rows: {
    es: 'Ninguna fila tiene las mediciones suficientes para evaluar el logro.',
    en: 'No row has enough measurements to evaluate the achievement.',
  },
  session_tolerance_invalid_using_core_default: {
    es: 'La tolerancia de sesión no es válida; se usó la tolerancia predeterminada.',
    en: 'The session tolerance is invalid; the default tolerance was used.',
  },
};

type TextKey = keyof typeof TEXT;

const ELEMENTS = ['crest', 'toe', 'berm'] as const;
type ElementKey = (typeof ELEMENTS)[number];

function makeFmt(lang: 'es' | 'en', signed: boolean): Intl.NumberFormat {
  return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-AR', {
    maximumFractionDigits: 2,
    ...(signed ? { signDisplay: 'exceptZero' as const } : {}),
  });
}

function fmtNumber(value: number, lang: 'es' | 'en'): string {
  return makeFmt(lang, false).format(value);
}

function fmtSignedMeters(value: number | null, unit: string, lang: 'es' | 'en'): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${makeFmt(lang, true).format(value)} ${unit}`;
}

function fmtPercent(value: number | null, lang: 'es' | 'en'): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${fmtNumber(value, lang)} %`;
}

function elementCard(
  key: ElementKey,
  summary: DesignAchievementSummary,
  tx: (k: TextKey) => string,
  unit: string,
  lang: 'es' | 'en',
) {
  const pct = key === 'crest' ? summary.crest_pct : key === 'toe' ? summary.toe_pct : summary.berm_pct;
  const cumple = key === 'crest' ? summary.crest_cumple : key === 'toe' ? summary.toe_cumple : summary.berm_cumple;
  const denom = key === 'crest' ? summary.crest_denom : key === 'toe' ? summary.toe_denom : summary.berm_denom;
  const delta = key === 'crest' ? summary.delta_crest_mean : key === 'toe' ? summary.delta_toe_mean : null;
  return (
    <div key={key} className="min-w-0 space-y-0.5 border-l border-border pl-3">
      <h4 className="m-0 text-xs font-normal text-text-muted">{tx(key)}</h4>
      <p className="m-0 text-xl font-semibold tabular-nums text-text-primary">{fmtPercent(pct, lang)}</p>
      {pct == null ? <p className="m-0 text-xs text-text-muted">{tx('noData')}</p> : null}
      <p className="m-0 text-xs tabular-nums text-text-muted">
        {cumple} / {denom}
      </p>
      {delta != null ? (
        <p className="m-0 text-xs tabular-nums text-text-muted">
          {tx('meanCorrection')}: {fmtSignedMeters(delta, unit, lang)}
        </p>
      ) : null}
    </div>
  );
}

export function DesignAchievementPanel({ filters }: { filters?: ResultFilterState }) {
  const activeFilters = filters ?? EMPTY_RESULT_FILTERS;
  const { data, isPending, isFetching, isError, error, isDemo, refetch } =
    useDesignAchievement(activeFilters);
  const { t, i18n } = useTranslation();
  const lang: 'es' | 'en' = i18n.resolvedLanguage?.toLowerCase().startsWith('en') ? 'en' : 'es';
  const tx = (key: TextKey) => t(`designAchievement.${key}`, { defaultValue: TEXT[key][lang] });
  const tw = (code: string) =>
    t(`designAchievement.warning_${code}`, {
      defaultValue: WARNING_TEXT[code]?.[lang] ?? code,
    });

  if (isDemo) {
    return (
      <section role="status" className="rounded-lg border border-border p-4 text-sm text-text-muted">
        {tx('demoUnavailable')}
      </section>
    );
  }

  const unit = data?.units.corrections ?? 'm';
  const provenance = data?.metadata;
  const isNoData = data != null && (data.metadata?.status ?? 'computed') === 'no_data';

  return (
    <section
      data-slot="design-achievement"
      aria-labelledby="design-achievement-title"
      aria-busy={isPending || (isFetching && !data) || undefined}
      className="min-w-0 space-y-4 rounded-lg border border-border bg-surface-raised p-4 text-sm"
    >
      <h3 id="design-achievement-title" className="ui-section-title m-0">
        {tx('title')}
      </h3>

      {isPending ? <p role="status" className="m-0 text-text-muted">{tx('loading')}</p> : null}

      {!isPending && isError ? (
        <div role="alert" className="space-y-2">
          <p className="m-0" style={{ color: 'var(--status-nok-text)' }}>
            {tx('loadError')}
            {error instanceof Error && error.message ? `: ${error.message}` : ''}
          </p>
          <button
            type="button"
            onClick={refetch}
            className="rounded-md border border-border px-2.5 py-1 text-xs text-text-primary hover:bg-surface-muted"
          >
            {tx('retry')}
          </button>
        </div>
      ) : null}

      {!isPending && !isError && data && isNoData ? (
        <div role="status" className="space-y-1">
          <p className="m-0 text-text-secondary">{tx('noData')}</p>
          <p className="m-0 text-xs tabular-nums text-text-muted">
            {fmtNumber(data.n_total_rows, lang)} {tx('rowsTotal')} ·{' '}
            {data.summary.n_evaluable} / {data.summary.n_total} {tx('evaluableCounts')}
          </p>
        </div>
      ) : null}

      {!isPending && !isError && data && !isNoData ? (
        <>
          <div className="flex flex-wrap items-end gap-x-10 gap-y-4">
            <dl className="m-0">
              <div className="flex items-baseline gap-2">
                <dt className="order-last text-xs text-text-muted">{tx('globalScore')}</dt>
                <dd className="m-0 text-3xl font-semibold leading-none tabular-nums text-text-primary">
                  {data.summary.global_score == null
                    ? '—'
                    : fmtNumber(data.summary.global_score, lang)}{' '}
                  <small className="text-xs font-normal text-text-muted">{tx('scoreScale')}</small>
                </dd>
                {data.summary.global_score == null ? (
                  <dd className="m-0 text-xs text-text-muted">{tx('noData')}</dd>
                ) : null}
                <dd className="m-0 text-xs tabular-nums text-text-muted">
                  {data.summary.n_evaluable} / {data.summary.n_total} {tx('evaluableCounts')}
                </dd>
              </div>
            </dl>
            <div className="grid min-w-0 flex-1 grid-cols-[repeat(auto-fit,minmax(120px,1fr))] gap-4">
              {ELEMENTS.map((el) => elementCard(el, data.summary, tx, unit, lang))}
            </div>
          </div>

          <details className="text-xs text-text-muted">
            <summary className="cursor-pointer select-none text-text-secondary hover:text-text-primary">
              {t('dashboard.kpi.how_calculated', { defaultValue: '¿Cómo se calcula?' })}
            </summary>
            <div className="mt-2 space-y-1">
              <p className="m-0">{tx('weights')}</p>
              <p className="m-0">{tx('weighingNote')}</p>
            </div>
          </details>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <caption className="pb-2 text-left text-xs text-text-muted" style={{ captionSide: 'top' }}>
                {tx('tolerances')}{' '}
                {data.tolerances.neg === data.tolerances.pos
                  ? `±${fmtNumber(Math.abs(data.tolerances.pos), lang)} ${unit}`
                  : `−${fmtNumber(Math.abs(data.tolerances.neg), lang)} / +${fmtNumber(
                      data.tolerances.pos,
                      lang,
                    )} ${unit}`}
                {' · '}
                {tx(
                  data.tolerances_source === 'session' ? 'tolSourceSession' : 'tolSourceCoreDefault',
                )}
              </caption>
              <thead>
                <tr className="border-b border-border text-xs text-text-muted">
                  <th scope="col" className="py-2 pr-4 text-left font-medium">
                    {tx('sector')}
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    {tx('nEvaluable')}
                  </th>
                  <th scope="col" className="py-2 text-right font-medium">
                    {tx('achievement')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.sectors.map((row) => (
                  <tr key={row.sector} className="border-b border-border last:border-b-0">
                    <th scope="row" className="py-2 pr-4 text-left font-medium text-text-primary">
                      {row.sector === '' ? tx('noSector') : row.sector}
                    </th>
                    <td className="py-2 pr-4 text-right tabular-nums text-text-secondary">{row.n_evaluable}</td>
                    <td className="py-2 text-right tabular-nums text-text-secondary">
                      {row.global_score == null ? '—' : fmtNumber(row.global_score, lang)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {data && data.warnings.length > 0 ? (
        <ul className="m-0 space-y-0.5 pl-5 text-xs text-text-secondary">
          {data.warnings.map((warning, i) => (
            <li key={i}>{tw(warning)}</li>
          ))}
        </ul>
      ) : null}

      {data && provenance ? (
        <p className="m-0 text-xs text-text-muted [overflow-wrap:anywhere]">
          {tx('provenanceSource')}: {translateProvenanceSource(provenance.source, lang)} ·{' '}
          {provenance.status === 'no_data' ? tx('statusNoData') : tx('statusComputed')}
        </p>
      ) : null}
    </section>
  );
}

function translateProvenanceSource(source: string, lang: 'es' | 'en'): string {
  if (source === 'persisted_comparisons') {
    return lang === 'en' ? 'persisted comparisons' : 'comparaciones procesadas';
  }
  return source;
}

export type { DesignAchievementResponse, DesignAchievementSummary };
