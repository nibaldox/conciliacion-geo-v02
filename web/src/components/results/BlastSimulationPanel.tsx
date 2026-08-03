import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  useCreateBlastSimulation,
  extractSimulationErrorDiagnostics,
} from '@/api/hooks';
import client from '@/api/client';
import type {
  SimulationCreateRequest,
  SimulationCreateResponse,
  EnergyMode,
  TemporalMode,
  AnisotropyMode,
  BlockingError,
  PlanSliceWire,
  SectionSliceWire,
} from '@/api/types';

interface Props {
  sessionId: string | null;
  geometryConfigurationVersion: string;
}

const EMPTY = '';

type Tensor = [number, number, number, number, number, number, number, number, number];

const IDENTITY_TENSOR: Tensor = [1, 0, 0, 0, 1, 0, 0, 0, 1];

interface ProfileRequest {
  start_x: number;
  start_y: number;
  start_z: number;
  end_x: number;
  end_y: number;
  end_z: number;
  n_samples: number;
}

interface ProfileResponse {
  unit: string;
  field_type: string;
  n_samples: number;
  distances_m: number[];
  x_m: number[];
  y_m: number[];
  z_m: number[];
  values: number[];
  min: number;
  max: number;
  mean: number;
  data_sha256: string;
  source_holes_projection: Array<Record<string, unknown>>;
}

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
  supportRadius: string;
  velocity: string;
  velocitySource: string;
  pulseSigma: string;
  planElevations: string;
  sectionCoords: string;
  tensor: Tensor;
  profileStart: string;
  profileEnd: string;
  profileSamples: string;
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
  supportRadius: EMPTY,
  velocity: EMPTY,
  velocitySource: EMPTY,
  pulseSigma: EMPTY,
  planElevations: EMPTY,
  sectionCoords: EMPTY,
  tensor: [...IDENTITY_TENSOR] as Tensor,
  profileStart: EMPTY,
  profileEnd: EMPTY,
  profileSamples: '100',
  confirmed: false,
};

function fingerprint(s: FormState): string {
  const parts = [
    s.voxelSize, s.xMin, s.xMax, s.yMin, s.yMax, s.zMin, s.zMax,
    s.energyMode, s.temporalMode, s.anisotropyMode,
    s.attenuation, s.regularization, s.coupling, s.supportRadius,
    s.velocity, s.velocitySource, s.pulseSigma,
    s.planElevations, s.sectionCoords,
    ...s.tensor.map((v) => String(v)),
    s.profileStart, s.profileEnd, s.profileSamples,
  ];
  return parts.join('|');
}

function reducer(s: FormState, patch: Partial<FormState>): FormState {
  if ('confirmed' in patch && Object.keys(patch).length === 1) {
    return { ...s, ...patch };
  }
  return { ...s, ...patch, confirmed: false };
}

interface TensorValidation {
  finite: boolean;
  symmetric: boolean;
  positiveDefinite: boolean;
  minors: { d1: number; d2: number; d3: number };
}

function validateTensor(t: Tensor): TensorValidation {
  const m: number[][] = [
    [t[0], t[1], t[2]],
    [t[3], t[4], t[5]],
    [t[6], t[7], t[8]],
  ];
  const finite = m.every((row) => row.every((v) => Number.isFinite(v)));
  if (!finite) {
    return { finite: false, symmetric: false, positiveDefinite: false, minors: { d1: 0, d2: 0, d3: 0 } };
  }
  const tol = 1e-9;
  const symmetric =
    Math.abs(m[0][1] - m[1][0]) < tol &&
    Math.abs(m[0][2] - m[2][0]) < tol &&
    Math.abs(m[1][2] - m[2][1]) < tol;
  const d1 = m[0][0];
  const d2 = m[0][0] * m[1][1] - m[0][1] * m[1][0];
  const d3 =
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
    m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
    m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const positiveDefinite = d1 > 0 && d2 > 0 && d3 > 0;
  return { finite, symmetric, positiveDefinite, minors: { d1, d2, d3 } };
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
  const supportRadius = Number(s.supportRadius);
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

  const rock_mass = s.anisotropyMode === 'ANISOTROPIC_TENSOR'
    ? {
        anisotropy_mode: 'ANISOTROPIC_TENSOR' as AnisotropyMode,
        anisotropy_tensor: [
          [s.tensor[0], s.tensor[1], s.tensor[2]],
          [s.tensor[3], s.tensor[4], s.tensor[5]],
          [s.tensor[6], s.tensor[7], s.tensor[8]],
        ],
      }
    : { anisotropy_mode: 'ISOTROPIC' as AnisotropyMode };

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
    support_radius_m: supportRadius,
    coupling_efficiency: coupling,
    propagation_velocity_m_s: velocity,
    propagation_velocity_source: s.velocitySource,
    pulse_sigma_s: pulseSigma,
    plan_elevations,
    section_coordinates,
    rock_mass,
  };
}

