import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useCreateBlastSimulation, extractSimulationErrorDiagnostics } from '@/api/hooks';
import type {
  SimulationCreateRequest,
  SimulationCreateResponse,
  EnergyMode,
  TemporalMode,
  AnisotropyMode,
} from '@/api/types';

interface Props {
  sessionId: string | null;
  geometryConfigurationVersion: string;
}

const EMPTY = '';

interface FormState {
  voxelSize: string;
  xMin: string; xMax: string;
  yMin: string; yMax: string;
  zMin: string; zMax: string;
  energyMode: EnergyMode | '';
  temporalMode: TemporalMode | '';
  anisotropyMode: AnisotropyMode | '';
  attenuation: string;
  regularization: string;
  coupling: string;
  velocity: string;
  velocitySource: string;
  pulseSigma: string;
  planElevations: string;
  sectionCoords: string;
  confirmed: boolean;
}

const INITIAL_STATE: FormState = {
  voxelSize: EMPTY,
  xMin: EMPTY, xMax: EMPTY,
  yMin: EMPTY, yMax: EMPTY,
  zMin: EMPTY, zMax: EMPTY,
  energyMode: EMPTY,
  temporalMode: EMPTY,
  anisotropyMode: EMPTY,
  attenuation: EMPTY,
  regularization: EMPTY,
  coupling: EMPTY,
  velocity: EMPTY,
  velocitySource: EMPTY,
  pulseSigma: EMPTY,
  planElevations: EMPTY,
  sectionCoords: EMPTY,
  confirmed: false,
};

function fingerprint(s: FormState): string {
  const parts = [
    s.voxelSize, s.xMin, s.xMax, s.yMin, s.yMax, s.zMin, s.zMax,
    s.energyMode, s.temporalMode, s.anisotropyMode,
    s.attenuation, s.regularization, s.coupling,
    s.velocity, s.velocitySource, s.pulseSigma,
    s.planElevations, s.sectionCoords,
  ];
  return parts.join('|');
}

function reducer(s: FormState, patch: Partial<FormState>): FormState {
  // Any edit clears the confirmation UNLESS the edit IS the confirmation
  // toggle itself (spec §10 — invalidation by fingerprint).
  if ('confirmed' in patch && Object.keys(patch).length === 1) {
    return { ...s, ...patch };
  }
  return { ...s, ...patch, confirmed: false };
}

function buildRequest(
  s: FormState,
  sessionId: string,
  geomVersion: string,
): SimulationCreateRequest | null {
  const voxel = Number(s.voxelSize);
  const xMin = Number(s.xMin), xMax = Number(s.xMax);
  const yMin = Number(s.yMin), yMax = Number(s.yMax);
  const zMin = Number(s.zMin), zMax = Number(s.zMax);
  const attenuation = Number(s.attenuation);
  const regularization = Number(s.regularization);
  const coupling = Number(s.coupling);
  if (![voxel, xMin, xMax, yMin, yMax, zMin, zMax, attenuation, regularization, coupling]
    .every((v) => Number.isFinite(v))) {
    return null;
  }
  if (!s.energyMode || !s.temporalMode || !s.anisotropyMode) return null;
  const plan_elevations = s.planElevations
    .split(',').map((x) => Number(x.trim())).filter(Number.isFinite);
  const section_coordinates = s.sectionCoords
    .split(';').map((part) => {
      const [ax, c] = part.split(',').map((x) => x.trim());
      if (ax !== 'x' && ax !== 'y') return null;
      const n = Number(c);
      return Number.isFinite(n) ? ([ax, n] as ['x' | 'y', number]) : null;
    }).filter((x): x is ['x' | 'y', number] => x !== null);
  const velocity = s.velocity ? Number(s.velocity) : null;
  const pulseSigma = s.pulseSigma ? Number(s.pulseSigma) : null;
  return {
    session_id: sessionId,
    geometry_configuration_version: geomVersion,
    user_confirmed: s.confirmed,
    voxel_size_m: voxel,
    domain_bounds: {
      x_min: xMin, y_min: yMin, z_min: zMin,
      x_max: xMax, y_max: yMax, z_max: zMax,
    },
    energy_mode: s.energyMode as EnergyMode,
    temporal_mode: s.temporalMode as TemporalMode,
    anisotropy_mode: s.anisotropyMode as AnisotropyMode,
    kernel_type: 'EXPONENTIAL_INVERSE_SQUARE',
    attenuation_coefficient_1_m: attenuation,
    regularization_radius_m: regularization,
    coupling_efficiency: coupling,
    propagation_velocity_m_s: velocity,
    propagation_velocity_source: s.velocitySource,
    pulse_sigma_s: pulseSigma,
    plan_elevations,
    section_coordinates,
  };
}

