import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUploadBlastCsv, useBlastHolesBySession, type BlastGeometryForm } from '../../api/hooks';
import { getSessionId } from '../../api/client';
import type { BlastUploadResponse, BlockingError, RejectedRow } from '../../api/types';

export interface BlastUploaderProps {
  onUploaded?: (response: BlastUploadResponse) => void;
}

const INCL_CONVENTIONS = ['from_vertical', 'dip_from_horizontal'] as const;
const SIGN_CONVENTIONS = [
  'ABSOLUTE_VALUE',
  'NEGATIVE_IS_DOWNWARD_DIP',
  'SOURCE_DEFINED',
] as const;
const AZ_CONVENTIONS = [
  'CLOCKWISE_FROM_NORTH',
  'COUNTERCLOCKWISE_FROM_NORTH',
  'CLOCKWISE_FROM_EAST',
  'COUNTERCLOCKWISE_FROM_EAST',
] as const;
const UNITS = ['degrees', 'radians'] as const;
const SOURCE_RULES = ['negative_is_downward_dip', 'positive_only', 'absolute_value'] as const;

interface GeometryState {
  confirmed: boolean;
  inclinationSourceColumn: string;
  inclinationConvention: (typeof INCL_CONVENTIONS)[number] | '';
  inclinationSignConvention: (typeof SIGN_CONVENTIONS)[number];
  inclinationUnit: (typeof UNITS)[number];
  inclinationSourceRule: (typeof SOURCE_RULES)[number];
  azimuthSourceColumn: string;
  azimuthConvention: (typeof AZ_CONVENTIONS)[number];
  azimuthUnit: (typeof UNITS)[number];
  benchHeightM: string;
}

const DEFAULT_STATE: GeometryState = {
  confirmed: false,
  inclinationSourceColumn: '',
  inclinationConvention: '',
  inclinationSignConvention: 'ABSOLUTE_VALUE',
  inclinationUnit: 'degrees',
  inclinationSourceRule: 'negative_is_downward_dip',
  azimuthSourceColumn: '',
  azimuthConvention: 'CLOCKWISE_FROM_NORTH',
  azimuthUnit: 'degrees',
  benchHeightM: '',
};

/**
 * Build the BlastGeometryForm from the visible state. Returns null when
 * the contract is incomplete — the caller MUST block submission then.
 *
 * INTEGRACIÓN §4.1: editing any option after confirming invalidates the
 * confirmation (we recompute validity live here, and the form below
 * unchecks the box when a field changes).
 */
function buildGeometry(state: GeometryState): BlastGeometryForm | null {
  if (!state.confirmed) return null;
  if (!state.inclinationSourceColumn.trim()) return null;
  if (!state.azimuthSourceColumn.trim()) return null;
  if (!state.inclinationConvention) return null;
  if (
    state.inclinationSignConvention === 'SOURCE_DEFINED' &&
    !state.inclinationSourceRule
  ) {
    return null;
  }
  return {
    geometry_user_confirmed: true,
    inclination_source_column: state.inclinationSourceColumn.trim(),
    inclination_convention: state.inclinationConvention,
    inclination_sign_convention: state.inclinationSignConvention,
    inclination_unit: state.inclinationUnit,
    inclination_source_rule:
      state.inclinationSignConvention === 'SOURCE_DEFINED'
        ? state.inclinationSourceRule
        : '',
    azimuth_source_column: state.azimuthSourceColumn.trim(),
    azimuth_convention: state.azimuthConvention,
    azimuth_unit: state.azimuthUnit,
    bench_height_m: state.benchHeightM ? Number(state.benchHeightM) : undefined,
  };
}

