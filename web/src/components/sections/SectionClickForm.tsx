import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useClickSection, useSections } from '../../api/hooks';
import type { SectionClickParams } from '../../api/types';

interface SectionClickFormProps {
  /** Register callback so PlanView can invoke it on map click */
  onRegisterClickHandler?: (handler: ((x: number, y: number) => void) | null) => void;
}

export function SectionClickForm({ onRegisterClickHandler }: SectionClickFormProps) {
  const { t } = useTranslation();
  const [length, setLength] = useState(200);
  const [sector, setSector] = useState('');
  const [azMode, setAzMode] = useState<'auto' | 'manual'>('auto');
  const [azimuth, setAzimuth] = useState(0);

  const mutation = useClickSection();
  const { data: sections } = useSections();

  const handleMapClick = useCallback(
    (x: number, y: number) => {
      const coords: [number, number] = [x, y];
      const params: SectionClickParams = {
        origin: coords,
        length,
        sector,
        az_mode: azMode,
        ...(azMode === 'manual' ? { azimuth } : {}),
      };

      mutation.mutate(params);
    },
    [length, sector, azMode, azimuth, mutation],
  );

  // Register the click handler so parent components (PlanView) can call it
  useEffect(() => {
    onRegisterClickHandler?.(handleMapClick);
    return () => {
      onRegisterClickHandler?.(null);
    };
  }, [onRegisterClickHandler, handleMapClick]);

  const nAdded = sections?.length ?? 0;

  return (
    <div className="space-y-5">
      {/* Instructions */}
      <div className="flex items-center gap-3 p-4 rounded-lg" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <span className="text-2xl">&#x1F4CD;</span>
        <div>
          <p className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
            {t('section_form_click.instruction_title')}
          </p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_click.instruction_subtitle')}
          </p>
        </div>
      </div>

      {/* Settings */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_click.length')}
          </label>
          <input
            type="number"
            min={1}
            step="any"
            value={length}
            onChange={(e) => setLength(parseFloat(e.target.value) || 200)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_click.sector')}
          </label>
          <input
            type="text"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            placeholder={t('section_form_click.sector_placeholder')}
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
            {t('section_form_click.az_mode')}
          </label>
          <select
            value={azMode}
            onChange={(e) => setAzMode(e.target.value as 'auto' | 'manual')}
            className="w-full rounded-md px-3 py-2 text-sm outline-none"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
          >
            <option value="auto">{t('section_form_click.az_auto')}</option>
            <option value="manual">{t('section_form_click.az_manual')}</option>
          </select>
        </div>

        {azMode === 'manual' && (
          <div>
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-muted)' }}>
              {t('section_form_click.azimuth')}
            </label>
            <input
              type="number"
              min={0}
              max={360}
              step="any"
              value={azimuth}
              onChange={(e) => setAzimuth(parseFloat(e.target.value) || 0)}
              className="w-full rounded-md px-3 py-2 text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </div>
        )}
      </div>

      {/* Status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-8 h-8 rounded-full text-white text-sm font-bold" style={{ backgroundColor: 'var(--color-mine-blue)' }}>
            {nAdded}
          </span>
          <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            {t('section_form_click.n_added', { count: nAdded })}
          </span>
        </div>

        {mutation.isPending && (
          <span className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-mine-blue)' }}>
            <span className="animate-spin inline-block w-4 h-4 border-2 rounded-full" style={{ borderColor: 'var(--color-mine-blue)', borderTopColor: 'transparent' }} />
            {t('section_form_click.adding')}
          </span>
        )}

        {mutation.isError && (
          <p className="text-sm" style={{ color: 'var(--color-mine-red)' }}>
            {t('common.error')}: {mutation.error instanceof Error ? mutation.error.message : t('section_form_click.error_generic')}
          </p>
        )}
      </div>
    </div>
  );
}
