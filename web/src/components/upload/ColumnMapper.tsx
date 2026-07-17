import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useDetectColumnMapping } from '../../api/hooks';
import type {
  ColumnDetectResponse,
  ColumnMappingField,
} from '../../api/types';

/**
 * ColumnMapper — schema-agnostic CSV upload wizard (mapping step).
 *
 * Renders a modal that lets the user pick which source column feeds
 * each canonical blast-hole field (X, Y, Z_collar, Incl, Az, Len,
 * plus 14 optional). On open we POST the supplied column names to
 * `POST /api/v1/mapping/detect`; the backend's two-pass (exact +
 * fuzzy) auto-mapper pre-fills the dropdowns and returns per-field
 * confidence.
 *
 * The Confirm button is locked until every required canonical field
 * has a non-empty source column, and a live 5-row preview reflects
 * the current mapping so the user can sanity-check before submitting.
 *
 * Wire format reminder: `ColumnDetectResponse.schema` is the alias
 * key (`schema`) on the Python side; the `ColumnMappingField` shape
 * mirrors `core.column_mapping.get_field_schema()`.
 */

export interface ColumnMapperProps {
  /** Open / close the modal. Controlled by the parent. */
  readonly open: boolean;
  /** Source CSV/Excel header — the columns the user uploaded. */
  readonly columns: string[];
  /**
   * First N rows keyed by source column name → array of stringified
   * values. Optional; when provided we use it to render a live preview
   * table of the first 5 mapped rows (cells are looked up by the
   * currently-selected source column for each canonical field).
   *
   * Values are rendered as strings verbatim (no type coercion) so the
   * user can see exactly what is in the file before confirming.
   */
  readonly previewRows?: Record<string, string[]> | null;
  /** Called when the user clicks Confirm with a complete mapping. */
  readonly onConfirm: (mapping: Record<string, string | null>) => void;
  /** Called when the user dismisses the modal without confirming. */
  readonly onCancel: () => void;
}

interface FieldRowProps {
  readonly field: ColumnMappingField;
  readonly value: string | null;
  readonly columns: string[];
  readonly mappedByOther: Set<string>;
  readonly confidenceKind: 'exact' | 'fuzzy' | 'unmatched' | undefined;
  readonly onChange: (source: string | null) => void;
  readonly isRequired: boolean;
  readonly isMissing: boolean;
}

/** Single field row: badge + label + dropdown. */
function FieldRow({
  field,
  value,
  columns,
  mappedByOther,
  confidenceKind,
  onChange,
  isRequired,
  isMissing,
}: FieldRowProps) {
  const { t } = useTranslation();

  // Status icon: ✓ if mapped (green), ⚠ if required & missing (amber).
  const statusIcon = value
    ? '✓'
    : isRequired
      ? '⚠'
      : '–';
  const statusColor = value
    ? 'var(--color-status-ok, #22c55e)'
    : isRequired
      ? 'var(--color-status-error, #ef4444)'
      : 'var(--color-text-muted)';

  // Confidence badge colour (only shown when mapped).
  const confidenceLabel =
    confidenceKind === 'exact'
      ? t('columnMapper.confidence_exact')
      : confidenceKind === 'fuzzy'
        ? t('columnMapper.confidence_fuzzy')
        : confidenceKind === 'unmatched'
          ? t('columnMapper.confidence_unmatched')
          : null;

  return (
    <tr
      data-testid={`column-mapper-row-${field.name}`}
      data-mapped={value ? 'true' : 'false'}
    >
      <td className="py-2 pr-3 text-sm font-mono whitespace-nowrap" style={{ color: 'var(--color-text-primary)' }}>
        <span style={{ color: statusColor }} aria-hidden="true">
          {statusIcon}
        </span>{' '}
        {field.name}
        {isRequired && (
          <span className="ml-1 text-[10px] uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
            *
          </span>
        )}
      </td>
      <td className="py-2 pr-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
        <div className="flex flex-col">
          <span>{field.description}</span>
          {field.unit && (
            <span className="text-[10px] font-mono opacity-70">
              [{field.unit}]
            </span>
          )}
        </div>
      </td>
      <td className="py-2">
        <div className="flex items-center gap-2">
          <select
            data-testid={`column-mapper-select-${field.name}`}
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value || null)}
            className="flex-1 min-w-[140px] px-2 py-1 border rounded-md text-xs outline-none focus:ring-2"
            style={{
              borderColor: isMissing && isRequired ? 'var(--color-status-error, #ef4444)' : 'var(--color-border)',
              backgroundColor: 'var(--color-surface)',
              color: 'var(--color-text-primary)',
            }}
            aria-required={isRequired}
            aria-invalid={isMissing && isRequired}
          >
            <option value="">
              {t('columnMapper.unmapped_option', { defaultValue: '— sin asignar —' })}
            </option>
            {columns.map((c) => {
              // Disable columns already claimed by another field so we
              // visually communicate the "no duplicates" invariant
              // rather than letting the user shoot themselves in the
              // foot (validation on the backend would still reject
              // it, but a disabled option is friendlier).
              const taken = mappedByOther.has(c) && c !== value;
              return (
                <option key={c} value={c} disabled={taken}>
                  {c}
                </option>
              );
            })}
          </select>
          {confidenceLabel && (
            <span
              className="text-[10px] uppercase tracking-wider font-mono px-1.5 py-0.5 rounded"
              style={{
                backgroundColor:
                  confidenceKind === 'exact'
                    ? 'rgba(34, 197, 94, 0.15)'
                    : 'rgba(234, 179, 8, 0.15)',
                color:
                  confidenceKind === 'exact'
                    ? 'var(--color-status-ok, #22c55e)'
                    : '#ca8a04',
              }}
              title={t('columnMapper.confidence_hint', { kind: confidenceKind ?? '' })}
            >
              {confidenceLabel}
            </span>
          )}
        </div>
      </td>
    </tr>
  );
}