function parseXYZ(input: string): [number, number, number] | null {
  const parts = input.split(',').map((p) => Number(p.trim()));
  if (parts.length !== 3 || !parts.every((p) => Number.isFinite(p))) return null;
  return [parts[0], parts[1], parts[2]];
}

export function BlastSimulationPanel({ sessionId, geometryConfigurationVersion }: Props) {
  const { t } = useTranslation();
  const [state, setState] = useState<FormState>(INITIAL_STATE);
  const [result, setResult] = useState<SimulationCreateResponse | null>(null);
  const [profileRequested, setProfileRequested] = useState<{
    simulationId: string;
    request: ProfileRequest;
  } | null>(null);
  const mutation = useCreateBlastSimulation();

  const confirmedFingerprint = useMemo(() => fingerprint(state), [state]);

  const update = (patch: Partial<FormState>) => setState((s) => reducer(s, patch));

  const updateTensorCell = (idx: number, value: number) => {
    setState((s) => {
      const next: Tensor = [...s.tensor] as Tensor;
      next[idx] = value;
      if (idx === 1) next[3] = value;
      else if (idx === 3) next[1] = value;
      else if (idx === 2) next[6] = value;
      else if (idx === 6) next[2] = value;
      else if (idx === 5) next[7] = value;
      else if (idx === 7) next[5] = value;
      return reducer(s, { tensor: next });
    });
  };

  const useIdentityTensor = () => {
    update({ tensor: [...IDENTITY_TENSOR] as Tensor });
  };

  const request = useMemo(
    () => sessionId ? buildRequest(state, sessionId, geometryConfigurationVersion) : null,
    [state, sessionId, geometryConfigurationVersion],
  );

  const tensorValidation = useMemo(
    () => (state.anisotropyMode === 'ANISOTROPIC_TENSOR' ? validateTensor(state.tensor) : null),
    [state.anisotropyMode, state.tensor],
  );

  const tensorError = useMemo(() => {
    if (!tensorValidation) return null;
    if (!tensorValidation.finite) return 'blast.simulation.tensor.nan_error';
    if (!tensorValidation.symmetric) return 'blast.simulation.tensor.symmetry_error';
    if (!tensorValidation.positiveDefinite) return 'blast.simulation.tensor.not_pd_error';
    return null;
  }, [tensorValidation]);

  const canConfirm = !!request && !tensorError;
  const canRun = !!request && state.confirmed && !mutation.isPending && !tensorError;

  const onSubmit = async () => {
    if (!request) return;
    setResult(null);
    setProfileRequested(null);
    try {
      const data = await mutation.mutateAsync(request);
      setResult(data);
    } catch {
      setResult(null);
    }
  };

  const errorDiag = extractSimulationErrorDiagnostics(mutation.error);

  const requestProfile = () => {
    if (!result) return;
    const start = parseXYZ(state.profileStart);
    const end = parseXYZ(state.profileEnd);
    if (!start || !end) return;
    const n = Math.max(2, Math.min(2000, Number(state.profileSamples) || 100));
    setProfileRequested({
      simulationId: result.simulation_id,
      request: {
        start_x: start[0], start_y: start[1], start_z: start[2],
        end_x: end[0], end_y: end[1], end_z: end[2],
        n_samples: n,
      },
    });
  };

  const profileQueryData = profileRequested ? (
    <ProfileFetcher requested={profileRequested} />
  ) : null;

  const tensorInRequest = state.anisotropyMode === 'ANISOTROPIC_TENSOR';

  return (
    <section className="rounded-lg border p-4 space-y-4" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}>
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">{t('blast.simulation.title')}</h2>
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{t('blast.simulation.subtitle')}</p>
        <p
          className="text-xs px-2 py-1 rounded"
          style={{ backgroundColor: 'var(--status-warn-bg, rgba(230,143,25,0.10))', color: 'var(--status-warn-text, #e68f19)' }}
        >
          ⚠ {t('blast.simulation.warning_uncalibrated')}
        </p>
      </header>

      {!sessionId && (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{t('blast.simulation.no_session')}</p>
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
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{t('blast.simulation.energy_mode_help')}</p>
      </fieldset>

      {tensorInRequest && (
        <TensorEditor
          tensor={state.tensor}
          onChangeCell={updateTensorCell}
          onUseIdentity={useIdentityTensor}
          errorKey={tensorError}
          validation={tensorValidation}
        />
      )}

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t('blast.simulation.kernel_section')}</legend>
        <div className="grid grid-cols-3 gap-2">
          <NumberField label={t('blast.simulation.attenuation')} value={state.attenuation} onChange={(v) => update({ attenuation: v })} />
          <NumberField label={t('blast.simulation.regularization')} value={state.regularization} onChange={(v) => update({ regularization: v })} />
          <NumberField label={t('blast.simulation.coupling')} value={state.coupling} onChange={(v) => update({ coupling: v })} />
          <NumberField label={t('blast.simulation.support_radius')} value={state.supportRadius} onChange={(v) => update({ supportRadius: v })} />
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

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t('blast.simulation.profile.title')}</legend>
        <div className="grid grid-cols-3 gap-2">
          <TextField label={t('blast.simulation.profile.start_end')} value={state.profileStart} onChange={(v) => update({ profileStart: v })} />
          <TextField label={t('blast.simulation.profile.start_end')} value={state.profileEnd} onChange={(v) => update({ profileEnd: v })} />
          <NumberField label={t('blast.simulation.profile.n_samples')} value={state.profileSamples} onChange={(v) => update({ profileSamples: v })} />
        </div>
        <button
          type="button"
          onClick={requestProfile}
          disabled={!result || !parseXYZ(state.profileStart) || !parseXYZ(state.profileEnd)}
          className="px-3 py-1.5 rounded text-sm"
          style={{
            backgroundColor: 'var(--color-mine-blue)',
            color: 'var(--color-surface)',
            opacity: !result || !parseXYZ(state.profileStart) || !parseXYZ(state.profileEnd) ? 0.5 : 1,
          }}
          data-testid="sim-profile-button"
        >
          {t('blast.simulation.profile.run_button')}
        </button>
      </fieldset>

      {tensorInRequest && state.tensor.some((v) => v !== 0) && (
        <details className="text-xs">
          <summary style={{ color: 'var(--color-text-secondary)', cursor: 'pointer' }}>
            {t('blast.simulation.tensor.summary_label')}
          </summary>
          <pre
            className="mt-1 p-2 rounded font-mono"
            style={{ backgroundColor: 'var(--color-surface-sunken)', color: 'var(--color-text-secondary)', borderColor: 'var(--color-border)', borderWidth: 1 }}
          >
{`[ ${state.tensor[0].toFixed(4)}  ${state.tensor[1].toFixed(4)}  ${state.tensor[2].toFixed(4)} ]
[ ${state.tensor[3].toFixed(4)}  ${state.tensor[4].toFixed(4)}  ${state.tensor[5].toFixed(4)} ]
[ ${state.tensor[6].toFixed(4)}  ${state.tensor[7].toFixed(4)}  ${state.tensor[8].toFixed(4)} ]`}
          </pre>
        </details>
      )}

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
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{t('blast.simulation.edit_invalidates')}</p>
        <button
          type="button"
          onClick={onSubmit}
          disabled={!canRun}
          data-testid="sim-run-button"
          className="px-3 py-1.5 rounded disabled:opacity-50"
          style={{ backgroundColor: 'var(--color-mine-blue)', color: 'var(--color-surface)' }}
        >
          {mutation.isPending ? t('blast.simulation.run_pending') : t('blast.simulation.run_button')}
        </button>
      </div>

      {errorDiag && (
        <div
          className="text-sm p-2 rounded"
          style={{ backgroundColor: 'var(--status-nok-bg, rgba(232,49,73,0.10))', color: 'var(--status-nok-text, #e83149)' }}
        >
          <strong>{errorDiag.error_code}</strong>: {errorDiag.message || t('blast.simulation.missing_field')}
        </div>
      )}

      {result && (
        <SimulationResultView result={result} />
      )}

      {profileQueryData}

      <p className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }} data-testid="sim-fingerprint">
        fp:{confirmedFingerprint.slice(0, 12)}
      </p>
    </section>
  );
}

