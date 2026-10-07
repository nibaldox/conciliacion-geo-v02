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

describe('BenchInspector', () => {
  it('asks for a selection without presenting invented measurements', () => {
    show(null);
    expect(screen.getByText('Selecciona un banco')).toBeInTheDocument();
    expect(screen.queryByText('Altura real')).not.toBeInTheDocument();
  });

  it('shows actual and design values with units and the selected bench status', () => {
    show(bench);
    expect(screen.getByText('Banco 04')).toBeInTheDocument();
    expect(screen.getByText('15.2 m')).toBeInTheDocument();
    expect(screen.getByText('15.0 m')).toBeInTheDocument();
    expect(screen.getByText('65.0 °')).toBeInTheDocument();
    expect(screen.getByText('No cumple')).toBeInTheDocument();
  });

  it('distinguishes measured zero from unavailable and nonfinite values', () => {
    show({ ...bench, height: 0, bermWidth: null, designBerm: null, designAngle: Number.NaN, status: 'UNKNOWN' });
    expect(screen.getByText('0.0 m')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(3);
    expect(screen.getByText('Sin datos')).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
