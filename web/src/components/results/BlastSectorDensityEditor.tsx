import { useTranslation } from 'react-i18next';

/**
 * Per-sector ρ editor (BlastDensityControl sub-panel).
 *
 * Renders one numeric input per distinct sector so the user can override
 * the global rock density for a single geotechnical domain. A blank
 * input means "use the global density"; a non-empty input PUTs the
 * override alongside the global blast block on apply.
 *
 * Inputs are read from / written to the parent's ``sectorDensity`` map
 * via ``setSectorDensity`` (the parent owns the staged map; this
 * component is purely presentational).
 *
 * Test IDs and labels mirror the original in-line JSX so existing
 * integration / e2e selectors continue to work.
 */
export function BlastSectorDensityEditor({
  sectors,
  density,
  sectorDensity,
  setSectorDensity,
}: {
  sectors: string[];
  density: number;
  sectorDensity: Record<string, number>;
  setSectorDensity: React.Dispatch<React.SetStateAction<Record<string, number>>>;
}) {
  const { t } = useTranslation();

  const inputStyle: React.CSSProperties = {
    backgroundColor: 'var(--color-surface)',
    borderColor: 'var(--color-border)',
    color: 'var(--color-text-primary)',
  };
  const sectorInputCls =
    'w-20 px-2 py-1 border rounded-md text-xs outline-none transition-colors focus:ring-2 focus:ring-accent/30 font-mono';

  return (
    <div
      className="flex flex-col gap-2 basis-full pt-2 border-t"
      style={{ borderColor: 'var(--color-border)' }}
      data-testid="blast-sector-density-editor"
    >
      <p
        className="text-xs font-semibold"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {t('blast.sector_density_title', { defaultValue: 'Densidad por sector' })}
      </p>
      {sectors.length === 0 ? (
        <p
          className="text-xs"
          style={{ color: 'var(--color-text-muted)' }}
          data-testid="blast-sector-density-empty"
        >
          {t('blast.sector_density_empty', {
            defaultValue:
              'Asigne un sector a cada sección para definir una densidad específica.',
          })}
        </p>
      ) : (
        <div className="flex flex-wrap gap-3">
          {sectors.map((sec) => (
            <div key={sec} className="flex flex-col gap-1">
              <label
                htmlFor={`blast-sector-rho-${sec}`}
                className="text-xs font-mono"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {sec}
              </label>
              <input
                id={`blast-sector-rho-${sec}`}
                type="number"
                inputMode="decimal"
                step="0.1"
                min="0"
                placeholder={String(density)}
                value={sectorDensity[sec] ?? ''}
                onChange={(e) => {
                  const v = e.target.value;
                  setSectorDensity((prev) => {
                    const next = { ...prev };
                    if (v === '') {
                      delete next[sec];
                    } else {
                      const num = Number(v);
                      if (Number.isFinite(num)) next[sec] = num;
                    }
                    return next;
                  });
                }}
                className={sectorInputCls}
                style={inputStyle}
                data-testid={`blast-sector-rho-${sec}`}
              />
            </div>
          ))}
          <p
            className="text-xs leading-relaxed self-center"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {t('blast.sector_density_help', {
              defaultValue:
                'Vacío = usar densidad global. Cada sector anula la densidad solo en sus secciones.',
            })}
          </p>
        </div>
      )}
    </div>
  );
}