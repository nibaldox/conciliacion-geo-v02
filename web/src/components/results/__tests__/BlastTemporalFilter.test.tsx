import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import i18n from '../../../i18n';
import { BlastTemporalFilter } from '../BlastTemporalFilter';

describe('BlastTemporalFilter', () => {
  beforeAll(async () => { await i18n.changeLanguage('es'); });

  it('applies only on confirmation and exposes the effective cutoff and missing dates', () => {
    const apply = vi.fn();
    const view = render(<BlastTemporalFilter surveyDate="" onApply={apply} />);
    expect(screen.getByRole('status')).toHaveTextContent('Sin fecha de levantamiento');
    fireEvent.change(screen.getByLabelText('Fecha del levantamiento topográfico'), { target: { value: '2026-11-04' } });
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Aplicar fecha' }));
    expect(apply).toHaveBeenCalledWith('2026-11-04');
    view.rerender(<BlastTemporalFilter surveyDate="2026-11-04" onApply={apply} metadata={{ enabled: true, survey_date: '2026-11-04', effective_cutoff_date: '2026-10-28', buffer_days: 7, policy: 'exclude_missing', included: 20, excluded: 4, missing: 2 }} />);
    expect(screen.getByRole('status')).toHaveTextContent('2026-10-28');
    expect(screen.getByRole('status')).toHaveTextContent('Sin fecha válida, excluidos: 2');
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro temporal' }));
    expect(apply).toHaveBeenLastCalledWith('');
  });
});