function TensorEditor({
  tensor,
  onChangeCell,
  onUseIdentity,
  errorKey,
  validation,
}: {
  tensor: Tensor;
  onChangeCell: (idx: number, value: number) => void;
  onUseIdentity: () => void;
  errorKey: string | null;
  validation: TensorValidation | null;
}) {
  const { t } = useTranslation();
  const cellValue = (idx: number): string => {
    const v = tensor[idx];
    return Number.isFinite(v) ? String(v) : EMPTY;
  };

  return (
    <fieldset
      className="space-y-2 p-3 rounded border"
      style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface-sunken)' }}
      data-testid="sim-tensor-editor"
    >
      <div className="flex items-center justify-between">
        <legend className="text-sm font-medium">{t('blast.simulation.tensor.title')}</legend>
        <button
          type="button"
          onClick={onUseIdentity}
          className="text-xs px-2 py-1 rounded"
          style={{
            borderWidth: 1,
            borderColor: 'var(--color-border-strong)',
            backgroundColor: 'var(--color-surface-raised)',
            color: 'var(--color-text-secondary)',
          }}
          data-testid="sim-tensor-identity"
        >
          {t('blast.simulation.tensor.identity_hint')}
        </button>
      </div>
      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {t('blast.simulation.tensor.identity_help')}
      </p>
      <div className="grid grid-cols-3 gap-2">
        {([0, 1, 2, 3, 4, 5, 6, 7, 8] as const).map((idx) => (
          <NumberField
            key={idx}
            label={t('blast.simulation.tensor.cell_label', { row: Math.floor(idx / 3) + 1, col: (idx % 3) + 1 })}
            value={cellValue(idx)}
            onChange={(v) => {
              const n = Number(v);
              onChangeCell(idx, Number.isFinite(n) ? n : Number.NaN);
            }}
          />
        ))}
      </div>
      {errorKey && (
        <p
          className="text-xs"
          style={{ color: 'var(--status-nok-text, #e83149)' }}
          data-testid="sim-tensor-error"
        >
          {t(errorKey)}
        </p>
      )}
      {validation?.positiveDefinite && (
        <p
          className="text-xs font-mono"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('blast.simulation.tensor.minors_label')}: d₁={validation.minors.d1.toExponential(2)},
          d₂={validation.minors.d2.toExponential(2)},
          d₃={validation.minors.d3.toExponential(2)}
        </p>
      )}
    </fieldset>
  );
}

