import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

export interface BlastHole3DRecord {
  row_id: string;
  hole_id: string;
  collar: number[] | null;
  toe: number[] | null;
  geometry_status: string;
  provenance: Record<string, unknown>;
  attributes: Record<string, unknown>;
  section_relation: string | null;
  section_distance_m: number | null;
  source_row_index?: number | null;
}

export interface BlastHoleFilterCounts {
  total: number;
  drawable: number;
  visible: number;
  excludedGeometry: number;
}

export interface BlastHoleFiltersProps<T extends BlastHole3DRecord = BlastHole3DRecord> {
  holes: readonly T[];
  hasSection?: boolean;
  initialCorridorM?: number;
  value?: BlastHoleFilterState;
  onChange?: (value: BlastHoleFilterState) => void;
  compact?: boolean;
  onFilteredChange?: (holes: T[], corridorM: number, counts: BlastHoleFilterCounts) => void;
}

export interface BlastHoleFilterState {
  query: string;
  bench: string;
  grid: string[];
  polygon: string[];
  originalBench: string[];
  phase: string[];
  depthMin: string;
  depthMax: string;
  chargeMin: string;
  chargeMax: string;
  date: string;
  datePresence?: string;
  geometryStatus: string;
  provenance: string;
  surfaceSampleStatus: string;
  sectionRelation: string;
  corridorM: number;
}

const BENCH_KEYS = ['bench_num_topo', 'bench_num', 'bench', 'Banco_Original'];
const DATE_KEYS = ['fecha_tronadura', 'fecha', 'Fecha_Tronadura', 'Fecha'];
const EVENT_KEYS = ['event_id'];
const FILTER_COLUMNS = {
  grid: ['Nombre_Malla_Original'],
  polygon: ['holes_polygon'],
  originalBench: ['Banco_Original', 'Nombre_Banco', 'Banco'],
  phase: ['Nombre_Fase', 'Fase'],
} as const;
const DEPTH_KEYS = ['Len', 'longitud_real'];
const CHARGE_KEYS = ['Kilos_Cargados_real', 'Kilos_Cargados', 'Carga_kg', 'Explosivo_kg'];
const MISSING_VALUE = '__missing__';
const PRESENT_VALUE = '__present__';
const PROVENANCE_LABELS: Record<string, string> = {
  design_surface_estimate: 'blast.holeFilters.provenance.design_surface_estimate',
  bench_elevation: 'blast.holeFilters.provenance.bench_elevation',
  collar_elevation: 'blast.holeFilters.provenance.collar_elevation',
  sampled: 'blast.holeFilters.provenance.sampled',
  outside: 'blast.holeFilters.provenance.outside',
  ambiguous: 'blast.holeFilters.provenance.ambiguous',
  invalid: 'blast.holeFilters.provenance.invalid',
};

function textValue(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

function firstAttribute(attributes: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = textValue(attributes[key]);
    if (value) return value;
  }
  return '';
}

function drawable(hole: BlastHole3DRecord): boolean {
  return Array.isArray(hole.collar) && hole.collar.length === 3 && hole.collar.every(Number.isFinite);
}

function numericValue(value: unknown): number | null {
  if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) return null;
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function matchesRange(value: unknown, lower: string, upper: string): boolean {
  if (lower === '' && upper === '') return true;
  const number = numericValue(value);
  if (number === null) return false;
  return (lower === '' || number >= Number(lower)) && (upper === '' || number <= Number(upper));
}

