import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../../../locales/es.json';
import { BenchInspector } from '../BenchInspector';
import type { Bench } from '../../domain/types';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

const bench: Bench = {
  benchNumber: 4, crestElevation: 100, crestDistance: 0, toeElevation: 85,
  toeDistance: 7, height: 15.2, faceAngle: 65, bermWidth: 8,
  designHeight: 15, designAngle: 70, designBerm: 9, isRamp: false,
  heightStatus: 'CUMPLE', angleStatus: 'NO_CUMPLE', bermStatus: 'CUMPLE',
  status: 'NO_CUMPLE', matched: true, deltaCrest: null, deltaToe: null,
};

function show(value: Bench | null) {
  return render(<I18nextProvider i18n={i18n}><BenchInspector bench={value} /></I18nextProvider>);
}

function structure(container: HTMLElement) {
  const strip = container.querySelector('[data-slot="bench-inspector"]');
  return {
    strip,
    className: strip?.className,
    cells: strip?.querySelectorAll('[data-slot="bench-inspector-cell"]').length,
    values: strip?.querySelectorAll('dd').length,
    labels: Array.from(strip?.querySelectorAll('dt') ?? []).map((label) => label.textContent),
    hint: strip?.querySelectorAll('[data-slot="bench-inspector-hint"]').length,
  };
}

describe('BenchInspector', () => {
  it('asks for a selection with placeholders instead of invented measurements', () => {
    const { container } = show(null);
    expect(screen.getByText('Selecciona un banco')).toBeInTheDocument();
    const values = Array.from(container.querySelectorAll('[data-slot="bench-inspector-cell"] dd:first-of-type'))
      .map((value) => value.textContent);
    expect(values).toEqual(['—', '—', '—', '—', '—']);
    expect(screen.queryByText(/\d+\.\d m/)).not.toBeInTheDocument();
  });

  it('shows actual and design values with units and the selected bench status', () => {
    show(bench);
    expect(screen.getByText('Banco 04')).toBeInTheDocument();
    expect(screen.getByText('15.2 m')).toBeInTheDocument();
    expect(screen.getByText('15.0 m')).toBeInTheDocument();
    expect(screen.getByText('65.0 °')).toBeInTheDocument();
    expect(screen.getByText('70.0 °')).toBeInTheDocument();
    expect(screen.getByText('No cumple')).toBeInTheDocument();
    expect(screen.queryByText('Selecciona un banco')).not.toBeInTheDocument();
  });

  it('distinguishes measured zero from unavailable and nonfinite values', () => {
    show({ ...bench, height: 0, bermWidth: null, designBerm: null, designAngle: Number.NaN, status: 'UNKNOWN' });
    expect(screen.getByText('0.0 m')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(3);
    expect(screen.getByText('Sin datos')).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it('keeps the same fixed-height structure with and without a selected bench', () => {
    const empty = show(null);
    const before = structure(empty.container);
    empty.unmount();
    const selected = show(bench);
    const after = structure(selected.container);

    expect(before.strip).not.toBeNull();
    expect(after.strip).not.toBeNull();
    expect(before.cells).toBe(5);
    expect(after.cells).toBe(before.cells);
    expect(after.values).toBe(before.values);
    expect(after.labels).toEqual(before.labels);
    expect(after.hint).toBe(1);
    expect(before.hint).toBe(1);
    expect(after.className).toBe(before.className);
    expect(before.className).toContain('h-24');
    expect(before.className).toContain('overflow-hidden');
  });
});