function ProfileFetcher({ requested }: { requested: { simulationId: string; request: ProfileRequest } }) {
  const query = useQuery<ProfileResponse>({
    queryKey: ['blast-simulation-profile', requested.simulationId, requested.request],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set('start_x', String(requested.request.start_x));
      params.set('start_y', String(requested.request.start_y));
      params.set('start_z', String(requested.request.start_z));
      params.set('end_x', String(requested.request.end_x));
      params.set('end_y', String(requested.request.end_y));
      params.set('end_z', String(requested.request.end_z));
      params.set('n_samples', String(requested.request.n_samples));
      const { data } = await client.get<ProfileResponse>(
        `/blast/simulations/${requested.simulationId}/profile?${params.toString()}`,
      );
      return data;
    },
    enabled: true,
  });
  if (query.data) return <ProfileChart profile={query.data} />;
  return null;
}

function SimulationResultView({ result }: { result: SimulationCreateResponse }) {
  const { t } = useTranslation();
  const unitLabel = result.grid_metadata.energy_unit === 'J'
    ? t('blast.simulation.energy_unit_j')
    : t('blast.simulation.energy_unit_dimensionless');
  return (
    <div className="space-y-3 border-t pt-3" style={{ borderColor: 'var(--color-border)' }} data-testid="sim-result">
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
      </dl>

      {result.blocking_errors.length > 0 && (
        <div
          className="text-sm p-2 rounded"
          style={{ backgroundColor: 'var(--status-nok-bg, rgba(232,49,73,0.10))', color: 'var(--status-nok-text, #e83149)' }}
        >
          <strong>{t('blast.simulation.blocking_errors_title')}</strong>
          <ul className="list-disc ml-4">
            {result.blocking_errors.map((b: BlockingError, i: number) => (
              <li key={i}>{b.error_code}: {b.message}</li>
            ))}
          </ul>
        </div>
      )}

      {result.warnings.length > 0 && (
        <div
          className="text-sm p-2 rounded"
          style={{ backgroundColor: 'var(--status-warn-bg, rgba(230,143,25,0.10))', color: 'var(--status-warn-text, #e68f19)' }}
        >
          <strong>{t('blast.simulation.warnings_title')}</strong>
          <ul className="list-disc ml-4">
            {result.warnings.map((w, i: number) => (
              <li key={i}>{typeof w === 'string' ? w : JSON.stringify(w)}</li>
            ))}
          </ul>
        </div>
      )}

      <SliceGrid
        title={t('blast.simulation.map.title')}
        slices={result.plan_slices}
        emptyMessage={t('blast.simulation.no_plan_slices')}
        unitLabel={unitLabel}
      />

      <SliceGrid
        title={t('blast.simulation.section_slices_title')}
        slices={result.section_slices}
        emptyMessage={t('blast.simulation.no_section_slices')}
        unitLabel={unitLabel}
      />

      <ProvenanceBlock result={result} unitLabel={unitLabel} />
    </div>
  );
}