export function BlastSimulationPanel({ sessionId, geometryConfigurationVersion }: Props) {
  const { t } = useTranslation();
  const [state, setState] = useState<FormState>(INITIAL_STATE);
  const [result, setResult] = useState<SimulationCreateResponse | null>(null);
  const mutation = useCreateBlastSimulation();

  const confirmedFingerprint = useMemo(() => fingerprint(state), [state]);

  const update = (patch: Partial<FormState>) => setState((s) => reducer(s, patch));

  const request = useMemo(
    () => sessionId ? buildRequest(state, sessionId, geometryConfigurationVersion) : null,
    [state, sessionId, geometryConfigurationVersion],
  );

  const canConfirm = !!request;
  const canRun = !!request && state.confirmed && !mutation.isPending;

  const onSubmit = async () => {
    if (!request) return;
    setResult(null);
    try {
      const data = await mutation.mutateAsync(request);
      setResult(data);
    } catch (err) {
      // The hook surfaces structured errors via extractSimulationErrorDiagnostics;
      // the parent renders them. We swallow the throw here.
      setResult(null);
    }
  };

  const errorDiag = extractSimulationErrorDiagnostics(mutation.error);

  return (
    <section className="rounded-lg border border-[var(--color-border)] p-4 space-y-4 bg-[var(--color-surface)]">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">{t('blast.simulation.title')}</h2>
        <p className="text-sm opacity-70">{t('blast.simulation.subtitle')}</p>
        <p className="text-xs px-2 py-1 rounded bg-[var(--status-warning-bg, #fef3c7)] text-[var(--status-warning-fg, #92400e)]">
          ⚠ {t('blast.simulation.warning_uncalibrated')}
        </p>
      </header>

      {!sessionId && (
        <p className="text-sm opacity-70">{t('blast.simulation.no_session')}</p>
      )}

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t('blast.simulation.domain_section')}</legend>
        <div className="grid grid-cols-3 gap-2">
          <NumberField label={t('blast.simulation.x_min')} value={state.xMin} onChange={(v) => update({ xMin: v })} />
          <NumberField label={t('blast.simulation.y_min')} value={state.yMin} onChange={(v) => update({ yMin: v })} />
          <NumberField label={t('blast.simulation.z_min')} value={state.zMin} onChange={(v) => update({ zMin: v })} />
          <NumberField label={t('blast.simulation.x_max')} value={state.xMax} onChange={(v) => update({ xMax: v })} />
          <NumberField label={t('blast.simulation.y_max')} value={state.yMax} onChange={(v) => update({ yMax: v })} />
          <NumberField label={t('blast.simulation.z_max')} value={state.zMax} onChange={(v) => update({ zMax: v })} />
          <NumberField label={t('blast.simulation.voxel_size')} value={state.voxelSize} onChange={(v) => update({ voxelSize: v })} />
        </div>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t('blast.simulation.physics_section')}</legend>
        <div className="grid grid-cols-3 gap-2">
          <SelectField
            label={t('blast.simulation.energy_mode')}
            value={state.energyMode}
            onChange={(v) => update({ energyMode: v as EnergyMode })}
            options={[
              { value: '', label: t('blast.simulation.select_placeholder') },
              { value: 'ABSOLUTE', label: t('blast.simulation.energy_mode_absolute') },
              { value: 'RELATIVE', label: t('blast.simulation.energy_mode_relative') },
            ]}
          />
          <SelectField
            label={t('blast.simulation.temporal_mode')}
            value={state.temporalMode}
            onChange={(v) => update({ temporalMode: v as TemporalMode })}
            options={[
              { value: '', label: t('blast.simulation.select_placeholder') },
              { value: 'STATIC', label: t('blast.simulation.temporal_mode_static') },
              { value: 'TEMPORAL', label: t('blast.simulation.temporal_mode_temporal') },
            ]}
          />
          <SelectField
            label={t('blast.simulation.anisotropy_mode')}
            value={state.anisotropyMode}
            onChange={(v) => update({ anisotropyMode: v as AnisotropyMode })}
            options={[
              { value: '', label: t('blast.simulation.select_placeholder') },
              { value: 'ISOTROPIC', label: t('blast.simulation.anisotropy_mode_isotropic') },
              { value: 'ANISOTROPIC_TENSOR', label: t('blast.simulation.anisotropy_mode_tensor') },
            ]}
          />
        </div>
        <p className="text-xs opacity-70">{t('blast.simulation.energy_mode_help')}</p>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t('blast.simulation.kernel_section')}</legend>
        <div className="grid grid-cols-3 gap-2">
          <NumberField label={t('blast.simulation.attenuation')} value={state.attenuation} onChange={(v) => update({ attenuation: v })} />
          <NumberField label={t('blast.simulation.regularization')} value={state.regularization} onChange={(v) => update({ regularization: v })} />
          <NumberField label={t('blast.simulation.coupling')} value={state.coupling} onChange={(v) => update({ coupling: v })} />
        </div>
      </fieldset>

      {state.temporalMode === 'TEMPORAL' && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t('blast.simulation.temporal_section')}</legend>
          <div className="grid grid-cols-3 gap-2">
            <NumberField label={t('blast.simulation.velocity')} value={state.velocity} onChange={(v) => update({ velocity: v })} />
            <TextField label={t('blast.simulation.velocity_source')} value={state.velocitySource} onChange={(v) => update({ velocitySource: v })} />
            <NumberField label={t('blast.simulation.pulse_sigma')} value={state.pulseSigma} onChange={(v) => update({ pulseSigma: v })} />
          </div>
        </fieldset>
      )}

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t('blast.simulation.plan_elevations')}</legend>
        <TextField label={t('blast.simulation.section_coords')} value={state.sectionCoords} onChange={(v) => update({ sectionCoords: v })} />
        <TextField label={t('blast.simulation.plan_elevations')} value={state.planElevations} onChange={(v) => update({ planElevations: v })} />
      </fieldset>

      <div className="space-y-2">
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            data-testid="sim-confirm-checkbox"
            checked={state.confirmed}
            disabled={!canConfirm}
            onChange={(e) => update({ confirmed: e.target.checked })}
          />
          <span>{t('blast.simulation.confirm_label')}</span>
        </label>
        <p className="text-xs opacity-70">{t('blast.simulation.edit_invalidates')}</p>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!canRun}
          data-testid="sim-run-button"
          className="px-3 py-1.5 rounded bg-[var(--color-primary)] text-[var(--color-on-primary)] disabled:opacity-50"
        >
          {mutation.isPending ? t('blast.simulation.run_pending') : t('blast.simulation.run_button')}
        </button>
      </div>

      {errorDiag && (
        <div className="text-sm p-2 rounded bg-[var(--status-error-bg, #fee2e2)] text-[var(--status-error-fg, #991b1b)]">
          <strong>{errorDiag.error_code}</strong>: {errorDiag.message || t('blast.simulation.missing_field')}
        </div>
      )}

      {result && <SimulationResultView result={result} />}

      <p className="text-xs opacity-50 font-mono" data-testid="sim-fingerprint">
        fp:{confirmedFingerprint.slice(0, 12)}
      </p>
    </section>
  );
}