export function BlastUploader({ onUploaded }: BlastUploaderProps) {
  const { t } = useTranslation();
  const sessionId = getSessionId();
  const upload = useUploadBlastCsv();
  const holes = useBlastHolesBySession(sessionId ?? null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [state, setState] = useState<GeometryState>(DEFAULT_STATE);

  // INTEGRACIÓN §4.1: editing any option after confirming invalidates the
  // confirmation — the operator must re-tick the checkbox.
  const update = <K extends keyof GeometryState>(key: K, value: GeometryState[K]) => {
    setState((prev) => ({
      ...prev,
      [key]: value,
      // Any edit clears the confirmation; the user must re-confirm.
      confirmed: key === 'confirmed' ? (value as boolean) : false,
    }));
  };

  const geometry: BlastGeometryForm | null = useMemo(() => buildGeometry(state), [state]);
  const canSubmit = Boolean(sessionId) && geometry !== null && !upload.isPending;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !sessionId || !geometry) return;
    setFilename(file.name);
    try {
      const result = await upload.mutateAsync({ sessionId, file, geometry });
      onUploaded?.(result);
    } catch {
      // Error state surfaced via upload.isError below.
    }
  };

  const blockingErrors: BlockingError[] = upload.data?.blocking_errors ?? [];
  const rejectedRows: RejectedRow[] = upload.data?.rejected_rows ?? [];
  const unitsMismatch = state.inclinationUnit !== state.azimuthUnit;

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border p-4"
      style={{
        borderColor: 'var(--color-border)',
        backgroundColor: 'var(--color-surface-muted)',
      }}
      data-testid="blast-uploader"
    >
      <h3
        className="text-sm font-semibold"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {t('blast.upload_title')}
      </h3>

      <details className="text-xs" data-testid="geometry-contract-form">
        <summary className="cursor-pointer font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          {t('blast.geometry_contract', { defaultValue: 'Contrato geométrico (obligatorio)' })}
        </summary>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_source_col', { defaultValue: 'Columna fuente de inclinación' })}</span>
            <input
              type="text"
              value={state.inclinationSourceColumn}
              onChange={(e) => update('inclinationSourceColumn', e.target.value)}
              placeholder="Inclinacion_real"
              data-testid="incl-source-column"
              className="rounded border px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>{t('blast.az_source_col', { defaultValue: 'Columna fuente de azimut' })}</span>
            <input
              type="text"
              value={state.azimuthSourceColumn}
              onChange={(e) => update('azimuthSourceColumn', e.target.value)}
              placeholder="Azimuth_real"
              data-testid="az-source-column"
              className="rounded border px-2 py-1"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_convention', { defaultValue: 'Convención de inclinación' })}</span>
            <select
              value={state.inclinationConvention}
              onChange={(e) => update('inclinationConvention', e.target.value as GeometryState['inclinationConvention'])}
              data-testid="incl-convention"
              className="rounded border px-2 py-1"
            >
              <option value="">—</option>
              {INCL_CONVENTIONS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_sign', { defaultValue: 'Política de signo' })}</span>
            <select
              value={state.inclinationSignConvention}
              onChange={(e) => update('inclinationSignConvention', e.target.value as GeometryState['inclinationSignConvention'])}
              data-testid="incl-sign"
              className="rounded border px-2 py-1"
            >
              {SIGN_CONVENTIONS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          {state.inclinationSignConvention === 'SOURCE_DEFINED' && (
            <label className="flex flex-col gap-1 col-span-2">
              <span>{t('blast.source_rule', { defaultValue: 'Regla (obligatoria para SOURCE_DEFINED)' })}</span>
              <select
                value={state.inclinationSourceRule}
                onChange={(e) => update('inclinationSourceRule', e.target.value as GeometryState['inclinationSourceRule'])}
                data-testid="source-rule"
                className="rounded border px-2 py-1"
              >
                {SOURCE_RULES.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_unit', { defaultValue: 'Unidad de inclinación' })}</span>
            <select
              value={state.inclinationUnit}
              onChange={(e) => update('inclinationUnit', e.target.value as GeometryState['inclinationUnit'])}
              data-testid="incl-unit"
              className="rounded border px-2 py-1"
            >
              {UNITS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span>{t('blast.az_unit', { defaultValue: 'Unidad de azimut' })}</span>
            <select
              value={state.azimuthUnit}
              onChange={(e) => update('azimuthUnit', e.target.value as GeometryState['azimuthUnit'])}
              data-testid="az-unit"
              className="rounded border px-2 py-1"
            >
              {UNITS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span>{t('blast.az_convention', { defaultValue: 'Convención de azimut' })}</span>
            <select
              value={state.azimuthConvention}
              onChange={(e) => update('azimuthConvention', e.target.value as GeometryState['azimuthConvention'])}
              data-testid="az-convention"
              className="rounded border px-2 py-1"
            >
              {AZ_CONVENTIONS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span>{t('blast.bench_height', { defaultValue: 'Altura de banco (m)' })}</span>
            <input
              type="number"
              min="0"
              step="0.1"
              value={state.benchHeightM}
              onChange={(e) => update('benchHeightM', e.target.value)}
              data-testid="bench-height"
              className="rounded border px-2 py-1"
            />
          </label>
          <label className="col-span-2 flex items-center gap-2 mt-1" data-testid="confirm-row">
            <input
              type="checkbox"
              checked={state.confirmed}
              onChange={(e) => update('confirmed', e.target.checked)}
              data-testid="geometry-confirmed"
            />
            <span>
              {t('blast.confirm_geometry', {
                defaultValue:
                  'He revisado y confirmo la configuración geométrica (habilita el cálculo).',
              })}
            </span>
          </label>
        </div>
        {unitsMismatch && (
          <p className="mt-2 text-xs" role="alert" style={{ color: 'var(--color-status-error, #ef4444)' }}>
            {t('blast.units_mismatch', {
              defaultValue:
                'Las unidades de inclinación y azimut difieren. La API Form actual requiere que coincidan; use la unidad común.',
            })}
          </p>
        )}
      </details>

      <input
        ref={fileInputRef}
        type="file"
        accept=".csv"
        data-testid="blast-file-input"
        onChange={handleFileChange}
        disabled={!canSubmit}
        className="text-xs file:mr-3 file:rounded-md file:border-0 file:bg-[var(--color-accent)] file:px-3 file:py-1.5 file:text-white file:transition-colors disabled:opacity-50"
        style={{ color: 'var(--color-text-primary)' }}
      />
      {!sessionId && (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.upload_no_session', { defaultValue: 'Inicie una sesión para cargar pozos.' })}
        </p>
      )}
      {sessionId && !geometry && (
        <p className="text-xs" role="alert" style={{ color: 'var(--color-status-error, #ef4444)' }}>
          {t('blast.contract_required', {
            defaultValue:
              'Complete y confirme el contrato geométrico antes de cargar el CSV.',
          })}
        </p>
      )}
      {filename && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {t('blast.file_selected', { filename })}
        </p>
      )}
      {upload.isPending && (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.uploading')}
        </p>
      )}
      {upload.isError && (
        <div className="text-xs" role="alert" data-testid="upload-error" style={{ color: 'var(--color-status-error, #ef4444)' }}>
          {t('blast.upload_error', { error: String(upload.error) })}
        </div>
      )}
      {blockingErrors.length > 0 && (
        <div className="text-xs" data-testid="blocking-errors" style={{ color: 'var(--color-status-error, #ef4444)' }}>
          <strong>{t('blast.blocking_errors', { defaultValue: 'Errores bloqueantes:' })}</strong>
          <ul className="ml-4 list-disc">
            {blockingErrors.map((err, idx) => (
              <li key={idx}>
                <code>{err.error_code}</code>: {err.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {rejectedRows.length > 0 && (
        <div className="text-xs" data-testid="rejected-rows" style={{ color: 'var(--color-status-warning, #b45309)' }}>
          <strong>{t('blast.rejected_rows', { defaultValue: 'Filas rechazadas:' })}</strong>
          <ul className="ml-4 list-disc">
            {rejectedRows.slice(0, 10).map((r, idx) => (
              <li key={idx}>
                <code>{r.error_code}</code> ({r.source_column} fila {r.source_row_index}):{' '}
                {r.rejection_reason}
              </li>
            ))}
            {rejectedRows.length > 10 && (
              <li>… +{rejectedRows.length - 10} más</li>
            )}
          </ul>
        </div>
      )}
      {upload.isSuccess && upload.data && (
        <div data-testid="blast-upload-summary">
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {t('blast.upload_summary', { n: upload.data.n_holes, skipped: upload.data.n_rows_skipped })}
          </p>
          {upload.data.carga_mean != null && (
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              {t('blast.carga_mean', { value: upload.data.carga_mean.toFixed(2) })}
            </p>
          )}
          {upload.data.descarga_mean != null && (
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              {t('blast.descarga_mean', { value: upload.data.descarga_mean.toFixed(2) })}
            </p>
          )}
        </div>
      )}
      {holes.data && (
        <p className="text-xs" data-testid="blast-hole-count" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.persisted_count', { n: holes.data.holes.length })}
        </p>
      )}
    </section>
  );
}
