import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useUploadBlastCsv,
  useBlastSessionSummary,
  extractBlastErrorDiagnostics,
  type BlastGeometryForm,
} from '../../api/hooks';
import { getSessionId } from '../../api/client';
import { DEMO_MESH_IDS, useSession } from '../../stores/session';
import type { BlastUploadResponse, BlockingError, RejectedRow } from '../../api/types';
import { GEOMETRY_CONFIGURATION_VERSION } from '../../api/types';
import { Button } from '../ui/Button';
import { PROJECT_INPUT_CLASS } from '../ui/ProjectControls';
import { previewBlastImport, type BlastImportPreview } from '../../api/blastImport';

const IMPORT_FIELDS = [
  ['X', 'Coordenada Este', true], ['Y', 'Coordenada Norte', true], ['Z_collar', 'Cota collar del pozo', true],
  ['Incl', 'Inclinación', true], ['Az', 'Azimut', true], ['Len', 'Longitud perforada', true],
  ['Burden', 'Burden', false], ['Esp', 'Espaciamiento', false], ['Diam_mm', 'Diámetro', false],
  ['Tipo_Explosivo', 'Tipo de explosivo', false], ['Taco_m', 'Taco', false], ['Secuencia', 'Secuencia', false],
  ['Retardo_ms', 'Retardo', false], ['Fila', 'Fila', false], ['Carga_Fondo_kg', 'Carga de fondo', false],
  ['Carga_Columna_kg', 'Carga de columna', false], ['Longitud_Carga_m', 'Longitud cargada', false],
  ['Tipo_Pozo', 'Tipo de pozo', false], ['Az_Diseno', 'Azimut de diseño', false], ['Incl_Diseno', 'Inclinación de diseño', false],
] as const;

