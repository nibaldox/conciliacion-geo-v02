/**
 * BenchTable — sortable table of benches for the current section.
 *
 * Each row = one bench. Columns: #, Elev, Height, Angle, Berm, Floor, Score.
 *
 * Cross-link:
 *  - Hover a row → crossLink.setHovered(benchNumber)
 *  - Click a row → crossLink.setSelected(benchNumber) + scroll into view
 *  - The ProfileChart (from Parada 2) reads crossLink.hovered/.selected
 *    and grows the matching bench marker.
 *
 * Sort: click a column header to cycle asc → desc → none. Default is
 * benchNumber asc. Implementation reuses the useSortedBenches hook
 * from the application layer.
 *
 * Visual: sticky header, subtle row borders, right-aligned tabular
 * numbers, status dot beside the bench number.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Bench, ComparisonBenchStatus } from '../domain/types';
import type { SortField, SortDirection } from '../domain/sorting';
import { cycleSort, SORT_FIELDS } from '../domain/sorting';
import { type UseCrossLinkStateApi, useSortedBenches } from '../application';
import { StatusDot } from './atoms/StatusDot';
import { getStatusClass } from '../../../../utils/format';

type TableSortField = Exclude<SortField, 'status'>;

const TABLE_SORT_FIELDS = SORT_FIELDS.filter(
  (field): field is TableSortField => field !== 'status',
);

export interface BenchTableProps {
  readonly benches: readonly Bench[];
  readonly crossLink: UseCrossLinkStateApi;
  readonly selectedDesignBenchNumbers?: readonly number[];
  readonly comparisonBenchStatuses?: readonly ComparisonBenchStatus[];
  /** Initial sort (defaults to benchNumber asc). */
  readonly initialField?: TableSortField;
  readonly initialDirection?: SortDirection;
  /** When the chart emits a click on a bench marker, the parent
   *  should call this with the bench number so the row scrolls
   *  into view. We accept it as a ref-like prop. */
  readonly scrollToBenchNumber?: number | null;
}

interface SortState {
  field: TableSortField;
  direction: SortDirection;
}

const COLUMN_LABELS: Record<TableSortField, string> = {
  benchNumber: '#',
  crestElevation: 'Elev (m)',
  designHeight: 'Alt (D)',
  height: 'Alt (R)',
  designAngle: 'Áng (D)',
  faceAngle: 'Áng (R)',
  designBerm: 'Berma (D)',
  bermWidth: 'Berma (R)',
};

const COLUMN_ALIGN: Record<TableSortField, 'left' | 'right'> = {
  benchNumber: 'left',
  crestElevation: 'right',
  designHeight: 'right',
  height: 'right',
  designAngle: 'right',
  faceAngle: 'right',
  designBerm: 'right',
  bermWidth: 'right',
};

