import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import type { Tolerances } from '../../../api/types';
import { TolerancesForm, mergeTolerance } from '../TolerancesForm';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

const BASE: Tolerances = {
  bench_height: { neg: 1, pos: 1.5 },
  face_angle: { neg: 5, pos: 5 },
  berm_width: { min: 6 },
  inter_ramp_angle: { neg: 3, pos: 2 },
  overall_angle: { neg: 2, pos: 2 },
};

const CREST_NEG = 'Tolerancia negativa: Desviación cresta-pata (m)';
const CREST_POS = 'Tolerancia positiva: Desviación cresta-pata (m)';

function renderForm(tolerances: Tolerances, onChange = vi.fn()) {
  render(
    <I18nextProvider i18n={i18n}>
      <TolerancesForm tolerances={tolerances} onChange={onChange} />
    </I18nextProvider>,
  );
  return onChange;
}

beforeEach(() => {
  void i18n.changeLanguage('es');
});

describe('TolerancesForm — desviación cresta/pata', () => {
  it('muestra el par cresta/pata (m) con entradas accesibles min 0 fuera de los ángulos globales', async () => {
    renderForm(BASE);
    const neg = screen.getByLabelText(CREST_NEG) as HTMLInputElement;
    const pos = screen.getByLabelText(CREST_POS) as HTMLInputElement;
    expect(neg.value).toBe('1');
    expect(pos.value).toBe('1');
    expect(neg.step).toBe('0.1');
    expect(pos.step).toBe('0.1');
    expect(neg.min).toBe('0');
    expect(pos.min).toBe('0');
    expect(neg.closest('details')).toBeNull();
    expect(pos.closest('details')).toBeNull();
    const interNeg = screen.getByLabelText('Tolerancia negativa: Ángulo inter-rampa (°)');
    expect(interNeg.closest('details')).not.toBeNull();
    const overallNeg = screen.getByLabelText('Tolerancia negativa: Ángulo global (°)');
    expect(overallNeg.closest('details')).not.toBeNull();
  });

  it('usa el fallback 1/1 explícito cuando el GET previo no trae el par', async () => {
    const onChange = renderForm(BASE);
    const neg = screen.getByLabelText(CREST_NEG) as HTMLInputElement;
    const pos = screen.getByLabelText(CREST_POS) as HTMLInputElement;
    expect(neg.value).toBe('1');
    expect(pos.value).toBe('1');
    fireEvent.change(pos, { target: { value: '3' } });
    expect(onChange.mock.lastCall).toEqual(['crest_toe_deviation', { neg: 1, pos: 3 }]);
    expect(onChange.mock.calls.every(([key]) => key === 'crest_toe_deviation')).toBe(true);
  });

  it('emite el par completo al editar un solo lado y no toca los demás ajustes', async () => {
    const onChange = renderForm({ ...BASE, crest_toe_deviation: { neg: 0.8, pos: 0.4 } });
    const neg = screen.getByLabelText(CREST_NEG) as HTMLInputElement;
    expect(neg.value).toBe('0.8');
    fireEvent.change(neg, { target: { value: '2.5' } });
    expect(onChange.mock.lastCall).toEqual(['crest_toe_deviation', { neg: 2.5, pos: 0.4 }]);
    const editedKeys = new Set(onChange.mock.calls.map(([key]) => key));
    expect([...editedKeys]).toEqual(['crest_toe_deviation']);
  });

  it('permite el cero como magnitud válida', async () => {
    const onChange = renderForm({ ...BASE, crest_toe_deviation: { neg: 2, pos: 1 } });
    const neg = screen.getByLabelText(CREST_NEG) as HTMLInputElement;
    fireEvent.change(neg, { target: { value: '0' } });
    expect(onChange.mock.lastCall).toEqual(['crest_toe_deviation', { neg: 0, pos: 1 }]);
  });

  it('rechaza valores negativos sin emitir onChange', () => {
    const onChange = renderForm({ ...BASE, crest_toe_deviation: { neg: 2, pos: 1 } });
    const neg = screen.getByLabelText(CREST_NEG);
    fireEvent.change(neg, { target: { value: '-3' } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('rechaza valores no finitos y no fabrica 0 al borrar', () => {
    const onChange = renderForm({ ...BASE, crest_toe_deviation: { neg: 2, pos: 1 } });
    const neg = screen.getByLabelText(CREST_NEG);
    fireEvent.change(neg, { target: { value: 'Infinity' } });
    fireEvent.change(neg, { target: { value: 'abc' } });
    fireEvent.change(neg, { target: { value: '' } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('adopta el texto del bundle de idioma cuando la clave se integra en locales', async () => {
    const inst = createInstance();
    const translation = { ...es, sidebar: { ...es.sidebar, tol_crest_toe: 'Desviación entre cresta y pata (m)' } };
    void inst.init({ lng: 'es', resources: { es: { translation } }, initAsync: false });
    render(
      <I18nextProvider i18n={inst}>
        <TolerancesForm tolerances={BASE} onChange={vi.fn()} />
      </I18nextProvider>,
    );
    expect(screen.getByLabelText('Tolerancia negativa: Desviación entre cresta y pata (m)')).toBeInTheDocument();
    expect(screen.getByLabelText('Tolerancia positiva: Desviación entre cresta y pata (m)')).toBeInTheDocument();
  });
});

describe('mergeTolerance', () => {
  it('completa el par ausente con el fallback del lado opuesto y preserva el resto', () => {
    const merged = mergeTolerance(BASE, 'crest_toe_deviation', { neg: 2.5 });
    expect(merged.crest_toe_deviation).toEqual({ neg: 2.5, pos: 1 });
    expect(merged.inter_ramp_angle).toBe(BASE.inter_ramp_angle);
    expect(merged.bench_height).toBe(BASE.bench_height);
    expect(merged.berm_width).toBe(BASE.berm_width);
    expect(merged.overall_angle).toBe(BASE.overall_angle);
  });

  it('conserva el lado no editado del par existente', () => {
    const merged = mergeTolerance(
      { ...BASE, crest_toe_deviation: { neg: 1.1, pos: 0.9 } },
      'crest_toe_deviation',
      { neg: 2 },
    );
    expect(merged.crest_toe_deviation).toEqual({ neg: 2, pos: 0.9 });
  });

  it('deja intactos los demás ajustes al editar otra tolerancia', () => {
    const withCrest = { ...BASE, crest_toe_deviation: { neg: 0.5, pos: 0.5 } };
    const merged = mergeTolerance(withCrest, 'berm_width', { min: 8 });
    expect(merged.berm_width).toEqual({ min: 8 });
    expect(merged.crest_toe_deviation).toEqual({ neg: 0.5, pos: 0.5 });
    expect(merged.bench_height).toBe(withCrest.bench_height);
  });
});