function SliceGrid({
  title,
  slices,
  emptyMessage,
  unitLabel,
}: {
  title: string;
  slices: Array<PlanSliceWire | SectionSliceWire>;
  emptyMessage: string;
  unitLabel: string;
}) {
  return (
    <div data-testid="sim-slice-grid">
      <h4 className="text-sm font-medium">{title}</h4>
      {slices.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{emptyMessage}</p>
      ) : (
        <div className="space-y-3">
          {slices.map((s, i: number) => {
            const values = s.values ?? [];
            const max = s.max ?? s.max_value ?? 0;
            const mean = s.mean ?? s.mean_value ?? 0;
            const min = s.min ?? 0;
            const sourceProjection = s.source_holes_projection ?? [];
            const validMask = s.valid_mask ?? values.map(() => true);
            const normalizedSlice = {
              grid_shape: s.grid_shape,
              values,
              x_coordinates_m: s.x_coordinates_m ?? [],
              y_coordinates_m: s.y_coordinates_m ?? [],
              along_coordinates_m: s.along_coordinates_m ?? [],
              vertical_coordinates_m: s.vertical_coordinates_m ?? [],
              valid_mask: validMask,
              min,
              max,
              mean,
              source_holes_projection: sourceProjection,
            };
            return (
              <SliceHeatmap
                key={i}
                slice={normalizedSlice}
                title={
                  s.elevation_m !== undefined
                    ? `z = ${s.elevation_m.toFixed(2)} m`
                    : `${s.axis} = ${(s.coordinate_m ?? 0).toFixed(2)} m`
                }
                xLabel={s.axis === 'x' ? 'Y (m)' : 'X (m)'}
                yLabel={s.elevation_m !== undefined ? 'Y (m)' : 'Z (m)'}
                unitLabel={s.unit === 'J' ? unitLabel : s.unit}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function SliceHeatmap({
  slice,
  title,
  xLabel,
  yLabel,
  unitLabel,
}: {
  slice: {
    grid_shape: [number, number];
    values: number[];
    x_coordinates_m?: number[];
    y_coordinates_m?: number[];
    along_coordinates_m?: number[];
    vertical_coordinates_m?: number[];
    valid_mask?: boolean[];
    min: number;
    max: number;
    mean: number;
    source_holes_projection: Array<Record<string, unknown>>;
  };
  title: string;
  xLabel: string;
  yLabel: string;
  unitLabel: string;
}) {
  const { t } = useTranslation();
  const nx = slice.grid_shape[0] || 1;
  const ny = slice.grid_shape[1] || 1;
  const xCoords = slice.x_coordinates_m ?? slice.along_coordinates_m ?? [];
  const yCoords = slice.y_coordinates_m ?? slice.vertical_coordinates_m ?? [];
  const cellCount = nx * ny;
  const useCanvas = cellCount > 20000;

  const xMin = xCoords[0] ?? 0;
  const xMax = xCoords[nx - 1] ?? 1;
  const yMin = yCoords[0] ?? 0;
  const yMax = yCoords[ny - 1] ?? 1;
  const valueMax = slice.max || 1;
  const valueMin = slice.min || 0;

  const bands = useMemo(() => buildRelativeBands(valueMin, valueMax), [valueMin, valueMax]);

  const width = 480;
  const height = 320;
  const cellW = width / nx;
  const cellH = height / ny;

  const projectHole = (h: Record<string, unknown>): { x: number; y: number; inside: boolean; value: number } | null => {
    let px: number | undefined;
    let py: number | undefined;
    let inside = false;
    let v = 0;
    if (typeof h.x_m === 'number' && typeof h.y_m === 'number') {
      px = h.x_m;
      py = h.y_m;
      inside = Boolean(h.inside_grid);
      v = typeof h.value_at_voxel === 'number' ? h.value_at_voxel : 0;
    } else if (typeof h.i_along === 'number' && typeof h.i_vertical === 'number') {
      px = xCoords[h.i_along];
      py = yCoords[h.i_vertical];
      inside = true;
      v = typeof h.value_at_voxel === 'number' ? h.value_at_voxel : 0;
    } else if (typeof h.ix === 'number' && typeof h.iy === 'number') {
      px = xCoords[h.ix];
      py = yCoords[h.iy];
      inside = true;
      v = typeof h.value_at_voxel === 'number' ? h.value_at_voxel : 0;
    }
    if (px === undefined || py === undefined) return null;
    return { x: px, y: py, inside, value: v };
  };

  const cells = useMemo(() => {
    if (useCanvas) return null;
    const out: Array<{ x: number; y: number; w: number; h: number; fill: string }> = [];
    for (let ix = 0; ix < nx; ix += 1) {
      for (let iy = 0; iy < ny; iy += 1) {
        const v = slice.values[ix * ny + iy] ?? 0;
        const band = classifyBand(v, bands);
        const fill = bandColor(band);
        out.push({
          x: (ix / nx) * width,
          y: height - ((iy + 1) / ny) * height,
          w: cellW + 0.5,
          h: cellH + 0.5,
          fill,
        });
      }
    }
    return out;
  }, [slice.values, nx, ny, bands, width, height, cellW, cellH, useCanvas]);

  return (
    <div
      className="space-y-2 p-2 rounded border"
      style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface-sunken)' }}
      data-testid="sim-slice-heatmap"
    >
      <div className="flex items-center justify-between text-xs">
        <strong style={{ color: 'var(--color-text-primary)' }}>{title}</strong>
        <span style={{ color: 'var(--color-text-muted)' }} className="font-mono">
          {xLabel} × {yLabel} · {t('blast.simulation.map.scale')} {valueMin.toExponential(2)}–{valueMax.toExponential(2)} {unitLabel}
        </span>
      </div>
      {useCanvas ? (
        <CanvasHeatmap
          values={slice.values}
          nx={nx}
          ny={ny}
          width={width}
          height={height}
          bands={bands}
        />
      ) : (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          role="img"
          aria-label={`Heatmap ${title}`}
          style={{ backgroundColor: 'var(--color-surface)', borderRadius: 4 }}
        >
          {cells?.map((c, i) => (
            <rect key={i} x={c.x} y={c.y} width={c.w} height={c.h} fill={c.fill} />
          ))}
          {slice.source_holes_projection.map((h, i) => {
            const p = projectHole(h);
            if (!p) return null;
            const sx = ((p.x - xMin) / (xMax - xMin || 1)) * width;
            const sy = height - ((p.y - yMin) / (yMax - yMin || 1)) * height;
            return (
              <g key={`hole-${i}`}>
                <circle cx={sx} cy={sy} r={3.5} fill="var(--color-accent-bright, #92a9c7)" stroke="var(--color-surface, #0b0f19)" strokeWidth={1} />
                <title>{String(h.hole_id ?? '')} @ {(p.value ?? 0).toExponential(2)} {unitLabel}</title>
              </g>
            );
          })}
        </svg>
      )}
      <SliceLegend bands={bands} unitLabel={unitLabel} />
      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }} data-testid="sim-slice-wells">
        {t('blast.simulation.map.wells_overlay')} ({slice.source_holes_projection.length})
      </p>
    </div>
  );
}

function CanvasHeatmap({
  values,
  nx,
  ny,
  width,
  height,
  bands,
}: {
  values: number[];
  nx: number;
  ny: number;
  width: number;
  height: number;
  bands: RelativeBand[];
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    const cellW = width / nx;
    const cellH = height / ny;
    for (let ix = 0; ix < nx; ix += 1) {
      for (let iy = 0; iy < ny; iy += 1) {
        const v = values[ix * ny + iy] ?? 0;
        const band = classifyBand(v, bands);
        ctx.fillStyle = bandColor(band);
        ctx.fillRect((ix / nx) * width, height - ((iy + 1) / ny) * height, cellW + 0.5, cellH + 0.5);
      }
    }
  }, [values, nx, ny, width, height, bands]);
  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{ backgroundColor: 'var(--color-surface)', borderRadius: 4 }}
      data-testid="sim-slice-canvas"
    />
  );
}

interface RelativeBand {
  threshold: number;
  label: string;
  color: string;
  maxInclusive: boolean;
}

function buildRelativeBands(min: number, max: number): RelativeBand[] {
  const range = max - min;
  return [
    { threshold: min + range * 0.0, label: '0–5 %', color: 'rgba(118,147,183,0.10)', maxInclusive: false },
    { threshold: min + range * 0.05, label: '5–20 %', color: 'rgba(118,147,183,0.30)', maxInclusive: false },
    { threshold: min + range * 0.20, label: '20–50 %', color: 'rgba(57,171,96,0.45)', maxInclusive: false },
    { threshold: min + range * 0.50, label: '50–80 %', color: 'rgba(230,143,25,0.65)', maxInclusive: false },
    { threshold: min + range * 0.80, label: '80–100 %', color: 'rgba(232,49,73,0.85)', maxInclusive: true },
  ];
}

function classifyBand(value: number, bands: RelativeBand[]): RelativeBand {
  for (let i = bands.length - 1; i >= 0; i -= 1) {
    const b = bands[i];
    if (b.maxInclusive ? value >= b.threshold : value > b.threshold) return b;
  }
  return bands[0];
}

function bandColor(b: RelativeBand): string {
  return b.color;
}

function SliceLegend({ bands, unitLabel }: { bands: RelativeBand[]; unitLabel: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 text-xs" data-testid="sim-slice-bands">
      <span style={{ color: 'var(--color-text-muted)' }}>{t('blast.simulation.map.bands')}:</span>
      {bands.map((b, i) => (
        <span key={i} className="flex items-center gap-1">
          <span
            aria-hidden
            style={{
              display: 'inline-block',
              width: 12,
              height: 12,
              backgroundColor: b.color,
              borderColor: 'var(--color-border)',
              borderWidth: 1,
              borderRadius: 2,
            }}
          />
          <span style={{ color: 'var(--color-text-secondary)' }}>{b.label}</span>
        </span>
      ))}
      <span className="ml-2 font-mono" style={{ color: 'var(--color-text-muted)' }}>{unitLabel}</span>
    </div>
  );
}

function ProfileChart({ profile }: { profile: ProfileResponse }) {
  const { t } = useTranslation();
  const w = 480;
  const h = 200;
  const padding = 32;
  const distances = profile.distances_m ?? [];
  const values = profile.values ?? [];
  if (distances.length === 0) {
    return (
      <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {t('blast.simulation.profile.empty')}
      </div>
    );
  }
  const dMin = distances[0];
  const dMax = distances[distances.length - 1];
  const vMin = profile.min;
  const vMax = profile.max === profile.min ? profile.min + 1 : profile.max;
  const dx = (dMax - dMin) || 1;
  const dy = (vMax - vMin) || 1;
  const points = distances.map((d, i) => {
    const v = values[i] ?? 0;
    const x = padding + ((d - dMin) / dx) * (w - 2 * padding);
    const y = h - padding - ((v - vMin) / dy) * (h - 2 * padding);
    return { x, y, v };
  });
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
  const holes = profile.source_holes_projection ?? [];

  return (
    <div
      className="space-y-2 p-2 rounded border"
      style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface-sunken)' }}
      data-testid="sim-profile-chart"
    >
      <div className="flex items-center justify-between text-xs">
        <strong style={{ color: 'var(--color-text-primary)' }}>{t('blast.simulation.profile.title')}</strong>
        <span className="font-mono" style={{ color: 'var(--color-text-muted)' }}>
          min={profile.min.toExponential(2)} · max={profile.max.toExponential(2)} · mean={profile.mean.toExponential(2)} {profile.unit}
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} role="img" aria-label="Profile chart">
        <line x1={padding} y1={h - padding} x2={w - padding} y2={h - padding} stroke="var(--color-border)" />
        <line x1={padding} y1={padding} x2={padding} y2={h - padding} stroke="var(--color-border)" />
        <text x={padding} y={padding - 8} fill="var(--color-text-muted)" fontSize="10">
          {profile.max.toExponential(2)} {profile.unit}
        </text>
        <text x={padding} y={h - 4} fill="var(--color-text-muted)" fontSize="10">
          0 m
        </text>
        <text x={w - padding} y={h - 4} fill="var(--color-text-muted)" fontSize="10" textAnchor="end">
          {dMax.toFixed(1)} m
        </text>
        <path d={path} fill="none" stroke="var(--color-accent-bright, #92a9c7)" strokeWidth={1.5} />
        {holes.map((h2, i) => {
          const x = padding + ((Number(h2.x_m ?? 0) - dMin) / dx) * (w - 2 * padding);
          return (
            <line
              key={i}
              x1={x}
              x2={x}
              y1={padding}
              y2={h - padding}
              stroke="var(--status-warn-border, #e68f19)"
              strokeDasharray="2 2"
            />
          );
        })}
      </svg>
    </div>
  );
}

