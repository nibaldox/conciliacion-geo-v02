import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useUploadBlastCsv,
  useBlastHolesBySession,
  extractBlastErrorDiagnostics,
  type BlastGeometryForm,
} from '../../api/hooks';
import { getSessionId } from '../../api/client';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import type { BlastUploadResponse, BlockingError, RejectedRow } from '../../api/types';
import { GEOMETRY_CONFIGURATION_VERSION } from '../../api/types';
import { Button } from '../ui/Button';
import { PROJECT_INPUT_CLASS } from '../ui/ProjectControls';
import { BlastInfoTip } from './blastLayout';

export interface BlastUploaderProps {
  onUploaded?: (response: BlastUploadResponse) => void;
  collapsible?: boolean;
}

function StatusLine({ tone, children, ...rest }: { tone: 'nok' | 'warn'; children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className="flex items-start gap-2 text-xs text-text-secondary" {...rest}>
      <span aria-hidden="true" className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: `var(--status-${tone}-text)` }} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

const INCL_CONVENTIONS = ['FROM_VERTICAL', 'DIP_FROM_HORIZONTAL'] as const;
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
const UNITS = ['DEGREES', 'RADIANS'] as const;
const SOURCE_RULES = ['negative_is_downward_dip', 'positive_only', 'absolute_value'] as const;
const CSV_HEADER_READ_LIMIT = 64 * 1024;

function parseCsvHeader(text: string): string[] {
  const firstLine = text.replace(/^\uFEFF/, '').split(/\r?\n/, 1)[0] ?? '';
  const columns: string[] = [];
  let value = '';
  let quoted = false;
  for (let index = 0; index < firstLine.length; index += 1) {
    const character = firstLine[index];
    if (character === '"' && quoted && firstLine[index + 1] === '"') {
      value += '"';
      index += 1;
    } else if (character === '"') {
      quoted = !quoted;
    } else if (character === ',' && !quoted) {
      columns.push(value.trim());
      value = '';
    } else {
      value += character;
    }
  }
  columns.push(value.trim());
  return [...new Set(columns.filter(Boolean))];
}

function readCsvHeader(file: File): Promise<string[]> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const rawBytes = new Uint8Array(reader.result as ArrayBuffer);
        const hasUtf8Bom = rawBytes.length >= 3 && rawBytes[0] === 0xef && rawBytes[1] === 0xbb && rawBytes[2] === 0xbf;
        const bytes = hasUtf8Bom ? rawBytes.subarray(3) : rawBytes;
        const utf8 = new TextDecoder('utf-8', { fatal: true });
        let decoded: string;
        try {
          decoded = utf8.decode(bytes);
        } catch {
          decoded = new TextDecoder('windows-1252').decode(bytes);
        }
        resolve(parseCsvHeader(decoded));
      } catch {
        resolve([]);
      }
    };
    reader.onerror = () => resolve([]);
    reader.readAsArrayBuffer(file.slice(0, CSV_HEADER_READ_LIMIT));
  });
}

type Empty = '';
type Option<T extends string> = T | Empty;

interface GeometryState {
  confirmed: boolean;
  inclinationSourceColumn: string;
  inclinationConvention: Option<(typeof INCL_CONVENTIONS)[number]>;
  inclinationSignConvention: Option<(typeof SIGN_CONVENTIONS)[number]>;
  inclinationUnit: Option<(typeof UNITS)[number]>;
  inclinationSourceRule: Option<(typeof SOURCE_RULES)[number]>;
  azimuthSourceColumn: string;
  azimuthConvention: Option<(typeof AZ_CONVENTIONS)[number]>;
  azimuthUnit: Option<(typeof UNITS)[number]>;
  benchHeightM: string;
  collarElevationSource: 'bench_height' | 'design_surface';
  spatialReferenceConfirmed: boolean;
}

