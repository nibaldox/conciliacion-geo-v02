/**
 * BenchTable — sortable table of benches for the current section.
 *
 * Each row = one bench. Columns: #, Elev, Height, Angle, Berm, Status.
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
 * numbers, status pill on the right.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Bench } from '../domain/types';
import type { SortField, SortDirection } from '../domain/sorting';
import { cycleSort, SORT_FIELDS } from '../domain/sorting';
import { type UseCrossLinkStateApi, useSortedBenches } from '../application';
import { StatusPill } from './atoms/StatusPill';
import { StatusDot } from './atoms/StatusDot';
import { getStatusClass } from '../../../../utils/format';

export interface BenchTableProps {
  readonly benches: readonly Bench[];
  readonly crossLink: UseCrossLinkStateApi;
  /** Initial sort (defaults to benchNumber asc). */
  readonly initialField?: SortField;
  readonly initialDirection?: SortDirection;
  /** When the chart emits a click on a bench marker, the parent
   *  should call this with the bench number so the row scrolls
   *  into view. We accept it as a ref-like prop. */
  readonly scrollToBenchNumber?: number | null;
}

interface SortState {
  field: SortField;
  direction: SortDirection;
}

const COLUMN_LABELS: Record<SortField, string> = {
  benchNumber: '#',
  crestElevation: 'Elev (m)',
  designHeight: 'Alt (D)',
  height: 'Alt (R)',
  designAngle: 'Áng (D)',
  faceAngle: 'Áng (R)',
  designBerm: 'Berma (D)',
  bermWidth: 'Berma (R)',
  status: 'Est',
};

const COLUMN_ALIGN: Record<SortField, 'left' | 'right'> = {
  benchNumber: 'left',
  crestElevation: 'right',
  designHeight: 'right',
  height: 'right',
  designAngle: 'right',
  faceAngle: 'right',
  designBerm: 'right',
  bermWidth: 'right',
  status: 'left',
};

export function BenchTable({
  benches,
  crossLink,
  initialField = 'benchNumber',
  initialDirection = 'asc',
  scrollToBenchNumber,
}: BenchTableProps) {
  const { t } = useTranslation();
  const [sort, setSort] = useState<SortState>({ field: initialField, direction: initialDirection });
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  // Apply sort. We use the hook (memoised) and feed it the live
  // sort state via the comparator factory.
  const sorted = useSortedBenches(
    benches,
    sort.field,
    sort.direction,
  );

  // Scroll a specific row into view when the chart's crossLink
  // selects a bench.
  useEffect(() => {
    if (scrollToBenchNumber == null) return;
    const row = rowRefs.current.get(scrollToBenchNumber);
    if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [scrollToBenchNumber]);

  const handleHeaderClick = useCallback((field: SortField) => {
    setSort((current) => cycleSort(current, field) ?? { field: 'benchNumber', direction: 'asc' });
  }, []);

  const headerCell = (field: SortField, customLabel?: string) => {
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
          'sticky top-0 px-3 py-2 text-[11px] uppercase tracking-wider font-semibold',
          'select-none cursor-pointer hover:opacity-80',
          COLUMN_ALIGN[field] === 'right' ? 'text-right' : 'text-left',
        ].join(' ')}
        style={{
          backgroundColor: 'var(--color-surface)',
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
        {customLabel ?? COLUMN_LABELS[field]} <span className="opacity-50">{next}</span>
      </th>
    );
  };

  if (benches.length === 0) {
    return (
      <div
        data-slot="bench-table"
        className="px-4 py-8 text-center text-sm"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {t('profileView.table.empty', { defaultValue: 'No hay bancos detectados en esta sección.' })}
      </div>
    );
  }

  return (
    <div
      data-slot="bench-table"
      className="overflow-auto max-h-72 rounded-lg"
      style={{ border: '1px solid var(--color-border)' }}
    >
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {SORT_FIELDS.map((f) => headerCell(f))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((b) => {
            const isHovered = crossLink.hovered === b.benchNumber;
            const isSelected = crossLink.selected === b.benchNumber;
            const rowClass = [
              'transition-colors duration-100',
              isSelected ? 'bg-[var(--color-mine-blue)]/8' : isHovered ? 'bg-[var(--color-surface-muted)]' : '',
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
                data-bench-number={b.benchNumber}
                data-hovered={isHovered || undefined}
                data-selected={isSelected || undefined}
              >
                <td className="px-3 py-2 text-left">
                  <span className="inline-flex items-center gap-2">
                    <StatusDot status={b.status} title={b.status} />
                    <span className="tabular-nums font-medium">{b.benchNumber}</span>
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{b.crestElevation.toFixed(1)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{b.designHeight === null ? '—' : b.designHeight.toFixed(1)}</td>
                <td className="px-3 py-2 text-right">
                  <span className={`inline-block px-1.5 py-0.5 rounded font-mono text-[11px] font-semibold ${getStatusClass(b.heightStatus)}`}>
                    {b.height.toFixed(1)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{b.designAngle === null ? '—' : b.designAngle.toFixed(0)}°</td>
                <td className="px-3 py-2 text-right">
                  <span className={`inline-block px-1.5 py-0.5 rounded font-mono text-[11px] font-semibold ${getStatusClass(b.angleStatus)}`}>
                    {b.faceAngle.toFixed(0)}°
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {b.designBerm === null ? '—' : b.designBerm.toFixed(1)}
                </td>
                <td className="px-3 py-2 text-right">
                  <span className={`inline-block px-1.5 py-0.5 rounded font-mono text-[11px] font-semibold ${b.bermWidth === null ? '' : getStatusClass(b.bermStatus)}`}>
                    {b.bermWidth === null ? '—' : b.bermWidth.toFixed(1)}
                  </span>
                </td>
                <td className="px-3 py-2 text-center">
                  <StatusPill status={b.status} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