function SimulationResultView({ result }: { result: SimulationCreateResponse }) {
  const { t } = useTranslation();
  const s = result.summary;
  const unitLabel = result.grid_metadata.energy_unit === 'J'
    ? t('blast.simulation.energy_unit_j')
    : t('blast.simulation.energy_unit_dimensionless');
  return (
    <div className="space-y-3 border-t pt-3" data-testid="sim-result">
      <h3 className="font-medium">{t('blast.simulation.summary_section')}</h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt>{t('blast.simulation.represented_energy')}</dt>
        <dd>{result.energy_field.represented_energy_j.toFixed(0)} {unitLabel}</dd>
        <dt>{t('blast.simulation.outside_energy')}</dt>
        <dd>{result.energy_field.outside_domain_energy_j.toFixed(0)} {unitLabel}</dd>
        <dt>{t('blast.simulation.fraction_represented')}</dt>
        <dd>{(result.energy_field.fraction_represented * 100).toFixed(2)} %</dd>
        <dt>{t('blast.simulation.active_voxels')}</dt>
        <dd>{result.energy_field.active_voxels} / {result.grid_metadata.voxel_count}</dd>
        <dt>{t('blast.simulation.valid_sources')}</dt>
        <dd>{s.valid_sources}</dd>
        <dt>{t('blast.simulation.invalid_sources')}</dt>
        <dd>{s.invalid_sources}</dd>
      </dl>

      {result.blocking_errors.length > 0 && (
        <div className="text-sm p-2 rounded bg-[var(--status-error-bg, #fee2e2)]">
          <strong>{t('blast.simulation.blocking_errors_title')}</strong>
          <ul className="list-disc ml-4">
            {result.blocking_errors.map((b, i) => (
              <li key={i}>{b.error_code}: {b.message}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h4 className="text-sm font-medium">{t('blast.simulation.plan_slices_title')}</h4>
        {result.plan_slices.length === 0 ? (
          <p className="text-xs opacity-70">{t('blast.simulation.no_plan_slices')}</p>
        ) : (
          <ul className="text-xs list-disc ml-4">
            {result.plan_slices.map((p, i) => (
              <li key={i}>
                z = {p.elevation_m.toFixed(2)} m — max {p.max_value.toFixed(3)},
                sha {p.data_sha256.slice(0, 8)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h4 className="text-sm font-medium">{t('blast.simulation.section_slices_title')}</h4>
        {result.section_slices.length === 0 ? (
          <p className="text-xs opacity-70">{t('blast.simulation.no_section_slices')}</p>
        ) : (
          <ul className="text-xs list-disc ml-4">
            {result.section_slices.map((s, i) => (
              <li key={i}>
                {s.axis} = {s.coordinate_m.toFixed(2)} m — max {s.max_value.toFixed(3)},
                sha {s.data_sha256.slice(0, 8)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="text-xs space-y-1 block">
      <span className="block opacity-70">{label}</span>
      <input
        type="number"
        step="any"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1 rounded border border-[var(--color-border)] bg-[var(--color-input-bg, transparent)]"
      />
    </label>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="text-xs space-y-1 block">
      <span className="block opacity-70">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1 rounded border border-[var(--color-border)] bg-[var(--color-input-bg, transparent)]"
      />
    </label>
  );
}

function SelectField({ label, value, onChange, options }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="text-xs space-y-1 block">
      <span className="block opacity-70">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1 rounded border border-[var(--color-border)] bg-[var(--color-input-bg, transparent)]"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}