export function filterBlastHoles<T extends BlastHole3DRecord>(
  holes: readonly T[],
  filters: BlastHoleFilterState,
): T[] {
  const query = filters.query.trim().toLocaleLowerCase();
  const categoryAttributeKeys = Object.fromEntries(Object.entries(FILTER_COLUMNS).map(([key, aliases]) => [
    key, resolveAttributeKey(holes, aliases),
  ])) as Record<keyof typeof FILTER_COLUMNS, string | undefined>;
  const depthAttributeKey = resolveAttributeKey(holes, DEPTH_KEYS);
  const chargeAttributeKey = resolveAttributeKey(holes, CHARGE_KEYS);
  return holes.filter((hole) => {
    if (query && !hole.hole_id.toLocaleLowerCase().includes(query)) return false;
    for (const filterKey of Object.keys(FILTER_COLUMNS) as (keyof typeof FILTER_COLUMNS)[]) {
      const selected = filters[filterKey];
      if (selected.length) {
        const attributeKey = categoryAttributeKeys[filterKey];
        if (!attributeKey || !selected.includes(textValue(hole.attributes[attributeKey]))) return false;
      }
    }
    if (!matchesRange(depthAttributeKey ? hole.attributes[depthAttributeKey] : undefined, filters.depthMin, filters.depthMax)) return false;
    if (!matchesRange(chargeAttributeKey ? hole.attributes[chargeAttributeKey] : undefined, filters.chargeMin, filters.chargeMax)) return false;
    const bench = firstAttribute(hole.attributes, BENCH_KEYS);
    if (filters.bench === MISSING_VALUE && bench) return false;
    if (filters.bench && filters.bench !== MISSING_VALUE && bench !== filters.bench) return false;
    const date = firstAttribute(hole.attributes, DATE_KEYS);
    if (filters.datePresence === MISSING_VALUE && date) return false;
    if (filters.datePresence === PRESENT_VALUE && !date) return false;
    const event = firstAttribute(hole.attributes, EVENT_KEYS);
    if (filters.date) {
      const search = filters.date.toLocaleLowerCase();
      if (!date.toLocaleLowerCase().includes(search) && !event.toLocaleLowerCase().includes(search)) return false;
    }
    if (filters.geometryStatus && hole.geometry_status !== filters.geometryStatus) return false;
    const provenance = textValue(hole.provenance.z_collar_semantic);
    if (filters.provenance === MISSING_VALUE && provenance) return false;
    if (filters.provenance && filters.provenance !== MISSING_VALUE && provenance !== filters.provenance) return false;
    const surfaceSampleStatus = textValue(hole.provenance.surface_sample_status);
    if (filters.surfaceSampleStatus === MISSING_VALUE && surfaceSampleStatus) return false;
    if (filters.surfaceSampleStatus && filters.surfaceSampleStatus !== MISSING_VALUE && surfaceSampleStatus !== filters.surfaceSampleStatus) return false;
    if (filters.sectionRelation) {
      if (filters.sectionRelation === 'near_section') {
        if (hole.section_relation === 'incomplete' || hole.section_relation === 'exact_intersection' ||
            hole.section_distance_m === null || hole.section_distance_m > filters.corridorM) return false;
      } else if (filters.sectionRelation === 'outside') {
        if (hole.section_distance_m === null || hole.section_distance_m <= filters.corridorM) return false;
      } else if (hole.section_relation !== filters.sectionRelation) {
        return false;
      }
    }
    return true;
  });
}

function defaultFilterState(initialCorridorM: number): BlastHoleFilterState {
  return {
    query: '', bench: '', grid: [], polygon: [], originalBench: [], phase: [],
    depthMin: '', depthMax: '', chargeMin: '', chargeMax: '', date: '', datePresence: '', geometryStatus: '', provenance: '', surfaceSampleStatus: '', sectionRelation: '',
    corridorM: Number.isFinite(initialCorridorM) ? Math.max(0, initialCorridorM) : 10,
  };
}

