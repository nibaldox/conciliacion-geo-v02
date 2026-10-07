import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import type { DxfImportReport, DxfInspectResponse, MeshType } from '../../api/types';

const UNIT_FACTORS: Record<number, number> = { 6: 1, 4: 0.001, 5: 0.01, 2: 0.3048, 1: 0.0254, 21: 1200 / 3937 };
const UNIT_OPTIONS = [6, 4, 5, 2, 1, 21];

interface DxfImportDialogProps {
  report: DxfInspectResponse;
  type: MeshType;
  busy: boolean;
  error: string | null;
  onConfirm: (layers: string[], units: number) => void;
  onCancel: () => void;
}

export function DxfImportDialog({ report, type, busy, error, onConfirm, onCancel }: DxfImportDialogProps) {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const compatibleLayers = useMemo(() => report.layers.filter((layer) => layer.n_faces > 0), [report.layers]);
  const [selectedLayers, setSelectedLayers] = useState<string[]>(() => compatibleLayers.length === 1 ? [compatibleLayers[0].name] : []);
  const [units, setUnits] = useState(() => UNIT_FACTORS[report.declared_units] ? report.declared_units : 0);
  const factor = UNIT_FACTORS[units] ?? 1;
  const selected = compatibleLayers.filter((layer) => selectedLayers.includes(layer.name));
  const totals = selected.reduce((sum, layer) => sum + layer.n_faces, 0);
  const bounds = selected.reduce((box, layer) => {
    if (!layer.bounds) return box;
    return {
      xmin: Math.min(box.xmin, layer.bounds.xmin), xmax: Math.max(box.xmax, layer.bounds.xmax),
      ymin: Math.min(box.ymin, layer.bounds.ymin), ymax: Math.max(box.ymax, layer.bounds.ymax),
      zmin: Math.min(box.zmin, layer.bounds.zmin), zmax: Math.max(box.zmax, layer.bounds.zmax),
    };
  }, { xmin: Infinity, xmax: -Infinity, ymin: Infinity, ymax: -Infinity, zmin: Infinity, zmax: -Infinity });

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cancelRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel();
      if (event.key === 'Tab' && dialogRef.current) {
        const items = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled])'));
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus();
    };
  }, [busy, onCancel]);

  const toggleLayer = (name: string) => setSelectedLayers((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  const warningText = (code: string) => {
    const translated = t(`step1.dxf.warning.${code}`, { defaultValue: '' });
    if (translated) return translated;
    if (code.startsWith('UNSUPPORTED_')) return t('step1.dxf.warning.unsupported_type', { entity: code.slice('UNSUPPORTED_'.length) });
    if (code.startsWith('INSERT_ENTITY_SKIPPED_')) return t('step1.dxf.warning.insert_entity_skipped', { entity: code.slice('INSERT_ENTITY_SKIPPED_'.length) });
    return t('step1.dxf.warning.generic');
  };
  const hasBounds = Number.isFinite(bounds.xmin);

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-text-primary/60 p-4" role="presentation">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="dxf-dialog-title" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-border bg-surface p-5 text-text-primary shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div><h2 id="dxf-dialog-title" className="text-lg font-semibold">{t('step1.dxf.title', { role: t(type === 'design' ? 'step1.design' : 'step1.topo') })}</h2><p className="mt-1 break-all text-sm text-text-muted">{report.filename}</p></div>
          <button ref={cancelRef} type="button" onClick={onCancel} disabled={busy} className="rounded px-2 py-1 text-sm text-text-secondary hover:bg-surface-muted disabled:opacity-50">{t('common.cancel')}</button>
        </div>
        <section className="mt-5">
          <h3 className="text-sm font-semibold">{t('step1.dxf.layers')}</h3>
          {compatibleLayers.length ? <ul className="mt-2 space-y-2">
            {report.layers.map((layer) => <li key={layer.name} className="rounded-lg border border-border p-3">
              {layer.n_faces > 0 ? <label className="flex cursor-pointer items-start gap-2"><input type="checkbox" checked={selectedLayers.includes(layer.name)} onChange={() => toggleLayer(layer.name)} disabled={busy} className="mt-1" /><span className="min-w-0 flex-1"><span className="block break-words text-sm font-medium">{layer.name || t('step1.dxf.unnamed_layer')}</span><span className="block text-xs text-text-muted">{t('step1.dxf.layer_stats', { faces: layer.n_faces, vertices: layer.n_vertices })}</span></span></label> : <div className="text-sm text-text-muted"><span className="font-medium">{layer.name || t('step1.dxf.unnamed_layer')}</span> · {t('step1.dxf.no_faces')}</div>}
            </li>)}
          </ul> : <p className="mt-2 text-sm text-status-error-text">{t('step1.dxf.no_surfaces')}</p>}
        </section>
        <section className="mt-5">
          <label htmlFor="dxf-units" className="block text-sm font-semibold">{t('step1.dxf.units')}</label>
          <select id="dxf-units" value={units} onChange={(event) => setUnits(Number(event.target.value))} disabled={busy} className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm">
            <option value={0}>{t('step1.dxf.choose_units')}</option>
            {UNIT_OPTIONS.map((unit) => <option key={unit} value={unit}>{t(`step1.dxf.unit_${unit}`)}</option>)}
          </select>
          {units > 0 && <p className="mt-2 text-xs text-text-muted">{t('step1.dxf.scale', { factor: factor.toPrecision(8) })}</p>}
        </section>
        {hasBounds && <section className="mt-4 rounded-lg bg-surface-muted p-3 text-xs text-text-secondary" aria-live="polite">
          <h3 className="font-semibold">{t('step1.dxf.extent', { faces: totals })}</h3>
          <p className="mt-1">X { (bounds.xmin * factor).toFixed(3) } – { (bounds.xmax * factor).toFixed(3) }{units > 0 ? ' m' : ''} · Y { (bounds.ymin * factor).toFixed(3) } – { (bounds.ymax * factor).toFixed(3) }{units > 0 ? ' m' : ''} · Z { (bounds.zmin * factor).toFixed(3) } – { (bounds.zmax * factor).toFixed(3) }{units > 0 ? ' m' : ''}</p>
        </section>}
        <p className="mt-4 text-xs text-text-muted">{t('step1.dxf.entities')}: {Object.entries(report.entity_counts).map(([name, count]) => `${name} ${count}`).join(' · ') || t('step1.dxf.none')}</p>
        {report.warnings.length > 0 && <section className="mt-4"><h3 className="text-sm font-semibold">{t('step1.dxf.warnings')}</h3><ul className="mt-1 list-disc pl-5 text-sm text-text-secondary">{report.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warningText(warning)}</li>)}</ul></section>}
        {error && <p role="alert" className="mt-4 rounded-lg border border-status-nok-border bg-status-nok-bg p-3 text-sm text-status-nok-text">{error}</p>}
        <div className="mt-5 flex justify-end gap-3">
          <button type="button" onClick={onCancel} disabled={busy} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-surface-muted disabled:opacity-50">{t('common.cancel')}</button>
          <button type="button" onClick={() => onConfirm(selectedLayers, units)} disabled={busy || selectedLayers.length === 0 || units === 0} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">{busy ? t('step1.dxf.confirming') : t('step1.dxf.confirm')}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function DxfImportSummary({ report }: { report: DxfImportReport }) {
  const { t } = useTranslation();
  const warningText = (code: string) => {
    const translated = t(`step1.dxf.warning.${code}`, { defaultValue: '' });
    if (translated) return translated;
    if (code.startsWith('UNSUPPORTED_')) return t('step1.dxf.warning.unsupported_type', { entity: code.slice('UNSUPPORTED_'.length) });
    if (code.startsWith('INSERT_ENTITY_SKIPPED_')) return t('step1.dxf.warning.insert_entity_skipped', { entity: code.slice('INSERT_ENTITY_SKIPPED_'.length) });
    return t('step1.dxf.warning.generic');
  };
  return (
    <div className="mt-2 rounded-lg border border-border bg-surface-muted p-2 text-xs text-text-secondary">
      <p>{t('step1.dxf.imported_layers', { layers: report.selected_layers.join(', ') })}</p>
      <p className="mt-1">{t('step1.dxf.imported_scale', { factor: report.scale_factor.toPrecision(8) })}</p>
      {report.warnings.length > 0 && <ul className="mt-1 list-disc pl-4">{report.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warningText(warning)}</li>)}</ul>}
    </div>
  );
}
