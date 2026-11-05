import { describe, expect, it } from 'vitest';

import en from './en.json';
import es from './es.json';

type Entry = { es: string; en: string };

const BLOCK1: Record<string, Entry> = {
  'sidebar.tol_crest_toe': { es: "Desviación cresta-pata (m)", en: "Crest-toe deviation (m)" },
  'results.filters.level': { es: "Cota", en: "Level" },
  'results.filters.no_sector': { es: "(sin sector)", en: "(no sector)" },
  'table.col_sector': { es: "Sector", en: "Sector" },
  'table.col_level': { es: "Nivel", en: "Level" },
  'table.col_delta_crest': { es: "Δ Cresta", en: "Δ Crest" },
  'table.col_delta_toe': { es: "Δ Pata", en: "Δ Toe" },
  'table.col_spill': { es: "B. Derrame (m)", en: "Spill width (m)" },
  'table.col_berm_effective': { es: 'B. Efectiva (m)', en: 'Effective berm width (m)' },
  'dashboard.section.deviation_toe': { es: 'Desviación de Pata (m)', en: 'Toe Deviation (m)' },
  'dashboard.section.deviation_berm': { es: 'Ancho de berma (m)', en: 'Berm Width (m)' },
  'dashboard.plot.axis.delta_toe': { es: 'Δ Pata (m)', en: 'Δ Toe (m)' },
  'dashboard.plot.axis.berm_width': { es: 'Ancho de berma real (m)', en: 'Actual berm width (m)' },
  'dashboard.kpi.classification_note': {
    es: 'La clasificación del perfil sigue el peor score de sus bancos (≥70 cumple). Es independiente del Puntaje de Logro Diseño; las métricas individuales se evalúan por tolerancias.',
    en: 'Profile classification follows the worst bench score (≥70 passes). It is independent of design achievement; individual metrics are evaluated against tolerances.',
  },
  'table.order_label': { es: "Orden", en: "Order" },
  'table.order_by_section': { es: "Por Sección", en: "By section" },
  'table.order_by_level': { es: "Por Nivel", en: "By level" },
  'designAchievement.title': { es: "Logro de diseño", en: "Design achievement" },
  'designAchievement.loading': { es: "Cargando logro de diseño…", en: "Loading design achievement…" },
  'designAchievement.loadError': { es: "No se pudo cargar el logro de diseño", en: "Failed to load design achievement" },
  'designAchievement.retry': { es: "Reintentar", en: "Retry" },
  'designAchievement.demoUnavailable': { es: "Logro de diseño no disponible en la demo por ahora.", en: "Design achievement is not available in the demo yet." },
  'designAchievement.noData': { es: "Sin datos", en: "No data" },
  'designAchievement.rowsTotal': { es: 'filas', en: 'rows' },
  'designAchievement.noDataShort': { es: "—", en: "—" },
  'designAchievement.globalScore': { es: "Puntaje de Logro Diseño", en: "Design achievement score" },
  'designAchievement.scoreScale': { es: "escala 0–100", en: "scale 0–100" },
  'designAchievement.weights': { es: "Pesos de Logro Diseño: cresta 40 % · pata 30 % · berma 30 %, con crédito parcial por elemento.", en: "Design achievement weights: crest 40 % · toe 30 % · berm 30 %, with partial credit per element." },
  'designAchievement.weighingNote': { es: "Nota: en la fila evaluable los elementos faltantes aportan 0 al puntaje global; los porcentajes y medias de cada elemento excluyen las ausencias de su propio denominador. Una fila parcial no equivale a una medición completa.", en: "Note: on an evaluable row missing elements contribute 0 to the global score; each element’s percentages and means exclude absences from its own denominator. A partial row is not a complete measurement." },
  'designAchievement.evaluableCounts': { es: "evaluables", en: "evaluable" },
  'designAchievement.crest': { es: "Cresta", en: "Crest" },
  'designAchievement.toe': { es: "Pata", en: "Toe" },
  'designAchievement.berm': { es: "Berma", en: "Berm" },
  'designAchievement.meanCorrection': { es: "Desviación media", en: "Mean deviation" },
  'designAchievement.sector': { es: "Sector", en: "Sector" },
  'designAchievement.noSector': { es: "Sin sector", en: "No sector" },
  'designAchievement.nEvaluable': { es: "n evaluables", en: "n evaluable" },
  'designAchievement.achievement': { es: "Logro (%)", en: "Achievement (%)" },
  'designAchievement.tolerances': { es: "Tolerancia", en: "Tolerance" },
  'designAchievement.tolSourceCoreDefault': { es: "predeterminada", en: "default" },
  'designAchievement.tolSourceSession': { es: "sesión", en: "session" },
  'designAchievement.provenanceSource': { es: "Fuente", en: "Source" },
  'designAchievement.statusComputed': { es: "calculado", en: "computed" },
  'designAchievement.statusNoData': { es: "sin datos", en: "no data" },
  'designAchievement.assumptions': { es: "Supuestos", en: "Assumptions" },
  'designAchievement.warning_no_results': { es: "No hay resultados de conciliación para evaluar el logro de diseño.", en: "No reconciliation results to evaluate design achievement." },
  'designAchievement.warning_all_rows_filtered_out': { es: "Todas las filas quedaron excluidas por los filtros activos.", en: "All rows were excluded by the active filters." },
  'designAchievement.warning_no_evaluable_rows': { es: "Ninguna fila tiene valores evaluables de cresta y pata.", en: "No rows have evaluable crest and toe values." },
  'designAchievement.warning_session_tolerance_invalid_using_core_default': { es: "Tolerancias de sesión inválidas; se usan las tolerancias predeterminadas del core.", en: "Invalid session tolerances; core default tolerances are used." },
};

function pick(obj: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>((node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined), obj);
}

describe('BLOCK1 es/en translations', () => {
  it.each(Object.entries(BLOCK1))('%s defined in es.json and en.json', (key, expected) => {
    expect(pick(es, key)).toBe(expected.es);
    expect(pick(en, key)).toBe(expected.en);
  });
});
