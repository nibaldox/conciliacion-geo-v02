import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from '../../../i18n';
import type { BlastCorrelationRow } from '../../../api/types';
import { BlastCorrelationTable } from '../BlastCorrelationTable';
import { ConsolidationReport, FootprintReport } from '../BlastUploader';
import { buildDamageTraces } from '../PowderFactorDamagePanel';

describe('corrective blast presentation', () => {
  it('explains all unavailable primary PF statuses and preserves unknown codes', async () => {
    await i18n.changeLanguage('es');
    const row = { section_name: 'S', sector: '', num_wells: 95, pf_voronoi_bench_g_per_ton_section: null, pf_voronoi_bench_status_counts: { MISSING_FOOTPRINT: 88, MISSING_BENCH_HEIGHT: 1, MISSING_DENSITY: 1, MISSING_CHARGE: 1, INVALID_AREA: 1, OUTSIDE_FOOTPRINT: 1, CONSERVATION_FAILED: 1, UNKNOWN: 1, NEW_STATUS: 2 } } as unknown as BlastCorrelationRow;
    render(<BlastCorrelationTable rows={[row]} />);
    expect(screen.getByText(/sin huella de malla \(88 pozos\)/i)).toBeInTheDocument();
    for (const text of ['sin altura de banco', 'sin densidad', 'sin carga', 'área inválida', 'fuera de la huella', 'falló la conservación', 'desconocido', 'NEW_STATUS']) expect(screen.getByText(new RegExp(text, 'i'))).toBeInTheDocument();
  });

  it('does not present missing reasons when primary PF is measured', async () => {
    await i18n.changeLanguage('es');
    const row = { section_name: 'S', sector: '', num_wells: 1, pf_voronoi_bench_g_per_ton_section: 0, pf_voronoi_bench_status_counts: { MISSING_FOOTPRINT: 1 } } as unknown as BlastCorrelationRow;
    render(<BlastCorrelationTable rows={[row]} />);
    expect(screen.queryByText(/sin huella de malla/)).not.toBeInTheDocument();
  });
  it('distinguishes missing primary PF and energy from measured zero', async () => {
    await i18n.changeLanguage('es');
    const row = {
      section_name: 'S', sector: '', num_wells: 2, total_kg: 0,
      pf_voronoi_bench_g_per_ton_section: null, n_pf_voronoi_bench_valid: 0,
      pf_g_per_ton_avg: 0, pf_g_per_ton_net_avg: null, pf_vol_avg_kgm3: null,
      pf_area_avg_kgm2: null, energy_total_mj: null, energy_coverage_kg_fraction: 0.5,
      avg_over_break: 0, avg_under_break: null, n_over: 1, n_under: 0,
    } as BlastCorrelationRow;
    render(<BlastCorrelationTable rows={[row]} />);
    expect(screen.getByText(/PF principal/)).toBeInTheDocument();
    expect(screen.getAllByText(/sin dato/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText('0.00').length).toBeGreaterThan(0);
    expect(screen.getByText(/50/)).toBeInTheDocument();
    expect(screen.getByText(/n = 1/)).toBeInTheDocument();
  });

  it('shows partial energy and missing mass coverage without inventing totals', async () => {
    await i18n.changeLanguage('es');
    const row = { section_name: 'S', sector: '', num_wells: 3, total_kg: null, n_kg_known: 2, n_kg_missing: 1, energy_total_mj: null, energy_known_mj: 70.68, energy_coverage_kg_fraction: 0.5 } as BlastCorrelationRow;
    render(<BlastCorrelationTable rows={[row]} />);
    expect(screen.getByText(/parcial: 70.68 MJ \(cobertura 50 %\)/i)).toBeInTheDocument();
    expect(screen.getByText(/2 conocidos.*1 faltante/i)).toBeInTheDocument();
  });

  it('exposes the exact API formula on the PF header', async () => {
    await i18n.changeLanguage('es');
    render(<BlastCorrelationTable rows={[]} definitions={{ pf_g_per_ton: { formula: '1000*Q/(B*S*L_vertical*rho)', numerator: 'charge_kg', denominator: 'B*S*L*rho', unit: 'g/t', height_source: 'length' } }} />);
    expect(screen.getByTitle('1000*Q/(B*S*L_vertical*rho)')).toBeInTheDocument();
  });

  it('reports consolidated copies and decks', async () => {
    await i18n.changeLanguage('es');
    render(<ConsolidationReport report={{ rows_in: 4, holes_out: 2, exact_copies_removed: 1, copies_by_malla: { M1: 1 }, holes_with_decks: 1, conflicts: [{ malla: 'M1', id_pozo: 'X', source_row_indices: [1], reason: 'conflict' }], key_columns: ['id_pozo'], deck_rows_merged: 1, unmerged_missing_identity: 0, version: 'v1' }} />);
    expect(screen.getByText(/filas recibidas: 4/i)).toBeInTheDocument();
    expect(screen.getByText(/M1: 1/)).toBeInTheDocument();
    expect(screen.getByText(/pozos con decks: 1/i)).toBeInTheDocument();
  });

  it('labels an estimated footprint on the primary PF column', async () => {
    await i18n.changeLanguage('es');
    const row = {
      section_name: 'S', sector: '', num_wells: 10, pf_voronoi_bench_g_per_ton_section: 120,
      pf_voronoi_bench_source_dominant: 'footprint:estimated_hull',
      pf_voronoi_bench_source_counts: { 'footprint:estimated_hull': 10 },
    } as unknown as BlastCorrelationRow;
    render(<BlastCorrelationTable rows={[row]} definitions={{ pf_voronoi_bench_g_per_ton: { formula: '1000*Q/(A*H*rho)', unit: 'g/t', footprint: 'convex hull of unique collar sites' } }} />);
    const label = screen.getByTestId('pf-footprint-source-S');
    expect(label).toHaveTextContent(/huella estimada/i);
    expect(label).toHaveAttribute('title', 'convex hull of unique collar sites');
  });

  it('labels an operator polygon differently from an estimated footprint', async () => {
    await i18n.changeLanguage('es');
    const row = {
      section_name: 'S', sector: '', num_wells: 2, pf_voronoi_bench_g_per_ton_section: 120,
      pf_voronoi_bench_source_dominant: 'footprint:user_polygon',
    } as unknown as BlastCorrelationRow;
    render(<BlastCorrelationTable rows={[row]} />);
    expect(screen.getByTestId('pf-footprint-source-S')).toHaveTextContent(/huella declarada/i);
  });

  it('renders the import footprint report with counts and missing reasons', async () => {
    await i18n.changeLanguage('es');
    render(<FootprintReport report={{
      mode: 'estimated_hull', n_mallas: 99, n_estimated: 97, n_user: 0, n_missing: 2,
      buffer_factor: 0.5,
      method: 'convex hull of unique collar sites buffered by 0.5×median nearest-neighbour spacing',
      missing_reasons: { M1: 'insufficient_noncollinear_sites' },
    }} />);
    expect(screen.getByText(/Mallas: 99/)).toBeInTheDocument();
    expect(screen.getByTestId('footprint-report-estimated')).toHaveTextContent(/Con huella estimada: 97/);
    expect(screen.getByTestId('footprint-report-missing')).toHaveTextContent(/Sin huella utilizable: 2/);
    expect(screen.getByText(/insufficient_noncollinear_sites/)).toBeInTheDocument();
  });

  it('does not draw a fit with unavailable coefficients', () => {
    const points = Array.from({ length: 5 }, (_, index) => ({ section_name: String(index), pf_g_per_ton: 10, over_break: 0 }));
    const fit = { beta0: null, beta1: 1, r_squared: null, p_value: null, n: 5, confidence: 'LOW' as const, ci_beta1_low: null, ci_beta1_high: null };
    expect(buildDamageTraces(points, fit)).toHaveLength(1);
  });

  it('excludes null scatter values but keeps measured zero', () => {
    const traces = buildDamageTraces([
      { section_name: 'missing', pf_g_per_ton: null, over_break: 1 },
      { section_name: 'zero', pf_g_per_ton: 10, over_break: 0 },
    ], null);
    expect(traces[0]).toMatchObject({ x: [10], y: [0], text: ['zero'] });
  });
});
