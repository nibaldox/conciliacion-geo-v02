import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Bench, BenchStatus, ComparisonBenchStatus } from '../domain/types';
import type { SortField, SortDirection } from '../domain/sorting';
import { cycleSort, SORT_FIELDS } from '../domain/sorting';
import { BENCH_PASSING_SCORE, STATUS_FG_VAR } from '../domain/status';
import { type UseCrossLinkStateApi, useSortedBenches } from '../application';
import { StatusDot } from './atoms/StatusDot';

type TableSortField = Exclude<SortField, 'status'>;

const TABLE_SORT_FIELDS = SORT_FIELDS.filter(
  (field): field is TableSortField => field !== 'status',
);

export interface BenchTableProps {
  readonly benches: readonly Bench[];
  readonly crossLink: UseCrossLinkStateApi;
  readonly selectedDesignBenchNumbers?: readonly number[];
  readonly comparisonBenchStatuses?: readonly ComparisonBenchStatus[];
  readonly initialField?: TableSortField;
  readonly initialDirection?: SortDirection;
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

const HEADER_CLASS = 'sticky top-0 z-[1] whitespace-nowrap border-b border-border bg-surface-raised px-3 py-2 text-xs font-normal';
const CELL_CLASS = 'px-3 py-1.5 text-right tabular-nums';

function StatusValue({ status, children }: { status: BenchStatus | null; children: ReactNode }) {
  if (status === null) return <span className="text-text-muted">{children}</span>;
  return (
    <span data-value-status={status} className="font-medium" style={{ color: status === 'UNKNOWN' ? undefined : STATUS_FG_VAR[status] }}>
      {children}
    </span>
  );
}

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

  const visibleBenches = selectedDesignBenchNumbers.length === 0
    ? benches
    : benches.filter((bench) => bench.designBenchNumber != null && selectedDesignBenchNumbers.includes(bench.designBenchNumber));
  const sorted = useSortedBenches(visibleBenches, sort.field, sort.direction);
  const missingDesignBenches = comparisonBenchStatuses.filter((bench) => !bench.hasTopo && !bench.isAdditional);

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

  const headerCell = (field: TableSortField) => {
    const isActive = sort.field === field;
    const next = isActive ? (sort.direction === 'asc' ? '↓' : '↑') : '↕';
    const ariaSort: 'ascending' | 'descending' | 'none' = isActive
      ? sort.direction === 'asc' ? 'ascending' : 'descending'
      : 'none';
    return (
      <th
        key={field}
        scope="col"
        aria-sort={ariaSort}
        className={[
          HEADER_CLASS,
          'cursor-pointer select-none hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent',
          isActive ? 'text-text-primary' : 'text-text-muted',
          COLUMN_ALIGN[field] === 'right' ? 'text-right' : 'text-left',
        ].join(' ')}
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
        {t('profileView.table.columns.' + field, { defaultValue: COLUMN_LABELS[field] })}{' '}
        <span className={isActive ? 'opacity-70' : 'opacity-30'} aria-hidden="true">{next}</span>
      </th>
    );
  };

  if (visibleBenches.length === 0) {
    return (
      <div data-slot="bench-table" className="px-4 py-8 text-center text-sm text-text-muted">
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
    <div data-slot="bench-table" className="max-h-[440px] overflow-auto">
      {missingDesignBenches.length > 0 && (
        <p role="status" className="flex items-center gap-2 border-b border-border px-4 py-1.5 text-xs text-text-secondary">
          <span aria-hidden="true" className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: 'var(--status-warn-text)' }} />
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
            <th scope="col" className={`${HEADER_CLASS} text-right text-text-muted`}>{t('profileView.table.columns.floor')}</th>
            <th scope="col" className={`${HEADER_CLASS} text-right text-text-muted`}>{t('profileView.table.columns.score')}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((b) => {
            const isHovered = crossLink.hovered === b.benchNumber;
            const isSelected = crossLink.selected === b.benchNumber;
            const rowClass = [
              'cursor-pointer border-t border-border transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent',
              isSelected ? 'bg-accent-bg' : isHovered ? 'bg-surface-muted' : '',
            ].join(' ');
            return (
              <tr
                key={b.benchNumber}
                ref={(el) => {
                  if (el) rowRefs.current.set(b.benchNumber, el);
                  else rowRefs.current.delete(b.benchNumber);
                }}
                className={rowClass}
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
                <td className="px-3 py-1.5 text-left">
                  <span className="inline-flex items-center gap-2">
                    <StatusDot status={b.status} title={b.status} />
                    <span className="tabular-nums font-medium">{b.matchType === 'EXTRA'
                      ? t('profileView.table.additional_topo', { number: b.benchNumber, defaultValue: 'Adicional topo · {{number}}' })
                      : b.benchNumber}</span>
                  </span>
                </td>
                <td className={CELL_CLASS}>{b.crestElevation.toFixed(1)}</td>
                <td className={`${CELL_CLASS} text-text-muted`}>{b.designHeight === null ? '—' : b.designHeight.toFixed(1)}</td>
                <td className={CELL_CLASS}><StatusValue status={b.heightStatus}>{b.height.toFixed(1)}</StatusValue></td>
                <td className={`${CELL_CLASS} text-text-muted`}>{b.designAngle === null ? '—' : b.designAngle.toFixed(0)}°</td>
                <td className={CELL_CLASS}><StatusValue status={b.angleStatus}>{b.faceAngle.toFixed(0)}°</StatusValue></td>
                <td className={`${CELL_CLASS} text-text-muted`}>{b.designBerm === null ? '—' : b.designBerm.toFixed(1)}</td>
                <td className={CELL_CLASS}>
                  {b.bermWidth === null
                    ? <StatusValue status={null}>—</StatusValue>
                    : <StatusValue status={b.bermStatus}>{b.bermWidth.toFixed(1)}</StatusValue>}
                </td>
                <td className={CELL_CLASS}>{b.floorElevation != null ? b.floorElevation.toFixed(1) : '—'}</td>
                <td className={CELL_CLASS}>
                  {b.benchScore != null
                    ? <StatusValue status={b.benchScore >= BENCH_PASSING_SCORE ? 'CUMPLE' : 'NO_CUMPLE'}>{b.benchScore.toFixed(0)}</StatusValue>
                    : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