export function BenchTable({
  benches,
  crossLink,
  selectedDesignBenchNumbers = [],
  comparisonBenchStatuses = [],
  initialField = 'benchNumber',
  initialDirection = 'asc',
  scrollToBenchNumber,
}: BenchTableProps) {
  const { t } = useTranslation();
  const [sort, setSort] = useState<SortState>({ field: initialField, direction: initialDirection });
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  // Apply sort. We use the hook (memoised) and feed it the live
  // sort state via the comparator factory.
  const visibleBenches = selectedDesignBenchNumbers.length === 0
    ? benches
    : benches.filter((bench) => bench.designBenchNumber != null && selectedDesignBenchNumbers.includes(bench.designBenchNumber));
  const sorted = useSortedBenches(
    visibleBenches,
    sort.field,
    sort.direction,
  );
  const missingDesignBenches = comparisonBenchStatuses.filter((bench) => !bench.hasTopo && !bench.isAdditional);

  // Scroll a specific row into view when the chart's crossLink
  // selects a bench.
  useEffect(() => {
    if (scrollToBenchNumber == null) return;
    const row = rowRefs.current.get(scrollToBenchNumber);
    if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [scrollToBenchNumber]);

  const handleHeaderClick = useCallback((field: TableSortField) => {
    setSort((current) => {
      const next = cycleSort(current, field);
      return next === null
        ? { field: 'benchNumber', direction: 'asc' }
        : { ...next, field };
    });
  }, []);

  const headerCell = (field: TableSortField, customLabel?: string) => {
    const isActive = sort.field === field;
    const next = isActive
      ? sort.direction === 'asc'
        ? '↓'
        : '↑'
      : '↕';
    const ariaSort: 'ascending' | 'descending' | 'none' = isActive
      ? sort.direction === 'asc' ? 'ascending' : 'descending'
      : 'none';
    return (
      <th
        key={field}
        scope="col"
        aria-sort={ariaSort}
        className={[
          'sticky top-0 px-3 py-2 text-xs whitespace-nowrap font-semibold',
          'select-none cursor-pointer hover:opacity-80',
          COLUMN_ALIGN[field] === 'right' ? 'text-right' : 'text-left',
        ].join(' ')}
        style={{
          backgroundColor: 'var(--color-surface-muted)',
          color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
          borderBottom: '1px solid var(--color-border)',
        }}
        onClick={() => handleHeaderClick(field)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleHeaderClick(field);
          }
        }}
        tabIndex={0}
        data-testid={`sort-header-${field}`}
      >
        {customLabel ?? t('profileView.table.columns.' + field, { defaultValue: COLUMN_LABELS[field] })} <span className="opacity-50">{next}</span>
      </th>
    );
  };

  if (visibleBenches.length === 0) {
    return (
      <div
        data-slot="bench-table"
        className="px-4 py-8 text-center text-sm"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {missingDesignBenches.length
          ? t('profileView.table.missing_design', {
              defaultValue: 'Cota base de diseño {{elevation}} m: sin banco topográfico emparejado.',
              elevation: missingDesignBenches.map((bench) => bench.designElevation?.toFixed(0) ?? '—').join(', '),
            })
          : t(selectedDesignBenchNumbers.length ? 'profileView.table.empty_filtered' : 'profileView.table.empty', { defaultValue: selectedDesignBenchNumbers.length ? 'El banco de diseño seleccionado no está emparejado en esta sección.' : 'No hay bancos detectados en esta sección.' })}
      </div>
    );
  }

  return (
    <div
      data-slot="bench-table"
      className="overflow-auto max-h-[440px]"
    >
      {missingDesignBenches.length > 0 && (
        <p role="status" className="border-b border-border px-4 py-2 text-xs text-status-warn-text">
          {t('profileView.table.missing_design_many', {
            defaultValue: 'Sin banco topográfico emparejado para cotas de diseño: {{elevations}} m.',
            elevations: missingDesignBenches.map((bench) => bench.designElevation?.toFixed(0) ?? '—').join(', '),
          })}
        </p>
      )}
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {TABLE_SORT_FIELDS.map((f) => headerCell(f))}
            <th scope="col" className="sticky top-0 px-3 py-2 text-xs whitespace-nowrap font-semibold text-right" style={{ backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>{t('profileView.table.columns.floor')}</th>
            <th scope="col" className="sticky top-0 px-3 py-2 text-xs whitespace-nowrap font-semibold text-center" style={{ backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)', borderBottom: '1px solid var(--color-border)' }}>{t('profileView.table.columns.score')}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((b) => {
            const isHovered = crossLink.hovered === b.benchNumber;
            const isSelected = crossLink.selected === b.benchNumber;
            const rowClass = [
              'cursor-pointer transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent',
              isSelected ? 'bg-accent-bg' : isHovered ? 'bg-[var(--color-surface-muted)]' : '',
            ].join(' ');
            return (
              <tr
                key={b.benchNumber}
                ref={(el) => {
                  if (el) rowRefs.current.set(b.benchNumber, el);
                  else rowRefs.current.delete(b.benchNumber);
                }}
                className={rowClass}
                style={{ borderTop: '1px solid var(--color-border)' }}
                onMouseEnter={() => crossLink.setHovered(b.benchNumber)}
                onMouseLeave={() => crossLink.setHovered(null)}
                onClick={() => crossLink.setSelected(b.benchNumber)}
                tabIndex={0}
                aria-label={t('profileView.inspector.bench', { number: b.benchNumber })}
                onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); crossLink.setSelected(b.benchNumber); } }}
                data-bench-number={b.benchNumber}
                data-match-type={b.matchType ?? 'UNKNOWN'}
                data-hovered={isHovered || undefined}
                data-selected={isSelected || undefined}
              >
                <td className="px-3 py-2 text-left">
                  <span className="inline-flex items-center gap-2">
                    <StatusDot status={b.status} title={b.status} />
                    <span className="tabular-nums font-medium">{b.matchType === 'EXTRA'
                      ? t('profileView.table.additional_topo', { number: b.benchNumber, defaultValue: 'Adicional topo · {{number}}' })
                      : b.benchNumber}</span>
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{b.crestElevation.toFixed(1)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{b.designHeight === null ? '—' : b.designHeight.toFixed(1)}</td>
                <td className="px-3 py-2 text-right">
                  <span className={`inline-block px-1.5 py-0.5 rounded tabular-nums text-sm font-semibold ${getStatusClass(b.heightStatus)}`}>
                    {b.height.toFixed(1)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{b.designAngle === null ? '—' : b.designAngle.toFixed(0)}°</td>
                <td className="px-3 py-2 text-right">
                  <span className={`inline-block px-1.5 py-0.5 rounded tabular-nums text-sm font-semibold ${getStatusClass(b.angleStatus)}`}>
                    {b.faceAngle.toFixed(0)}°
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {b.designBerm === null ? '—' : b.designBerm.toFixed(1)}
                </td>
                <td className="px-3 py-2 text-right">
                  <span className={`inline-block px-1.5 py-0.5 rounded tabular-nums text-sm font-semibold ${b.bermWidth === null ? '' : getStatusClass(b.bermStatus)}`}>
                    {b.bermWidth === null ? '—' : b.bermWidth.toFixed(1)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {b.floorElevation != null ? b.floorElevation.toFixed(1) : '—'}
                </td>
                <td className="px-3 py-2 text-center">
                  {b.benchScore != null ? (
                    <span className={`inline-block px-1.5 py-0.5 rounded tabular-nums text-sm font-semibold ${b.benchScore >= 70 ? 'badge-ok' : 'badge-nok'}`}>
                      {b.benchScore.toFixed(0)}
                    </span>
                  ) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