// INTEGRACIÓN §5.3 — NO defaults are pre-selected. Every field begins
// empty so the operator MUST consciously select each option before
// confirmation is allowed.
const DEFAULT_STATE: GeometryState = {
  confirmed: false,
  inclinationSourceColumn: '',
  inclinationConvention: '',
  inclinationSignConvention: '',
  inclinationUnit: '',
  inclinationSourceRule: '',
  azimuthSourceColumn: '',
  azimuthConvention: '',
  azimuthUnit: '',
  benchHeightM: '',
  collarElevationSource: 'design_surface',
  spatialReferenceConfirmed: false,
};

/**
 * Build the BlastGeometryForm from the visible state. Returns null when
 * the contract is incomplete — the caller MUST block submission then.
 *
 * INTEGRACIÓN §5.3: no default values are silently promoted to a
 * confirmed decision. Empty options invalidate the contract.
 */
function buildGeometry(state: GeometryState): BlastGeometryForm | null {
  if (!state.confirmed) return null;
  if (!state.inclinationSourceColumn.trim()) return null;
  if (!state.azimuthSourceColumn.trim()) return null;
  if (!state.inclinationConvention) return null;
  if (!state.inclinationSignConvention) return null;
  if (!state.inclinationUnit) return null;
  if (!state.azimuthConvention) return null;
  if (!state.azimuthUnit) return null;
  if (state.inclinationConvention === 'FROM_VERTICAL' && state.inclinationSignConvention === 'NEGATIVE_IS_DOWNWARD_DIP') return null;
  if (state.collarElevationSource === 'design_surface' && !state.spatialReferenceConfirmed) return null;
  if (
    state.inclinationSignConvention === 'SOURCE_DEFINED' &&
    !state.inclinationSourceRule
  ) {
    return null;
  }
  return {
    geometry_configuration_version: GEOMETRY_CONFIGURATION_VERSION,
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
    bench_height_m: state.collarElevationSource === 'bench_height' && state.benchHeightM ? Number(state.benchHeightM) : undefined,
    ...(state.collarElevationSource === 'design_surface'
      ? { collar_elevation_source: 'design_surface' as const, spatial_reference_confirmed: true }
      : {}),
  };
}