export function BlastHoleFilters<T extends BlastHole3DRecord = BlastHole3DRecord>({
  holes,
  hasSection = false,
  initialCorridorM = 10,
  onFilteredChange,
  value,
  onChange,
  compact = false,
}: BlastHoleFiltersProps<T>) {
  const { t } = useTranslation();
  const [localFilters, setLocalFilters] = useState<BlastHoleFilterState>(() => defaultFilterState(initialCorridorM));
  const controlled = value !== undefined;
  const filters = value ?? localFilters;
  const [filtersClearedNotice, setFiltersClearedNotice] = useState(false);
  const currentFiltersRef = useRef(filters);
  currentFiltersRef.current = filters;
  const commit = (next: BlastHoleFilterState) => {
    currentFiltersRef.current = next;
    if (controlled) onChange?.(next);
    else setLocalFilters(next);
  };
  const commitRef = useRef(commit);
  commitRef.current = commit;

  useEffect(() => {
    const current = currentFiltersRef.current;
    if (!hasSection && current.sectionRelation) commitRef.current({ ...current, sectionRelation: '' });
  }, [hasSection]);

  const update = (key: keyof BlastHoleFilterState, value: string | number | string[]) => {
    setFiltersClearedNotice(false);
    commitRef.current({ ...currentFiltersRef.current, [key]: value });
  };
  const benches = useMemo(() => [...new Set(holes.map((hole) => firstAttribute(hole.attributes, BENCH_KEYS)).filter(Boolean))].sort(), [holes]);
  const statuses = useMemo(() => [...new Set(holes.map((hole) => hole.geometry_status).filter(Boolean))].sort(), [holes]);
  const provenances = useMemo(() => [...new Set(holes.map((hole) => textValue(hole.provenance.z_collar_semantic)).filter(Boolean))].sort(), [holes]);
  const surfaceSampleStatuses = useMemo(() => [...new Set(holes.map((hole) => textValue(hole.provenance.surface_sample_status)).filter(Boolean))].sort(), [holes]);
  const categoryAttributeKeys = useMemo(() => Object.fromEntries(Object.entries(FILTER_COLUMNS).map(([key, aliases]) => [
    key, resolveAttributeKey(holes, aliases),
  ])) as Record<keyof typeof FILTER_COLUMNS, string | undefined>, [holes]);
  const categoryOptions = useMemo(() => Object.fromEntries(Object.keys(FILTER_COLUMNS).map((key) => {
    const attribute = categoryAttributeKeys[key as keyof typeof FILTER_COLUMNS];
    return [key, attribute
      ? [...new Set(holes.map((hole) => textValue(hole.attributes[attribute])).filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
      : []];
  })) as Record<keyof typeof FILTER_COLUMNS, string[]>, [holes, categoryAttributeKeys]);
  const depthAttributeKey = useMemo(() => resolveAttributeKey(holes, DEPTH_KEYS), [holes]);
  const chargeAttributeKey = useMemo(() => resolveAttributeKey(holes, CHARGE_KEYS), [holes]);
  const depthExtent = useMemo(() => numericExtent(holes, depthAttributeKey), [holes, depthAttributeKey]);
  const chargeExtent = useMemo(() => numericExtent(holes, chargeAttributeKey), [holes, chargeAttributeKey]);
  const availabilityKey = [categoryAttributeKeys.grid, categoryAttributeKeys.polygon, categoryAttributeKeys.originalBench,
    categoryAttributeKeys.phase, depthAttributeKey, chargeAttributeKey].map((key) => Number(key !== undefined)).join('');
  const effectiveFilters = useMemo(() => ({
    ...filters,
    grid: categoryAttributeKeys.grid ? filters.grid : [],
    polygon: categoryAttributeKeys.polygon ? filters.polygon : [],
    originalBench: categoryAttributeKeys.originalBench ? filters.originalBench : [],
    phase: categoryAttributeKeys.phase ? filters.phase : [],
    depthMin: depthAttributeKey ? filters.depthMin : '',
    depthMax: depthAttributeKey ? filters.depthMax : '',
    chargeMin: chargeAttributeKey ? filters.chargeMin : '',
    chargeMax: chargeAttributeKey ? filters.chargeMax : '',
  }), [filters, categoryAttributeKeys, depthAttributeKey, chargeAttributeKey]);
  const filtered = useMemo(() => filterBlastHoles(holes, effectiveFilters), [holes, effectiveFilters]);
  const baseCounts = useMemo(() => ({
    total: holes.length,
    drawable: holes.filter(drawable).length,
    excludedGeometry: holes.filter((hole) => !drawable(hole)).length,
  }), [holes]);
  const counts = useMemo<BlastHoleFilterCounts>(() => ({
    ...baseCounts,
    visible: filtered.filter(drawable).length,
  }), [baseCounts, filtered]);

  useEffect(() => {
    const [gridAvailable, polygonAvailable, originalBenchAvailable, phaseAvailable, depthAvailable, chargeAvailable] = availabilityKey.split('').map((value) => value === '1');
    const current = currentFiltersRef.current;
    const grid = gridAvailable ? current.grid : [];
    const polygon = polygonAvailable ? current.polygon : [];
    const originalBench = originalBenchAvailable ? current.originalBench : [];
    const phase = phaseAvailable ? current.phase : [];
    const depthMin = depthAvailable ? current.depthMin : '';
    const depthMax = depthAvailable ? current.depthMax : '';
    const chargeMin = chargeAvailable ? current.chargeMin : '';
    const chargeMax = chargeAvailable ? current.chargeMax : '';
    let nextGrid = grid;
    let nextPolygon = polygon;
    let nextOriginalBench = originalBench;
    let nextPhase = phase;
    let nextBench = current.bench;
    let nextDatePresence = current.datePresence ?? '';
    let nextGeometryStatus = current.geometryStatus;
    let nextProvenance = current.provenance;
    let nextSurfaceSampleStatus = current.surfaceSampleStatus;

    if (holes.length > 0) {
      const availableValues = (keys: readonly string[]) => {
        const key = resolveAttributeKey(holes, keys);
        return new Set(key ? holes.map((hole) => textValue(hole.attributes[key])).filter(Boolean) : []);
      };
      const retainAvailable = (selected: string[], values: Set<string>) => selected.filter((value) => values.has(value));
      nextGrid = retainAvailable(grid, availableValues(FILTER_COLUMNS.grid));
      nextPolygon = retainAvailable(polygon, availableValues(FILTER_COLUMNS.polygon));
      nextOriginalBench = retainAvailable(originalBench, availableValues(FILTER_COLUMNS.originalBench));
      nextPhase = retainAvailable(phase, availableValues(FILTER_COLUMNS.phase));

      const benchValues = new Set(holes.map((hole) => firstAttribute(hole.attributes, BENCH_KEYS)).filter(Boolean));
      const dateValues = holes.map((hole) => firstAttribute(hole.attributes, DATE_KEYS));
      const geometryValues = new Set(holes.map((hole) => hole.geometry_status).filter(Boolean));
      const provenanceValues = new Set(holes.map((hole) => textValue(hole.provenance.z_collar_semantic)).filter(Boolean));
      const surfaceSampleValues = new Set(holes.map((hole) => textValue(hole.provenance.surface_sample_status)).filter(Boolean));
      if (nextBench === MISSING_VALUE ? !holes.some((hole) => !firstAttribute(hole.attributes, BENCH_KEYS)) : nextBench && !benchValues.has(nextBench)) nextBench = '';
      if (nextDatePresence === MISSING_VALUE && !dateValues.some((value) => !value)) nextDatePresence = '';
      if (nextDatePresence === PRESENT_VALUE && !dateValues.some(Boolean)) nextDatePresence = '';
      if (nextGeometryStatus && !geometryValues.has(nextGeometryStatus)) nextGeometryStatus = '';
      if (nextProvenance === MISSING_VALUE ? !holes.some((hole) => !textValue(hole.provenance.z_collar_semantic)) : nextProvenance && !provenanceValues.has(nextProvenance)) nextProvenance = '';
      if (nextSurfaceSampleStatus === MISSING_VALUE ? !holes.some((hole) => !textValue(hole.provenance.surface_sample_status)) : nextSurfaceSampleStatus && !surfaceSampleValues.has(nextSurfaceSampleStatus)) nextSurfaceSampleStatus = '';
    }

    const removedUnavailableFilters = nextGrid.length !== current.grid.length || nextPolygon.length !== current.polygon.length ||
      nextOriginalBench.length !== current.originalBench.length || nextPhase.length !== current.phase.length ||
      nextBench !== current.bench || nextDatePresence !== (current.datePresence ?? '') ||
      nextGeometryStatus !== current.geometryStatus || nextProvenance !== current.provenance ||
      nextSurfaceSampleStatus !== current.surfaceSampleStatus ||
      depthMin !== current.depthMin || depthMax !== current.depthMax || chargeMin !== current.chargeMin || chargeMax !== current.chargeMax;

    if (removedUnavailableFilters) {
      commitRef.current({ ...current, grid: nextGrid, polygon: nextPolygon, originalBench: nextOriginalBench, phase: nextPhase,
        bench: nextBench, datePresence: nextDatePresence, geometryStatus: nextGeometryStatus, provenance: nextProvenance,
        surfaceSampleStatus: nextSurfaceSampleStatus, depthMin, depthMax, chargeMin, chargeMax });
      setFiltersClearedNotice(true);
    } else {
      setFiltersClearedNotice(false);
    }
  }, [availabilityKey, holes]);

  useEffect(() => {
    onFilteredChange?.(filtered, filters.corridorM, counts);
  }, [filtered, filters.corridorM, counts, onFilteredChange]);
  const resetFilters = () => {
    setFiltersClearedNotice(false);
    commit(defaultFilterState(initialCorridorM));
  };

  const gridControl = categoryAttributeKeys.grid && <SearchMultiSelect label={t('blast.holeFilters.grid', { defaultValue: 'Malla (Grid)' })} options={categoryOptions.grid} selected={filters.grid} onChange={(value) => update('grid', value)} searchLabel={t('blast.holeFilters.searchOptions', { defaultValue: 'Buscar mallas' })} />;
  const polygonControl = categoryAttributeKeys.polygon && <SearchMultiSelect label={t('blast.holeFilters.polygon', { defaultValue: 'Polígono' })} options={categoryOptions.polygon} selected={filters.polygon} onChange={(value) => update('polygon', value)} searchLabel={t('blast.holeFilters.searchOptions', { defaultValue: 'Buscar polígonos' })} />;
  const originalBenchControl = categoryAttributeKeys.originalBench && <SearchMultiSelect label={t('blast.holeFilters.originalBench', { defaultValue: 'Banco de tronadura' })} options={categoryOptions.originalBench} selected={filters.originalBench} onChange={(value) => update('originalBench', value)} searchLabel={t('blast.holeFilters.searchOptions', { defaultValue: 'Buscar bancos' })} />;
  const phaseControl = categoryAttributeKeys.phase && <SearchMultiSelect label={t('blast.holeFilters.phase', { defaultValue: 'Fase' })} options={categoryOptions.phase} selected={filters.phase} onChange={(value) => update('phase', value)} searchLabel={t('blast.holeFilters.searchOptions', { defaultValue: 'Buscar fases' })} />;
  const depthControl = depthAttributeKey && <RangeFilter label={t('blast.holeFilters.depthRange', { defaultValue: 'Profundidad (m)' })} min={filters.depthMin} max={filters.depthMax} extent={depthExtent} minLabel={t('blast.holeFilters.minimum', { defaultValue: 'Mínimo' })} maxLabel={t('blast.holeFilters.maximum', { defaultValue: 'Máximo' })} onMinChange={(value) => update('depthMin', value)} onMaxChange={(value) => update('depthMax', value)} />;
  const chargeControl = chargeAttributeKey && <RangeFilter label={t('blast.holeFilters.chargeRange', { defaultValue: 'Explosivo (kg)' })} min={filters.chargeMin} max={filters.chargeMax} extent={chargeExtent} minLabel={t('blast.holeFilters.minimum', { defaultValue: 'Mínimo' })} maxLabel={t('blast.holeFilters.maximum', { defaultValue: 'Máximo' })} onMinChange={(value) => update('chargeMin', value)} onMaxChange={(value) => update('chargeMax', value)} />;
  const idControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.id')}</span>
      <input className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" value={filters.query} onChange={(event) => update('query', event.target.value)} />
    </label>
  );
  const benchControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.bench')}</span>
      <select className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" value={filters.bench} onChange={(event) => update('bench', event.target.value)}>
        <option value="">{t('blast.holeFilters.any')}</option>
        <option value={MISSING_VALUE}>{t('blast.noData')}</option>
        {benches.map((bench) => <option key={bench} value={bench}>{bench}</option>)}
      </select>
    </label>
  );
  const dateControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.dateEvent')}</span>
      <select aria-label={t('blast.holeFilters.datePresence', { defaultValue: 'Presencia de fecha' })} className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" value={filters.datePresence ?? ''} onChange={(event) => update('datePresence', event.target.value)}>
        <option value="">{t('blast.holeFilters.any')}</option>
        <option value={PRESENT_VALUE}>{t('blast.holeFilters.withDate', { defaultValue: 'Con fecha' })}</option>
        <option value={MISSING_VALUE}>{t('blast.noData')}</option>
      </select>
      <input className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" value={filters.date} onChange={(event) => update('date', event.target.value)} placeholder={t('blast.holeFilters.datePlaceholder')} />
    </label>
  );
  const geometryControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.geometry')}</span>
      <select className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" value={filters.geometryStatus} onChange={(event) => update('geometryStatus', event.target.value)}>
        <option value="">{t('blast.holeFilters.any')}</option>
        {statuses.map((status) => <option key={status} value={status}>{t(`blast.holeFilters.geometryStatus.${status}`, status)}</option>)}
      </select>
    </label>
  );
  const provenanceControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.collarProvenanceLabel', { defaultValue: 'Procedencia de cota' })}</span>
      <select className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" value={filters.provenance} onChange={(event) => update('provenance', event.target.value)}>
        <option value="">{t('blast.holeFilters.any')}</option>
        <option value={MISSING_VALUE}>{t('blast.noData')}</option>
        {provenances.map((status) => <option key={status} value={status}>{PROVENANCE_LABELS[status] ? t(PROVENANCE_LABELS[status]) : status}</option>)}
      </select>
    </label>
  );
  const surfaceControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.surfaceSampleStatusLabel', { defaultValue: 'Estado de muestreo de superficie' })}</span>
      <select className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" value={filters.surfaceSampleStatus} onChange={(event) => update('surfaceSampleStatus', event.target.value)}>
        <option value="">{t('blast.holeFilters.any')}</option>
        <option value={MISSING_VALUE}>{t('blast.noData')}</option>
        {surfaceSampleStatuses.map((status) => <option key={status} value={status}>{PROVENANCE_LABELS[status] ? t(PROVENANCE_LABELS[status]) : status}</option>)}
      </select>
    </label>
  );
  const sectionControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.section')}</span>
      <select disabled={!hasSection} className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm disabled:opacity-50" value={filters.sectionRelation} onChange={(event) => update('sectionRelation', event.target.value)}>
        <option value="">{t('blast.holeFilters.any')}</option>
        {['exact_intersection', 'near_section', 'outside', 'incomplete'].map((relation) => <option key={relation} value={relation}>{t(`blast.holeFilters.relation.${relation}`)}</option>)}
      </select>
    </label>
  );
  const corridorControl = (
    <label className="space-y-1 text-xs">
      <span>{t('blast.holeFilters.corridor')}</span>
      <input disabled={!hasSection} type="number" min="0" step="1" inputMode="decimal" className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm disabled:opacity-50" value={filters.corridorM} onChange={(event) => update('corridorM', Math.max(0, Number(event.target.value) || 0))} />
    </label>
  );

  const gridStyle = { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))' };
  const compactGridStyle = { gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 140px), 1fr))' };
  const advancedControls: [string, ReactNode][] = [['polygon', polygonControl], ['originalBench', originalBenchControl], ['phase', phaseControl],
    ['depth', depthControl], ['charge', chargeControl], ['date', dateControl], ['geometry', geometryControl], ['provenance', provenanceControl],
    ['surface', surfaceControl], ['section', sectionControl], ['corridor', corridorControl]];

  return (
    <fieldset className="space-y-3 rounded-lg border border-[var(--color-border)] p-3" aria-label={t('blast.holeFilters.title')}>
      <legend className="px-1 text-sm font-semibold">{t('blast.holeFilters.title')}</legend>
      {compact ? (
        <>
          <div className="grid gap-2" style={compactGridStyle}>
            <div className="col-span-full">{idControl}</div>
            {benchControl}
            {gridControl}
          </div>
          <details className="rounded border border-[var(--color-border)] p-2">
            <summary className="min-h-10 cursor-pointer py-2 text-sm font-medium">{t('blast.holeFilters.advanced', { defaultValue: 'Filtros avanzados' })}</summary>
            <div className="mt-2 grid gap-2" style={compactGridStyle}>
              {advancedControls.map(([key, control]) => <Fragment key={key}>{control}</Fragment>)}
            </div>
          </details>
        </>
      ) : (
        <div className="grid gap-2" style={gridStyle}>
          {idControl}
          {gridControl}
          {polygonControl}
          {originalBenchControl}
          {phaseControl}
          {depthControl}
          {chargeControl}
          {benchControl}
          {dateControl}
          {geometryControl}
          {provenanceControl}
          {surfaceControl}
          {sectionControl}
          {corridorControl}
        </div>
      )}
      {!hasSection && <p className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.chooseSection')}</p>}
      {filtersClearedNotice && <p role="status" className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.unavailableFiltersCleared', { defaultValue: 'Se limpiaron filtros porque sus columnas ya no están disponibles.' })}</p>}
      {hasSection && <p className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.corridorHelp')}</p>}
      <p className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.estimateHelp')}</p>
      <button type="button" className="min-h-10 rounded border border-[var(--color-border)] px-3 py-2 text-sm" onClick={resetFilters}>{t('blast.holeFilters.clear')}</button>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs" aria-live="polite">
        <span>{t('blast.holeFilters.countTotal', { count: counts.total })}</span>
        <span>{t('blast.holeFilters.countDrawable', { count: counts.drawable })}</span>
        <span>{t('blast.holeFilters.countVisible', { count: counts.visible })}</span>
        <span>{t('blast.holeFilters.countExcluded', { count: counts.excludedGeometry })}</span>
      </div>
    </fieldset>
  );

}

function resolveAttributeKey(holes: readonly BlastHole3DRecord[], keys: readonly string[]): string | undefined {
  return keys.find((key) => holes.some((hole) => Object.prototype.hasOwnProperty.call(hole.attributes, key)));
}

function numericExtent(holes: readonly BlastHole3DRecord[], attributeKey: string | undefined): [number, number] | null {
  if (!attributeKey) return null;
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const hole of holes) {
    const value = numericValue(hole.attributes[attributeKey]);
    if (value !== null) {
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
  }
  return Number.isFinite(min) ? [min, max] : null;
}

function SearchMultiSelect({
  label, options, selected, onChange, searchLabel,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (value: string[]) => void;
  searchLabel: string;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return options.filter((option) => !normalized || option.toLocaleLowerCase().includes(normalized)).slice(0, 100);
  }, [options, query]);
  const toggle = (option: string) => onChange(selected.includes(option) ? selected.filter((value) => value !== option) : [...selected, option]);
  return (
    <fieldset className="min-w-0 space-y-1 rounded border border-[var(--color-border)] p-2">
      <legend className="px-1 text-xs font-medium">{label}</legend>
      <input aria-label={`${searchLabel}: ${label}`} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={searchLabel} className="w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" />
      {selected.length > 0 && <p className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.selectedCount', { count: selected.length, defaultValue: '{{count}} seleccionados' })}</p>}
      <div className="max-h-24 overflow-y-auto" role="group" aria-label={label}>
        {visible.map((option) => <label key={option} className="flex min-h-10 items-center gap-2 py-1 text-sm"><input className="h-4 w-4 shrink-0" type="checkbox" checked={selected.includes(option)} onChange={() => toggle(option)} /> <span className="truncate">{option}</span></label>)}
        {visible.length === 0 && <p className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.noMatches', { defaultValue: 'Sin coincidencias' })}</p>}
        {visible.length === 100 && <p className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.refineSearch', { defaultValue: 'Refina la búsqueda para ver más opciones.' })}</p>}
      </div>
      {selected.length > 0 && <button type="button" className="min-h-10 px-1 text-sm underline" onClick={() => onChange([])}>{t('blast.holeFilters.clearCategory', { label: label.toLocaleLowerCase(), defaultValue: 'Limpiar {{label}}' })}</button>}
    </fieldset>
  );
}

function RangeFilter({
  label, min, max, extent, minLabel, maxLabel, onMinChange, onMaxChange,
}: {
  label: string;
  min: string;
  max: string;
  extent: [number, number] | null;
  minLabel: string;
  maxLabel: string;
  onMinChange: (value: string) => void;
  onMaxChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <fieldset className="min-w-0 space-y-1 rounded border border-[var(--color-border)] p-2">
      <legend className="px-1 text-xs font-medium">{label}</legend>
      <div className="grid grid-cols-2 gap-2">
        <label className="space-y-1 text-xs"><span>{minLabel}</span><input aria-label={`${label}: ${minLabel}`} type="number" inputMode="decimal" min={extent?.[0]} max={max || extent?.[1]} value={min} onChange={(event) => onMinChange(event.target.value)} className="w-full min-w-0 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" /></label>
        <label className="space-y-1 text-xs"><span>{maxLabel}</span><input aria-label={`${label}: ${maxLabel}`} type="number" inputMode="decimal" min={min || extent?.[0]} max={extent?.[1]} value={max} onChange={(event) => onMaxChange(event.target.value)} className="w-full min-w-0 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm" /></label>
      </div>
      {extent && <p className="text-xs text-[var(--color-text-secondary)]">{t('blast.holeFilters.dataExtent', { min: extent[0], max: extent[1], defaultValue: 'Datos: {{min}} – {{max}}' })}</p>}
    </fieldset>
  );
}