export interface BlastUploaderProps {
  onUploaded?: (response: BlastUploadResponse) => void;
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

export function BlastUploader({ onUploaded }: BlastUploaderProps) {
  const { t } = useTranslation();
  const { designMeshId, topoMeshId } = useSession();
  const hasVirtualMesh = (
    designMeshId === DEMO_MESH_IDS.design || topoMeshId === DEMO_MESH_IDS.topo
  );
  const sessionId = getSessionId();
  const upload = useUploadBlastCsv();
  const blastSummary = useBlastSessionSummary(hasVirtualMesh ? null : sessionId ?? null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const contractRef = useRef<HTMLDetailsElement>(null);
  const headerReadVersion = useRef(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceColumns, setSourceColumns] = useState<string[]>([]);
  const [preview, setPreview] = useState<BlastImportPreview | null>(null);
  const [columnMap, setColumnMap] = useState<Record<string, string>>({});
  const [mappingConfirmed, setMappingConfirmed] = useState(false);
  const [sheetName, setSheetName] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
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
  const requiredMissing = IMPORT_FIELDS.filter(([key, , required]) => required && key !== 'Z_collar' && !columnMap[key]).map(([key]) => key);
  if (state.collarElevationSource !== 'design_surface' && !columnMap.Z_collar) requiredMissing.push('Z_collar');
  const duplicateMappings = Object.entries(columnMap).filter(([, source]) => source).map(([, source]) => source).filter((source, index, values) => values.indexOf(source) !== index);
  const canSubmit = !hasVirtualMesh && Boolean(sessionId) && selectedFile !== null && geometry !== null && mappingConfirmed && requiredMissing.length === 0 && duplicateMappings.length === 0 && !previewLoading && !upload.isPending && sourceColumnsValid;

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
      <section className="flex flex-col gap-3 rounded-lg border p-4 text-left" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface-muted)' }} data-testid="blast-uploader">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
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
    if (!/\.(csv|xlsx)$/i.test(file.name)) {
      setFileError(t('blast.import_supported', { defaultValue: 'Seleccione un archivo CSV o XLSX. Los archivos XLS no son compatibles.' }));
      return;
    }
    setFileError(null);
    setSelectedFile(file);
    setPreview(null);
    setColumnMap({});
    setMappingConfirmed(false);
    setSheetName('');
    setSourceColumns([]);
    setPreviewLoading(true);
    const readVersion = headerReadVersion.current + 1;
    headerReadVersion.current = readVersion;
    void previewBlastImport(file).then((result) => {
      if (headerReadVersion.current !== readVersion) return;
      setPreview(result);
      setSourceColumns(result.headers);
      const suggested = Object.fromEntries(Object.entries(result.suggested_mapping).filter(([, value]) => typeof value === 'string')) as Record<string, string>;
      setColumnMap(suggested);
      setSheetName(result.sheet_name ?? result.sheets[0] ?? '');
    }).catch((error: unknown) => {
      if (headerReadVersion.current === readVersion) setFileError(error instanceof Error ? error.message : t('blast.preview_error', { defaultValue: 'No se pudo leer la vista previa del archivo.' }));
    }).finally(() => { if (headerReadVersion.current === readVersion) setPreviewLoading(false); });
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
        geometry: { ...geometry, column_map: columnMap, sheet_name: sheetName || undefined },
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

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border p-4 text-left"
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

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={() => fileInputRef.current?.click()} disabled={upload.isPending} data-testid="blast-file-picker">{t('blast.choose_csv', { defaultValue: 'Seleccionar archivo' })}</Button>
        {filename && <span className="min-w-0 break-all text-xs text-text-secondary">{t('blast.file_selected', { filename })}</span>}
      </div>
      <input ref={fileInputRef} type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" data-testid="blast-file-input" onChange={handleFileChange} disabled={upload.isPending} className="hidden" />
      {fileError && <p role="alert" className="text-xs text-mine-red">{fileError}</p>}
      {previewLoading && <p role="status" className="text-xs text-text-muted">{t('blast.preview_loading', { defaultValue: 'Leyendo encabezados y hasta 20 filas…' })}</p>}
      {preview && <div className="flex flex-col gap-2 rounded border p-3" style={{ borderColor: 'var(--color-border)' }} data-testid="blast-import-mapper">
        {preview.sheets.length > 0 && <label className="flex flex-col gap-1">{t('blast.sheet_name', { defaultValue: 'Hoja de Excel' })}<select value={sheetName} className={PROJECT_INPUT_CLASS} data-testid="blast-sheet-select" onChange={(event) => {
          const nextSheet = event.target.value;
          const version = headerReadVersion.current + 1; headerReadVersion.current = version;
          setSheetName(nextSheet); setMappingConfirmed(false); setPreview(null); setColumnMap({}); setPreviewLoading(true);
          void previewBlastImport(selectedFile!, nextSheet).then((result) => { if (headerReadVersion.current !== version) return; setPreview(result); setSourceColumns(result.headers); setColumnMap(Object.fromEntries(Object.entries(result.suggested_mapping).filter(([, value]) => typeof value === 'string')) as Record<string, string>); }).catch(() => { if (headerReadVersion.current === version) setFileError(t('blast.preview_error', { defaultValue: 'No se pudo leer la vista previa del archivo.' })); }).finally(() => { if (headerReadVersion.current === version) setPreviewLoading(false); });
        }}>{preview.sheets.map((sheet) => <option key={sheet} value={sheet}>{sheet}</option>)}</select></label>}
        <p className="text-xs text-text-muted">{t('blast.mapping_title', { defaultValue: 'Asigne las columnas del archivo a los campos de tronadura. Las sugerencias deben confirmarse.' })} {preview.encoding ? `${t('blast.encoding', { defaultValue: 'Codificación' })}: ${preview.encoding}` : ''}</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">{IMPORT_FIELDS.filter(([, , required]) => required).map(([key, label, required]) => { const confidence = preview.confidence[key] as { kind?: string; score?: number } | undefined; return <label key={key} className="flex flex-col gap-1"><span>{t(`blast.field_${key}`, { defaultValue: label })}{required ? ' *' : ''}</span><select data-testid={`map-${key}`} value={columnMap[key] ?? ''} className={PROJECT_INPUT_CLASS} onChange={(event) => { setColumnMap((previous) => ({ ...previous, [key]: event.target.value })); setMappingConfirmed(false); if (key === 'Incl') update('inclinationSourceColumn', event.target.value); if (key === 'Az') update('azimuthSourceColumn', event.target.value); }}><option value="">{t('blast.unmapped', { defaultValue: 'Sin asignar' })}</option>{preview.headers.map((column) => <option key={`${key}-${column}`} value={column}>{column}</option>)}</select>{confidence && preview.suggested_mapping[key] === columnMap[key] && <span className="text-[11px] text-text-muted">{t('blast.mapping_confidence', { defaultValue: 'Sugerencia: {{kind}} ({{score}}%)', kind: t(`blast.kind_${confidence.kind ?? 'unmatched'}`, { defaultValue: confidence.kind ?? 'unmatched' }), score: Math.round((confidence.score ?? 0) * 100) })}</span>}</label>; })}</div>
        <details><summary className="cursor-pointer">{t('blast.optional_fields', { defaultValue: 'Campos opcionales (14)' })}</summary><div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">{IMPORT_FIELDS.filter(([, , required]) => !required).map(([key, label]) => <label key={key} className="flex flex-col gap-1"><span>{t(`blast.field_${key}`, { defaultValue: label })}</span><select data-testid={`map-${key}`} value={columnMap[key] ?? ''} className={PROJECT_INPUT_CLASS} onChange={(event) => { setColumnMap((previous) => ({ ...previous, [key]: event.target.value })); setMappingConfirmed(false); }}><option value="">{t('blast.unmapped', { defaultValue: 'Sin asignar' })}</option>{preview.headers.map((column) => <option key={`${key}-${column}`} value={column}>{column}</option>)}</select></label>)}</div></details>
        <label className="flex items-center gap-2"><input type="checkbox" data-testid="mapping-confirmed" checked={mappingConfirmed} onChange={(event) => { setMappingConfirmed(event.target.checked); update('confirmed', false); }} />{t('blast.mapping_confirm', { defaultValue: 'Confirmo que el mapeo de columnas es correcto.' })}</label>
        {requiredMissing.length > 0 && <p role="alert" className="text-xs text-mine-red">{t('blast.mapping_missing', { defaultValue: 'Asigne todos los campos obligatorios: {{fields}}', fields: requiredMissing.join(', ') })}</p>}
        {duplicateMappings.length > 0 && <p role="alert" className="text-xs text-mine-red">{t('blast.mapping_duplicate', { defaultValue: 'Cada columna del archivo debe asignarse a un solo campo.' })}</p>}
        <div className="overflow-x-auto"><table className="text-xs"><thead><tr>{preview.headers.slice(0, 20).map((header) => <th key={header} className="max-w-40 border px-2 py-1 text-left">{header}</th>)}</tr></thead><tbody>{preview.preview.slice(0, 20).map((row, index) => <tr key={index}>{preview.headers.slice(0, 20).map((header) => <td key={header} className="max-w-40 truncate border px-2 py-1">{String(row[header] ?? '')}</td>)}</tr>)}</tbody></table></div>
      </div>}
      <p className="text-xs text-text-muted">{t('blast.upload_steps')}</p>

      <details ref={contractRef} className="text-xs" data-testid="geometry-contract-form">
        <summary className="cursor-pointer font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
          {t('blast.geometry_contract', { defaultValue: 'Contrato geométrico (obligatorio)' })}
        </summary>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span>{t('blast.incl_source_col', { defaultValue: 'Columna fuente de inclinación' })}</span>
            {sourceColumns.length > 0 ? (
              <select value={state.inclinationSourceColumn} onChange={(e) => { update('inclinationSourceColumn', e.target.value); setColumnMap((previous) => ({ ...previous, Incl: e.target.value })); setMappingConfirmed(false); }} data-testid="incl-source-column" aria-invalid={Boolean(state.inclinationSourceColumn && !sourceColumns.includes(state.inclinationSourceColumn))} className={PROJECT_INPUT_CLASS}>
                <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
                {state.inclinationSourceColumn && !sourceColumns.includes(state.inclinationSourceColumn) && <option value={state.inclinationSourceColumn}>{state.inclinationSourceColumn}</option>}
                {sourceColumns.map((column) => <option key={column} value={column}>{column}</option>)}
              </select>
            ) : (
              <input type="text" value={state.inclinationSourceColumn} onChange={(e) => update('inclinationSourceColumn', e.target.value)} placeholder="Inclinacion_real" data-testid="incl-source-column" className={PROJECT_INPUT_CLASS} />
            )}
          </label>
          {sourceColumns.length > 0 && state.inclinationSourceColumn && !sourceColumns.includes(state.inclinationSourceColumn) && (
            <p className="col-span-2 text-xs text-text-muted" role="status">{t('blast.source_column_missing', { column: state.inclinationSourceColumn, defaultValue: 'La columna «{{column}}» no está en el encabezado del archivo seleccionado. Elija una columna disponible.' })}</p>
          )}
          {state.inclinationConvention === 'FROM_VERTICAL' && state.inclinationSignConvention === 'NEGATIVE_IS_DOWNWARD_DIP' && (
            <p className="col-span-2 rounded-md border p-2 text-xs" role="alert" style={{ borderColor: 'var(--color-status-error)', color: 'var(--color-status-error)' }}>
              {t('blast.inclination_convention_sign_incompatible', { defaultValue: 'La convención desde la vertical no es compatible con la regla «negativo indica buzamiento descendente». Seleccione buzamiento desde la horizontal o una política de signo compatible.' })}
            </p>
          )}
          <label className="flex flex-col gap-1">
            <span>{t('blast.az_source_col', { defaultValue: 'Columna fuente de azimut' })}</span>
            {sourceColumns.length > 0 ? (
              <select value={state.azimuthSourceColumn} onChange={(e) => { update('azimuthSourceColumn', e.target.value); setColumnMap((previous) => ({ ...previous, Az: e.target.value })); setMappingConfirmed(false); }} data-testid="az-source-column" aria-invalid={Boolean(state.azimuthSourceColumn && !sourceColumns.includes(state.azimuthSourceColumn))} className={PROJECT_INPUT_CLASS}>
                <option value="">{t('blast.select_option', { defaultValue: 'Seleccione una opción' })}</option>
                {state.azimuthSourceColumn && !sourceColumns.includes(state.azimuthSourceColumn) && <option value={state.azimuthSourceColumn}>{state.azimuthSourceColumn}</option>}
                {sourceColumns.map((column) => <option key={column} value={column}>{column}</option>)}
              </select>
            ) : (
              <input type="text" value={state.azimuthSourceColumn} onChange={(e) => update('azimuthSourceColumn', e.target.value)} placeholder="Azimuth_real" data-testid="az-source-column" className={PROJECT_INPUT_CLASS} />
            )}
          </label>
          {sourceColumns.length > 0 && state.azimuthSourceColumn && !sourceColumns.includes(state.azimuthSourceColumn) && (
            <p className="col-span-2 text-xs text-text-muted" role="status">{t('blast.source_column_missing', { column: state.azimuthSourceColumn, defaultValue: 'La columna «{{column}}» no está en el encabezado del archivo seleccionado. Elija una columna disponible.' })}</p>
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
            <label className="flex flex-col gap-1 col-span-2">
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
          <label className="flex flex-col gap-1 col-span-2">
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
          <label className="flex flex-col gap-1 col-span-2">
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
            <label className="flex flex-col gap-1 col-span-2">
              <span>{t('blast.bench_height', { defaultValue: 'Altura de banco (m)' })}</span>
              <input type="number" min="0" step="0.1" value={state.benchHeightM} onChange={(e) => update('benchHeightM', e.target.value)} data-testid="bench-height" className={PROJECT_INPUT_CLASS} />
            </label>
          ) : (
            <div className="col-span-2 flex flex-col gap-2 rounded-md border p-2" style={{ borderColor: 'var(--color-border)' }} data-testid="design-surface-elevation">
              <p>{t('blast.design_surface_help', { defaultValue: 'La cota del collar se estimará desde la superficie de diseño. El factor de carga volumétrico puede quedar indisponible o ser aproximado; no se infiere la altura real del banco.' })}</p>
              <label className="flex items-start gap-2">
                <input type="checkbox" checked={state.spatialReferenceConfirmed} onChange={(e) => update('spatialReferenceConfirmed', e.target.checked)} data-testid="spatial-reference-confirmed" />
                <span>{t('blast.spatial_reference_confirm', { defaultValue: 'Confirmo que coordenadas, CRS, unidades y datum de la CSV son compatibles con la superficie de diseño.' })}</span>
              </label>
            </div>
          )}
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
      </details>

      <Button type="button" size="sm" onClick={handleUpload} disabled={!canSubmit} loading={upload.isPending} data-testid="blast-upload-submit">
        {t('blast.submit_csv')}
      </Button>
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
      {(upload.isPending || uploadPhase !== null) && (
        <div className="space-y-1" role="status" aria-live="polite" data-testid="blast-upload-progress">
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {uploadPhase === 'processing'
              ? t('blast.processing_geometry')
              : t('blast.transferring_file')}
          </p>
          {uploadPhase !== 'processing' && uploadProgress != null && (
            <div className="flex items-center gap-2">
              <progress className="h-2 w-full" max={100} value={uploadProgress} aria-label={t('blast.transfer_progress')} />
              <span className="shrink-0 text-xs" style={{ color: 'var(--color-text-muted)' }}>{uploadProgress}%</span>
            </div>
          )}
        </div>
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
      {diagnostics && (
        <div className="grid gap-2 text-xs" data-testid="processing-diagnostics">
          <div data-testid="accepted-rows">{t('blast.accepted_rows_label')}: {diagnostics.accepted_rows?.length ?? diagnostics.n_rows_loaded ?? 0}</div>
          <div data-testid="event-warnings">{t('blast.event_warnings_label')}: {diagnostics.event_warnings?.length ?? 0}</div>
          {eventWarningMessages.length > 0 && (
            <ul aria-label={t('blast.event_warnings_label')} aria-live="polite" className="ml-4 list-disc" data-testid="event-warning-messages">
              {eventWarningMessages.map((message, index) => <li key={index}>{message}</li>)}
            </ul>
          )}
          <div>
            <strong>{t('blast.processing_summary_label')}</strong>
            <pre data-testid="processing-summary">{JSON.stringify(diagnostics.processing_summary ?? {}, null, 2)}</pre>
          </div>
          <div>
            <strong>{t('blast.geometry_configuration_label')}</strong>
            <pre data-testid="geometry-configuration">{JSON.stringify(diagnostics.geometry_configuration ?? {}, null, 2)}</pre>
          </div>
          <div>
            <strong>{t('blast.spatial_diagnostics_label')}</strong>
            <pre data-testid="spatial-diagnostics">{JSON.stringify(diagnostics.spatial_diagnostics ?? {}, null, 2)}</pre>
          </div>
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
          {upload.data.design_surface && (
            <div className="mt-2 rounded-md border p-2 text-xs" style={{ borderColor: 'var(--color-border)' }} data-testid="design-surface-sampling-summary">
              <strong>{t('blast.design_surface_sampling_title')}</strong>
              <p>{t('blast.design_surface_sampling_coverage', { coverage: (upload.data.design_surface.coverage * 100).toFixed(1), rows: upload.data.design_surface.rows })}</p>
              <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1">
                <div><dt className="inline">{t('blast.design_surface_sampled')}: </dt><dd className="inline" data-testid="design-surface-sampled">{upload.data.design_surface.counts.sampled}</dd></div>
                <div><dt className="inline">{t('blast.design_surface_outside')}: </dt><dd className="inline" data-testid="design-surface-outside">{upload.data.design_surface.counts.outside}</dd></div>
                <div><dt className="inline">{t('blast.design_surface_ambiguous')}: </dt><dd className="inline" data-testid="design-surface-ambiguous">{upload.data.design_surface.counts.ambiguous}</dd></div>
                <div><dt className="inline">{t('blast.design_surface_invalid')}: </dt><dd className="inline" data-testid="design-surface-invalid">{upload.data.design_surface.counts.invalid}</dd></div>
              </dl>
            </div>
          )}
        </div>
      )}
      {blastSummary.data && (
        <p className="text-xs" data-testid="blast-hole-count" style={{ color: 'var(--color-text-muted)' }}>
          {t('blast.persisted_count', { n: blastSummary.data.n_holes })}
        </p>
      )}
    </section>
  );
}