function ProvenanceBlock({ result, unitLabel }: { result: SimulationCreateResponse; unitLabel: string }) {
  const { t } = useTranslation();
  return (
    <div
      className="space-y-1 text-xs p-2 rounded"
      style={{ backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-secondary)' }}
      data-testid="sim-provenance"
    >
      <strong>{t('blast.simulation.provenance_title')}</strong>
      <p>
        {t('blast.simulation.provenance_engine')}: <span className="font-mono">{result.provenance.engine_version}</span> ·
        {' '}{t('blast.simulation.provenance_config')}: <span className="font-mono">{result.provenance.simulation_configuration_version}</span>
      </p>
      <p>
        {t('blast.simulation.provenance_explosives')}: {result.provenance.explosive_products_used.join(', ') || '—'} ·
        {' '}{t('blast.simulation.provenance_rock_mass')}: <span className="font-mono">{result.provenance.rock_mass_source || '—'}</span>
      </p>
      <p>
        {t('blast.simulation.provenance_velocity')}: <span className="font-mono">{result.provenance.propagation_velocity_source || '—'}</span> ·
        {' '}{t('blast.simulation.provenance_accepted_rows')}: <span className="font-mono">{result.provenance.accepted_rows_hash.slice(0, 12)}…</span>
      </p>
      {result.provenance.assumptions.length > 0 && (
        <p>
          {t('blast.simulation.provenance_assumptions')}: {result.provenance.assumptions.join('; ')}
        </p>
      )}
      <p className="font-mono">
        {t('blast.simulation.npz_sha')}: {result.npz_sha256.slice(0, 16)}… · {unitLabel}
      </p>
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="text-xs space-y-1 block">
      <span className="block" style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
      <input
        type="number"
        step="any"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1 rounded border outline-none"
        style={{
          borderColor: 'var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          color: 'var(--color-text-primary)',
        }}
      />
    </label>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="text-xs space-y-1 block">
      <span className="block" style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1 rounded border outline-none font-mono"
        style={{
          borderColor: 'var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          color: 'var(--color-text-primary)',
        }}
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
      <span className="block" style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-2 py-1 rounded border outline-none"
        style={{
          borderColor: 'var(--color-border)',
          backgroundColor: 'var(--color-surface)',
          color: 'var(--color-text-primary)',
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}