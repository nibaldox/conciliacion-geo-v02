import { useTranslation } from 'react-i18next';
import {
  useDesignAchievement,
  type DesignAchievementResponse,
  type DesignAchievementSummary,
} from '../../api/designAchievement';
import { EMPTY_RESULT_FILTERS, type ResultFilterState } from './resultFilters';

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
    <div
      key={key}
      style={{
        border: '1px solid var(--color-border, currentColor)',
        borderRadius: 6,
        padding: 'var(--space-2, 0.5rem)',
        background: 'var(--color-surface-muted, transparent)',
        minWidth: 0,
      }}
    >
      <h4 style={{ margin: '0 0 0.25rem', fontSize: '0.9rem' }}>{tx(key)}</h4>
      <p style={{ margin: 0, fontSize: '1.35rem', fontWeight: 600 }}>{fmtPercent(pct, lang)}</p>
      {pct == null ? (
        <p style={{ margin: 0, color: 'var(--color-text-dim, inherit)' }}>
          <small>{tx('noData')}</small>
        </p>
      ) : null}
      <p style={{ margin: '0.25rem 0 0', color: 'var(--color-text-dim, inherit)' }}>
        <small>
          {cumple} / {denom}
        </small>
      </p>
      {delta != null ? (
        <p style={{ margin: '0.25rem 0 0', color: 'var(--color-text-dim, inherit)' }}>
          <small>
            {tx('meanCorrection')}: {fmtSignedMeters(delta, unit, lang)}
          </small>
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
      <section role="status" style={{ padding: 'var(--space-2, 0.5rem)' }}>
        {tx('demoUnavailable')}
      </section>
    );
  }

  const unit = data?.units.corrections ?? 'm';
  const provenance = data?.metadata;
  const isNoData = data != null && (data.metadata?.status ?? 'computed') === 'no_data';

  return (
    <section
      aria-labelledby="design-achievement-title"
      aria-busy={isPending || (isFetching && !data) || undefined}
      style={{ padding: 'var(--space-2, 0.5rem)', minWidth: 0 }}
    >
      <h3 id="design-achievement-title" style={{ margin: '0 0 0.5rem' }}>
        {tx('title')}
      </h3>

      {isPending ? <p role="status">{tx('loading')}</p> : null}

      {!isPending && isError ? (
        <div role="alert" style={{ padding: 'var(--space-2, 0.5rem)' }}>
          <p style={{ margin: '0 0 0.5rem' }}>
            {tx('loadError')}
            {error instanceof Error && error.message ? `: ${error.message}` : ''}
          </p>
          <button type="button" onClick={refetch}>
            {tx('retry')}
          </button>
        </div>
      ) : null}

      {!isPending && !isError && data && isNoData ? (
        <div role="status" style={{ margin: '0 0 0.5rem' }}>
          <p style={{ margin: 0 }}>{tx('noData')}</p>
          <p style={{ margin: '0.25rem 0 0' }}>
            <small>
              {fmtNumber(data.n_total_rows, lang)} {tx('rowsTotal')} ·{' '}
              {data.summary.n_evaluable} / {data.summary.n_total} {tx('evaluableCounts')}
            </small>
          </p>
        </div>
      ) : null}

      {!isPending && !isError && data && !isNoData ? (
        <>
          <dl style={{ margin: '0 0 0.5rem' }}>
            <div style={{ margin: 0 }}>
              <dt style={{ fontWeight: 600 }}>{tx('globalScore')}</dt>
              <dd style={{ margin: 0 }}>
                {data.summary.global_score == null
                  ? '—'
                  : fmtNumber(data.summary.global_score, lang)}{' '}
                <small style={{ color: 'var(--color-text-dim, inherit)' }}>{tx('scoreScale')}</small>
              </dd>
              {data.summary.global_score == null ? (
                <dd style={{ margin: 0, color: 'var(--color-text-dim, inherit)' }}>
                  <small>{tx('noData')}</small>
                </dd>
              ) : null}
              <dd style={{ margin: 0 }}>
                <small>
                  {data.summary.n_evaluable} / {data.summary.n_total} {tx('evaluableCounts')}
                </small>
              </dd>
            </div>
          </dl>
          <p style={{ margin: '0 0 0.5rem' }}>
            <small>{tx('weights')}</small>
          </p>
          <p style={{ margin: '0 0 0.5rem', color: 'var(--color-text-dim, inherit)' }}>
            <small>{tx('weighingNote')}</small>
          </p>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 'var(--space-2, 0.5rem)',
              margin: '0 0 0.75rem',
            }}
          >
            {ELEMENTS.map((el) => elementCard(el, data.summary, tx, unit, lang))}
          </div>

          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <caption
              style={{
                textAlign: 'left',
                captionSide: 'top',
                color: 'var(--color-text-dim, inherit)',
                padding: '0.25rem 0',
              }}
            >
              <small>
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
              </small>
            </caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  {tx('sector')}
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  {tx('nEvaluable')}
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  {tx('achievement')}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.sectors.map((row) => (
                <tr key={row.sector}>
                  <th scope="row" style={{ textAlign: 'left', fontWeight: 500 }}>
                    {row.sector === '' ? tx('noSector') : row.sector}
                  </th>
                  <td style={{ textAlign: 'right' }}>{row.n_evaluable}</td>
                  <td style={{ textAlign: 'right' }}>
                    {row.global_score == null ? '—' : fmtNumber(row.global_score, lang)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {data && data.warnings.length > 0 ? (
        <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem' }}>
          {data.warnings.map((warning, i) => (
            <li key={i}>
              <small>{tw(warning)}</small>
            </li>
          ))}
        </ul>
      ) : null}

      {data && provenance ? (
        <p
          style={{
            margin: '0.5rem 0 0',
            color: 'var(--color-text-dim, inherit)',
            overflowWrap: 'anywhere',
          }}
        >
          <small>
            {tx('provenanceSource')}: {translateProvenanceSource(provenance.source, lang)} ·{' '}
            {provenance.status === 'no_data' ? tx('statusNoData') : tx('statusComputed')}
          </small>
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