export function ColumnMapper({
  open,
  columns,
  previewRows,
  onConfirm,
  onCancel,
}: ColumnMapperProps) {
  const { t } = useTranslation();
  const detect = useDetectColumnMapping();

  // Local working copy of the mapping. Filled on first detect, then
  // editable. Source column for each canonical field, or null if the
  // user has explicitly unmapped it.
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [hasFetched, setHasFetched] = useState(false);

  // Reset state every time the modal is (re-)opened so we don't leak a
  // mapping from the previous file into the new one.
  useEffect(() => {
    if (!open) return;
    setHasFetched(false);
    setMapping({});

    // Trigger auto-detect automatically on open. The mutation's
    // `data` will then drive the useEffect below to populate
    // `mapping`.
    void detect.mutateAsync({ columns }).catch(() => {
      // Errors are surfaced via `detect.isError` / the banner below;
      // nothing to do here.
    });
    // We intentionally only depend on `open` — `columns` is captured
    // fresh on each open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // When the detect call resolves, seed the local mapping from the
  // server's suggestions. We keep user edits if they happen to match.
  useEffect(() => {
    if (!detect.data || hasFetched) return;
    const initial: Record<string, string | null> = {};
    for (const [k, v] of Object.entries(detect.data.mapping)) {
      initial[k] = v;
    }
    setMapping(initial);
    setHasFetched(true);
  }, [detect.data, hasFetched]);

  // Lock body scroll while the modal is open, matching the pattern in
  // `components/ui/KeyboardShortcutsHelp.tsx`.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Field schema and required-set come from the detect response
  // (which embeds the same payload as GET /mapping/schema). If the
  // server hasn't replied yet we render an empty list and the user
  // sees a spinner in the body area.
  const fieldSchema: ColumnMappingField[] = detect.data?.schema ?? [];
  const requiredSet = useMemo(() => {
    // The detect response doesn't carry `required_fields` explicitly,
    // so we derive it from per-field `required`. (Falls back to the
    // schema's per-field flag if the response omits the field.)
    return new Set(fieldSchema.filter((f) => f.required).map((f) => f.name));
  }, [fieldSchema]);

  // For the "no duplicates" dropdown hint: build a per-canonical-field
  // set of source columns already claimed by some OTHER canonical
  // field. The dropdown then disables those options so the user
  // cannot pick a value the backend would later reject.
  const mappedByOther = useMemo(() => {
    const result = new Map<string, Set<string>>();
    const allKeys = Object.keys(mapping);
    for (const canonical of allKeys) {
      const others = new Set<string>();
      for (const otherCanonical of allKeys) {
        if (otherCanonical === canonical) continue;
        const otherSrc = mapping[otherCanonical];
        if (otherSrc) others.add(otherSrc);
      }
      result.set(canonical, others);
    }
    return result;
  }, [mapping]);

  const requiredFields = Array.from(requiredSet);

  const missingRequired = requiredFields.filter((name) => !mapping[name]);
  const canConfirm = missingRequired.length === 0 && requiredFields.length > 0;

  const handleFieldChange = (canonical: string, src: string | null) => {
    setMapping((prev) => ({ ...prev, [canonical]: src }));
  };

  const handleConfirm = () => {
    if (!canConfirm) return;
    onConfirm(mapping);
  };

  // Keyboard: Escape to close (matches existing modal pattern).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  // Build the live preview table cells: for each canonical field's
  // selected source column, look up the first 5 string values from
  // `previewRows`. If no preview data was supplied, render an empty
  // row to avoid layout shift.
  const previewFields = fieldSchema.filter((f) => mapping[f.name] && previewRows);
  const previewColumnNames = previewFields.map((f) => mapping[f.name] ?? '');
  const previewRowCount = previewRows
    ? Math.min(5, Math.max(...previewColumnNames.map((c) => previewRows[c]?.length ?? 0), 0))
    : 0;

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="column-mapper-title"
      data-testid="column-mapper-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.55)' }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-5xl max-h-[90vh] flex flex-col rounded-xl border shadow-2xl glass-panel"
        style={{
          backgroundColor: 'var(--color-surface)',
          borderColor: 'var(--color-border)',
        }}
      >
        {/* Header */}
        <div
          className="flex items-start justify-between gap-3 p-4"
          style={{ borderBottom: '1px solid var(--color-border)' }}
        >
          <div className="min-w-0">
            <p
              className="text-[10px] uppercase tracking-widest font-semibold"
              style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('columnMapper.eyebrow', { defaultValue: 'MAPEO DE COLUMNAS' })}
            </p>
            <h2
              id="column-mapper-title"
              className="text-lg font-semibold mt-0.5"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {t('columnMapper.title', { defaultValue: 'Asignar columnas del archivo' })}
            </h2>
            <p className="text-xs mt-1" style={{ color: 'var(--color-text-muted)' }}>
              {t('columnMapper.subtitle', {
                defaultValue:
                  '{{n}} columnas detectadas. Asigna cada campo canónico a una columna del archivo.',
                n: columns.length,
              })}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label={t('common.close', { defaultValue: 'Cerrar' })}
            className="text-2xl leading-none px-2"
            style={{ color: 'var(--color-text-muted)' }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {/* Error banner */}
          {detect.isError && (
            <div
              role="alert"
              data-testid="column-mapper-error"
              className="text-xs px-3 py-2 rounded-md border"
              style={{
                borderColor: 'var(--color-status-error, #ef4444)',
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                color: 'var(--color-status-error, #ef4444)',
              }}
            >
              {t('columnMapper.error', {
                defaultValue: 'No se pudo auto-detectar el mapeo. Asigna las columnas manualmente.',
              })}
              <button
                type="button"
                onClick={() => detect.mutate({ columns })}
                disabled={detect.isPending}
                className="ml-3 underline"
              >
                {t('common.retry', { defaultValue: 'Reintentar' })}
              </button>
            </div>
          )}

          {/* Summary banner */}
          {detect.isSuccess && detect.data && (
            <div
              data-testid="column-mapper-summary"
              className="text-xs px-3 py-2 rounded-md border"
              style={{
                borderColor: 'var(--color-border)',
                backgroundColor: 'var(--color-surface-muted)',
                color: 'var(--color-text-secondary)',
              }}
            >
              {t('columnMapper.summary', {
                defaultValue:
                  '{{done}} de {{total}} campos requeridos cubiertos · {{missing}} faltantes.',
                done: requiredFields.length - missingRequired.length,
                total: requiredFields.length,
                missing: missingRequired.length,
              })}
            </div>
          )}

          {/* Mapping table */}
          <div className="overflow-auto rounded-lg border" style={{ borderColor: 'var(--color-border)' }}>
            <table className="w-full">
              <thead>
                <tr
                  style={{
                    backgroundColor: 'var(--color-surface-muted)',
                    borderBottom: '1px solid var(--color-border)',
                  }}
                >
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--color-text-muted)' }}>
                    {t('columnMapper.col_field', { defaultValue: 'Campo canónico' })}
                  </th>
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--color-text-muted)' }}>
                    {t('columnMapper.col_description', { defaultValue: 'Descripción' })}
                  </th>
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--color-text-muted)' }}>
                    {t('columnMapper.col_source', { defaultValue: 'Columna del archivo' })}
                  </th>
                </tr>
              </thead>
              <tbody>
                {detect.isPending && fieldSchema.length === 0 && (
                  <tr>
                    <td
                      colSpan={3}
                      className="text-center text-xs py-6"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {t('columnMapper.loading', { defaultValue: 'Auto-detectando…' })}
                    </td>
                  </tr>
                )}
                {fieldSchema.map((field) => (
                  <FieldRow
                    key={field.name}
                    field={field}
                    value={mapping[field.name] ?? null}
                    columns={columns}
                    mappedByOther={mappedByOther.get(field.name) ?? new Set()}
                    confidenceKind={
                      detect.data?.confidence[field.name]?.kind ?? undefined
                    }
                    onChange={(src) => handleFieldChange(field.name, src)}
                    isRequired={field.required}
                    isMissing={!mapping[field.name]}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Live preview */}
          <div>
            <p
              className="text-[10px] uppercase tracking-widest font-semibold mb-1.5"
              style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('columnMapper.preview_title', {
                defaultValue: 'Vista previa (primeras 5 filas)',
              })}
            </p>
            {previewFields.length === 0 ? (
              <p className="text-xs italic" style={{ color: 'var(--color-text-muted)' }}>
                {t('columnMapper.preview_empty', {
                  defaultValue:
                    'Asigna al menos un campo con una columna para ver la vista previa.',
                })}
              </p>
            ) : (
              <div className="overflow-auto rounded-lg border" style={{ borderColor: 'var(--color-border)' }}>
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ backgroundColor: 'var(--color-surface-muted)' }}>
                      {previewFields.map((f) => (
                        <th
                          key={f.name}
                          className="text-left px-2 py-1 font-mono font-semibold"
                          style={{ color: 'var(--color-text-primary)' }}
                        >
                          {f.name}
                          <span
                            className="ml-1 font-normal"
                            style={{ color: 'var(--color-text-muted)' }}
                          >
                            ({mapping[f.name]})
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: previewRowCount }).map((_, i) => (
                      <tr
                        // eslint-disable-next-line react/no-array-index-key
                        key={i}
                        style={{ borderTop: '1px solid var(--color-border)' }}
                      >
                        {previewFields.map((f) => {
                          const src = mapping[f.name];
                          const value = src && previewRows ? previewRows[src]?.[i] : '';
                          return (
                            <td
                              key={f.name}
                              className="px-2 py-1 font-mono"
                              style={{ color: 'var(--color-text-secondary)' }}
                            >
                              {value ?? ''}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                    {previewRowCount === 0 && (
                      <tr>
                        <td
                          colSpan={previewFields.length}
                          className="text-center italic py-2"
                          style={{ color: 'var(--color-text-muted)' }}
                        >
                          {t('columnMapper.preview_no_rows', {
                            defaultValue: 'Sin datos para mostrar.',
                          })}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between gap-3 p-4"
          style={{ borderTop: '1px solid var(--color-border)' }}
        >
          <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {missingRequired.length > 0
              ? t('columnMapper.missing_required', {
                  defaultValue:
                    'Faltan campos requeridos: {{names}}.',
                  names: missingRequired.join(', '),
                })
              : t('columnMapper.ready', {
                  defaultValue: 'Listo para confirmar.',
                })}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-3 py-1.5 rounded-md border text-xs"
              style={{
                borderColor: 'var(--color-border)',
                color: 'var(--color-text-primary)',
                backgroundColor: 'var(--color-surface)',
              }}
            >
              {t('common.cancel', { defaultValue: 'Cancelar' })}
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!canConfirm || detect.isPending}
              data-testid="column-mapper-confirm"
              className="px-3 py-1.5 rounded-md border text-xs font-semibold transition-opacity disabled:opacity-50"
              style={{
                borderColor: 'var(--color-accent)',
                backgroundColor: 'var(--color-accent)',
                color: 'var(--color-accent-fg, #fff)',
              }}
            >
              {t('common.confirm', { defaultValue: 'Confirmar' })}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ColumnMapper;