export function BlastUploader({ onUploaded, collapsible = false }: BlastUploaderProps) {
  const { t } = useTranslation();
  const { designMeshId, topoMeshId } = useSession();
  const hasVirtualMesh = (
    designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo
  );
  const sessionId = getSessionId();
  const upload = useUploadBlastCsv();
  const holes = useBlastHolesBySession(hasVirtualMesh ? null : sessionId ?? null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const contractRef = useRef<HTMLDetailsElement>(null);
  const headerReadVersion = useRef(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceColumns, setSourceColumns] = useState<string[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploadPhase, setUploadPhase] = useState<'transfer' | 'processing' | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const filename = selectedFile?.name ?? null;
  const [state, setState] = useState<GeometryState>(DEFAULT_STATE);

  // INTEGRACIÓN §5.3/§5.4: editing any option after confirming invalidates
  // the confirmation — the operator must re-tick the checkbox. This does
  // NOT depend on the visual state of the checkbox; it is enforced by
  // the reducer below.
  const update = <K extends keyof GeometryState>(key: K, value: GeometryState[K]) => {
    setState((prev) => ({
      ...prev,
      [key]: value,
      confirmed: key === 'confirmed' ? (value as boolean) : false,
    }));
  };

  const geometry: BlastGeometryForm | null = useMemo(() => buildGeometry(state), [state]);
  const sourceColumnsValid = sourceColumns.length === 0 || (
    sourceColumns.includes(state.inclinationSourceColumn) && sourceColumns.includes(state.azimuthSourceColumn)
  );
  const canSubmit = !hasVirtualMesh && Boolean(sessionId) && selectedFile !== null && geometry !== null && !upload.isPending && sourceColumnsValid;

  // INTEGRACIÓN §5.4 — extract structured diagnostics from HTTP 400/422
  // error responses (AxiosError.response.data) so the operator sees the
  // same rejected_rows / blocking_errors that a 200 would carry.
  const errorDiagnostics = useMemo(
    () => (upload.isError ? extractBlastErrorDiagnostics(upload.error) : null),
    [upload.isError, upload.error],
  );
  const errorBlockingErrors: BlockingError[] = errorDiagnostics?.blocking_errors ?? [];
  const errorRejectedRows: RejectedRow[] = errorDiagnostics?.rejected_rows ?? [];

  // Successful responses (200) and structured error responses (400/422)
  // share the SAME diagnostics surface so the UI renders them in the
  // same component regardless of status code.
  const successBlockingErrors: BlockingError[] = upload.data?.blocking_errors ?? [];
  const successRejectedRows: RejectedRow[] = upload.data?.rejected_rows ?? [];
  const blockingErrors: BlockingError[] = upload.isError
    ? errorBlockingErrors
    : successBlockingErrors;
  const rejectedRows: RejectedRow[] = upload.isError ? errorRejectedRows : successRejectedRows;
  const diagnostics = upload.isError ? errorDiagnostics : upload.data;
  const eventWarningMessages = (diagnostics?.event_warnings ?? []).map((warning) =>
    typeof warning.message === 'string'
      ? warning.message
      : t('blast.event_warning_generic', { defaultValue: 'Revise las advertencias de los datos de tronadura.' }),
  );

  if (hasVirtualMesh) {
    return (
      <section className="flex flex-col gap-2 text-left" data-testid="blast-uploader">
        <h3 className="ui-section-title">
          {t('blast.upload_title')}
        </h3>
        <p className="text-xs leading-relaxed text-text-muted" role="status" data-testid="blast-demo-notice">
          {t('blast.demo_upload_unavailable', {
            defaultValue: 'La demo usa mallas virtuales y no incluye datos de tronadura. La carga está disponible en una sesión real.',
          })}
        </p>
      </section>
    );
  }

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setFileError(t('blast.csv_required'));
      return;
    }
    setFileError(null);
    setSelectedFile(file);
    setSourceColumns([]);
    const readVersion = headerReadVersion.current + 1;
    headerReadVersion.current = readVersion;
    void readCsvHeader(file).then((columns) => {
      if (headerReadVersion.current === readVersion) setSourceColumns(columns);
    });
    upload.reset?.();
    update('confirmed', false);
    if (contractRef.current) contractRef.current.open = true;
  };

  const handleUpload = async () => {
    if (hasVirtualMesh || !selectedFile || !sessionId || !geometry || upload.isPending) return;
    setUploadPhase('transfer');
    setUploadProgress(0);
    try {
      const result = await upload.mutateAsync({
        sessionId,
        file: selectedFile,
        geometry,
        onUploadProgress: (progress) => {
          if (progress == null) return;
          setUploadProgress(progress);
          if (progress >= 100) setUploadPhase('processing');
        },
      });
      setUploadPhase(null);
      onUploaded?.(result);
    } catch {
      setUploadPhase(null);
      return;
    }
  };

  const title = (
    <span className="flex items-center gap-2">
      <span className="ui-section-title">{t('blast.upload_title')}</span>
      <BlastInfoTip>{t('blast.upload_steps')}</BlastInfoTip>
    </span>
  );

  const body = (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={() => fileInputRef.current?.click()} disabled={upload.isPending} data-testid="blast-file-picker">{t('blast.choose_csv')}</Button>
        {filename && <span className="min-w-0 break-all font-mono text-xs text-text-secondary">{t('blast.file_selected', { filename })}</span>}
      </div>
      <input ref={fileInputRef} type="file" accept=".csv,text/csv" data-testid="blast-file-input" onChange={handleFileChange} disabled={upload.isPending} className="hidden" />
      {fileError && <StatusLine tone="nok" role="alert">{fileError}</StatusLine>}

      <details ref={contractRef} className="group text-xs" data-testid="geometry-contract-form">
        <summary className="cursor-pointer text-xs font-medium text-text-secondary hover:text-text-primary">
          {t('blast.geometry_contract', { defaultValue: 'Contrato geométrico (obligatorio)' })}
        </summary>
        <div className="mt-3 grid grid-cols-1 gap-3 text-text-muted sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_source_col', { defaultValue: 'Columna fuente de inclinación' })}</span>
            {sourceColumns.length > 0 ? (
              <select value={state.inclinationSourceColumn} onChange={(e) => update('inclinationSourceColumn', e.target.value)} data-testid="incl-source-column" aria-invalid={Boolean(state.inclinationSourceColumn && !sourceColumns.includes(state.inclinationSourceColumn))} className={PROJECT_INPUT_CLASS}>
                <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
                {state.inclinationSourceColumn && !sourceColumns.includes(state.inclinationSourceColumn) && <option value={state.inclinationSourceColumn}>{state.inclinationSourceColumn}</option>}
                {sourceColumns.map((column) => <option key={column} value={column}>{column}</option>)}
              </select>
            ) : (
              <input type="text" value={state.inclinationSourceColumn} onChange={(e) => update('inclinationSourceColumn', e.target.value)} placeholder="Inclinacion_real" data-testid="incl-source-column" className={PROJECT_INPUT_CLASS} />
            )}
          </label>
          {sourceColumns.length > 0 && state.inclinationSourceColumn && !sourceColumns.includes(state.inclinationSourceColumn) && (
            <p className="sm:col-span-2 text-xs text-text-muted" role="status">{t('blast.source_column_missing', { column: state.inclinationSourceColumn, defaultValue: 'La columna «{{column}}» no está en el encabezado del archivo seleccionado. Elija una columna disponible.' })}</p>
          )}
          {state.inclinationConvention === 'FROM_VERTICAL' && state.inclinationSignConvention === 'NEGATIVE_IS_DOWNWARD_DIP' && (
            <StatusLine tone="nok" className="flex items-start gap-2 text-xs text-text-secondary sm:col-span-2" role="alert">
              {t('blast.inclination_convention_sign_incompatible', { defaultValue: 'La convención desde la vertical no es compatible con la regla «negativo indica buzamiento descendente». Seleccione buzamiento desde la horizontal o una política de signo compatible.' })}
            </StatusLine>
          )}
          <label className="flex flex-col gap-1">
            <span>{t('blast.az_source_col', { defaultValue: 'Columna fuente de azimut' })}</span>
            {sourceColumns.length > 0 ? (
              <select value={state.azimuthSourceColumn} onChange={(e) => update('azimuthSourceColumn', e.target.value)} data-testid="az-source-column" aria-invalid={Boolean(state.azimuthSourceColumn && !sourceColumns.includes(state.azimuthSourceColumn))} className={PROJECT_INPUT_CLASS}>
                <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
                {state.azimuthSourceColumn && !sourceColumns.includes(state.azimuthSourceColumn) && <option value={state.azimuthSourceColumn}>{state.azimuthSourceColumn}</option>}
                {sourceColumns.map((column) => <option key={column} value={column}>{column}</option>)}
              </select>
            ) : (
              <input type="text" value={state.azimuthSourceColumn} onChange={(e) => update('azimuthSourceColumn', e.target.value)} placeholder="Azimuth_real" data-testid="az-source-column" className={PROJECT_INPUT_CLASS} />
            )}
          </label>
          {sourceColumns.length > 0 && state.azimuthSourceColumn && !sourceColumns.includes(state.azimuthSourceColumn) && (
            <p className="sm:col-span-2 text-xs text-text-muted" role="status">{t('blast.source_column_missing', { column: state.azimuthSourceColumn, defaultValue: 'La columna «{{column}}» no está en el encabezado del archivo seleccionado. Elija una columna disponible.' })}</p>
          )}
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_convention', { defaultValue: 'Convención de inclinación' })}</span>
            <select
              value={state.inclinationConvention}
              onChange={(e) => update('inclinationConvention', e.target.value as GeometryState['inclinationConvention'])}
              data-testid="incl-convention"
              className={PROJECT_INPUT_CLASS}
            >
              <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
              {INCL_CONVENTIONS.map((v) => (
                <option key={v} value={v}>{t('blast.geometry_options.' + v)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_sign', { defaultValue: 'Política de signo' })}</span>
            <select
              value={state.inclinationSignConvention}
              onChange={(e) => update('inclinationSignConvention', e.target.value as GeometryState['inclinationSignConvention'])}
              data-testid="incl-sign"
              className={PROJECT_INPUT_CLASS}
            >
              <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
              {SIGN_CONVENTIONS.map((v) => (
                <option key={v} value={v}>{t('blast.geometry_options.' + v)}</option>
              ))}
            </select>
          </label>
          {state.inclinationSignConvention === 'SOURCE_DEFINED' && (
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span>{t('blast.source_rule', { defaultValue: 'Regla (obligatoria para SOURCE_DEFINED)' })}</span>
              <select
                value={state.inclinationSourceRule}
                onChange={(e) => update('inclinationSourceRule', e.target.value as GeometryState['inclinationSourceRule'])}
                data-testid="source-rule"
                className={PROJECT_INPUT_CLASS}
              >
                <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
                {SOURCE_RULES.map((v) => (
                  <option key={v} value={v}>{t('blast.geometry_options.' + v)}</option>
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
              className={PROJECT_INPUT_CLASS}
            >
              <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
              {UNITS.map((v) => (
                <option key={v} value={v}>{t('blast.geometry_options.' + v)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span>{t('blast.az_unit', { defaultValue: 'Unidad de azimut' })}</span>
            <select
              value={state.azimuthUnit}
              onChange={(e) => update('azimuthUnit', e.target.value as GeometryState['azimuthUnit'])}
              data-testid="az-unit"
              className={PROJECT_INPUT_CLASS}
            >
              <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
              {UNITS.map((v) => (
                <option key={v} value={v}>{t('blast.geometry_options.' + v)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span>{t('blast.az_convention', { defaultValue: 'Convención de azimut' })}</span>
            <select
              value={state.azimuthConvention}
              onChange={(e) => update('azimuthConvention', e.target.value as GeometryState['azimuthConvention'])}
              data-testid="az-convention"
              className={PROJECT_INPUT_CLASS}
            >
              <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
              {AZ_CONVENTIONS.map((v) => (
                <option key={v} value={v}>{t('blast.geometry_options.' + v)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span>{t('blast.collar_elevation_source', { defaultValue: 'Fuente de cota de collar' })}</span>
            <select
              value={state.collarElevationSource}
              onChange={(e) => update('collarElevationSource', e.target.value as GeometryState['collarElevationSource'])}
              data-testid="collar-elevation-source"
              className={PROJECT_INPUT_CLASS}
            >
              <option value="bench_height">{t('blast.collar_source_height', { defaultValue: 'Altura de banco (modo actual)' })}</option>
              <option value="design_surface">{t('blast.collar_source_design', { defaultValue: 'Superficie de diseño' })}</option>
            </select>
          </label>
          {state.collarElevationSource === 'bench_height' ? (
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span>{t('blast.bench_height', { defaultValue: 'Altura de banco (m)' })}</span>
              <input type="number" min="0" step="0.1" value={state.benchHeightM} onChange={(e) => update('benchHeightM', e.target.value)} data-testid="bench-height" className={PROJECT_INPUT_CLASS} />
            </label>
          ) : (
            <div className="flex flex-col gap-2 sm:col-span-2" data-testid="design-surface-elevation">
              <p>{t('blast.design_surface_help', { defaultValue: 'La cota del collar se estimará desde la superficie de diseño. El factor de carga volumétrico puede quedar indisponible o ser aproximado; no se infiere la altura real del banco.' })}</p>
              <label className="flex items-start gap-2 text-text-secondary">
                <input type="checkbox" checked={state.spatialReferenceConfirmed} onChange={(e) => update('spatialReferenceConfirmed', e.target.checked)} data-testid="spatial-reference-confirmed" />
                <span>{t('blast.spatial_reference_confirm', { defaultValue: 'Confirmo que coordenadas, CRS, unidades y datum de la CSV son compatibles con la superficie de diseño.' })}</span>
              </label>
            </div>
          )}
          <label className="mt-1 flex items-center gap-2 text-text-secondary sm:col-span-2" data-testid="confirm-row">
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
      </details>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" size="sm" onClick={handleUpload} disabled={!canSubmit} loading={upload.isPending} data-testid="blast-upload-submit">
          {t('blast.submit_csv')}
        </Button>
        {!sessionId && (
          <p className="text-xs text-text-muted">
            {t('blast.upload_no_session', { defaultValue: 'Inicie una sesión para cargar pozos.' })}
          </p>
        )}
        {sessionId && !geometry && (
          <p className="text-xs text-text-muted" role="alert">
            {t('blast.contract_required', {
              defaultValue:
                'Complete y confirme el contrato geométrico antes de cargar el CSV.',
            })}
          </p>
        )}
      </div>
      {(upload.isPending || uploadPhase !== null) && (
        <div className="flex flex-col gap-1" role="status" aria-live="polite" data-testid="blast-upload-progress">
          <p className="text-xs text-text-muted">
            {uploadPhase === 'processing'
              ? t('blast.processing_geometry')
              : t('blast.transferring_file')}
          </p>
          {uploadPhase !== 'processing' && uploadProgress != null && (
            <div className="flex items-center gap-2">
              <progress className="h-1.5 w-full accent-[var(--color-accent)]" max={100} value={uploadProgress} aria-label={t('blast.transfer_progress')} />
              <span className="shrink-0 text-xs tabular-nums text-text-muted">{uploadProgress}%</span>
            </div>
          )}
        </div>
      )}
      {upload.isError && (
        <StatusLine tone="nok" role="alert" data-testid="upload-error">
          {t('blast.upload_error', { error: String(upload.error) })}
        </StatusLine>
      )}
      {blockingErrors.length > 0 && (
        <StatusLine tone="nok" data-testid="blocking-errors">
          <p className="font-medium text-text-primary">{t('blast.blocking_errors', { defaultValue: 'Errores bloqueantes:' })}</p>
          <ul className="ml-4 list-disc">
            {blockingErrors.map((err, idx) => (
              <li key={idx}>
                <code className="font-mono">{err.error_code}</code>: {err.message}
              </li>
            ))}
          </ul>
        </StatusLine>
      )}
      {rejectedRows.length > 0 && (
        <StatusLine tone="warn" data-testid="rejected-rows">
          <p className="font-medium text-text-primary">{t('blast.rejected_rows', { defaultValue: 'Filas rechazadas:' })}</p>
          <ul className="ml-4 list-disc">
            {rejectedRows.slice(0, 10).map((r, idx) => (
              <li key={idx}>
                <code className="font-mono">{r.error_code}</code> ({r.source_column} fila {r.source_row_index}):{' '}
                {r.rejection_reason}
              </li>
            ))}
            {rejectedRows.length > 10 && (
              <li>… +{rejectedRows.length - 10} más</li>
            )}
          </ul>
        </StatusLine>
      )}
      {diagnostics && (
        <div className="flex flex-col gap-2 text-xs text-text-secondary" data-testid="processing-diagnostics">
          <div className="flex flex-wrap gap-x-4 gap-y-1 tabular-nums">
            <div data-testid="accepted-rows">{t('blast.accepted_rows_label')}: {diagnostics.accepted_rows?.length ?? 0}</div>
            <div data-testid="event-warnings">{t('blast.event_warnings_label')}: {diagnostics.event_warnings?.length ?? 0}</div>
          </div>
          {eventWarningMessages.length > 0 && (
            <ul aria-label={t('blast.event_warnings_label')} aria-live="polite" className="ml-4 list-disc" data-testid="event-warning-messages">
              {eventWarningMessages.map((message, index) => <li key={index}>{message}</li>)}
            </ul>
          )}
          <details className="text-text-muted">
            <summary className="cursor-pointer text-xs font-medium text-text-secondary hover:text-text-primary">
              {t('blast.technical_diagnostics', { defaultValue: 'Diagnóstico técnico' })}
            </summary>
            <div className="mt-2 flex flex-col gap-2">
              <div>
                <p className="font-medium text-text-secondary">{t('blast.processing_summary_label')}</p>
                <pre className="overflow-x-auto font-mono text-[11px]" data-testid="processing-summary">{JSON.stringify(diagnostics.processing_summary ?? {}, null, 2)}</pre>
              </div>
              <div>
                <p className="font-medium text-text-secondary">{t('blast.geometry_configuration_label')}</p>
                <pre className="overflow-x-auto font-mono text-[11px]" data-testid="geometry-configuration">{JSON.stringify(diagnostics.geometry_configuration ?? {}, null, 2)}</pre>
              </div>
              <div>
                <p className="font-medium text-text-secondary">{t('blast.spatial_diagnostics_label')}</p>
                <pre className="overflow-x-auto font-mono text-[11px]" data-testid="spatial-diagnostics">{JSON.stringify(diagnostics.spatial_diagnostics ?? {}, null, 2)}</pre>
              </div>
            </div>
          </details>
        </div>
      )}
      {upload.isSuccess && upload.data && (
        <div className="flex flex-col gap-1 text-xs text-text-secondary" data-testid="blast-upload-summary">
          <p>
            {t('blast.upload_summary', { n: upload.data.n_holes, skipped: upload.data.n_rows_skipped })}
          </p>
          {upload.data.carga_mean != null && (
            <p className="tabular-nums">
              {t('blast.carga_mean', { value: upload.data.carga_mean.toFixed(2) })}
            </p>
          )}
          {upload.data.descarga_mean != null && (
            <p className="tabular-nums">
              {t('blast.descarga_mean', { value: upload.data.descarga_mean.toFixed(2) })}
            </p>
          )}
          {upload.data.design_surface && (
            <div className="mt-1 flex flex-col gap-1" data-testid="design-surface-sampling-summary">
              <p className="font-medium text-text-primary">{t('blast.design_surface_sampling_title')}</p>
              <p>{t('blast.design_surface_sampling_coverage', { coverage: (upload.data.design_surface.coverage * 100).toFixed(1), rows: upload.data.design_surface.rows })}</p>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 tabular-nums">
                <div><dt className="inline text-text-muted">{t('blast.design_surface_sampled')}: </dt><dd className="inline" data-testid="design-surface-sampled">{upload.data.design_surface.counts.sampled}</dd></div>
                <div><dt className="inline text-text-muted">{t('blast.design_surface_outside')}: </dt><dd className="inline" data-testid="design-surface-outside">{upload.data.design_surface.counts.outside}</dd></div>
                <div><dt className="inline text-text-muted">{t('blast.design_surface_ambiguous')}: </dt><dd className="inline" data-testid="design-surface-ambiguous">{upload.data.design_surface.counts.ambiguous}</dd></div>
                <div><dt className="inline text-text-muted">{t('blast.design_surface_invalid')}: </dt><dd className="inline" data-testid="design-surface-invalid">{upload.data.design_surface.counts.invalid}</dd></div>
              </dl>
            </div>
          )}
        </div>
      )}
    </div>
  );

  const persistedCount = holes.data ? (
    <p className="text-xs tabular-nums text-text-muted" data-testid="blast-hole-count">
      {t('blast.persisted_count', { n: holes.data.holes.length })}
    </p>
  ) : null;

  if (collapsible) {
    return (
      <section className="text-left" data-testid="blast-uploader" data-collapsible="true">
        <details className="group">
          <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3 [&::-webkit-details-marker]:hidden">
            <span className="flex items-center gap-2">
              <svg aria-hidden="true" viewBox="0 0 12 12" className="h-3 w-3 text-text-muted transition-transform group-open:rotate-90" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M4.5 2.5 8 6l-3.5 3.5" />
              </svg>
              {title}
            </span>
            {persistedCount}
          </summary>
          <div className="border-t border-border py-4">{body}</div>
        </details>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-3 text-left" data-testid="blast-uploader">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h3 className="flex items-center gap-2">{title}</h3>
        {persistedCount}
      </div>
      {body}
    </section>
  );
}
