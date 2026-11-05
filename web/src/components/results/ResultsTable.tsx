import { useMemo } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useResults } from '../../api/hooks';
import { useSession } from '../../stores/session';
import {
  formatMeters,
  formatDegrees,
  formatDeviation,
  getMatchClass,
} from '../../utils/format';
import type { ComparisonResult, MatchType } from '../../api/types';
import { filterResults, type ResultFilterState } from './resultFilters.utils';

interface ResultsTableProps {
  filters?: ResultFilterState;
  onFiltersChange?: (filters: ResultFilterState) => void;
  ResultFiltersComponent?: React.ComponentType<{ results: ComparisonResult[]; filters: ResultFilterState; onChange: (filters: ResultFilterState) => void }>;
}

const ID_COLUMNS = new Set(['section', 'sector', 'level', 'bench_num', 'type']);

function statusTextColor(status: string): string | undefined {
  const s = (status ?? '').toUpperCase();
  if (s === 'CUMPLE') return 'var(--status-ok-text)';
  if (s.includes('FUERA')) return 'var(--status-warn-text)';
  if (s.includes('NO CUMPLE')) return 'var(--status-nok-text)';
  return undefined;
}

function StatusValue({ status, children }: { status: string; children: React.ReactNode }) {
  const color = statusTextColor(status);
  return (
    <span className="font-medium" style={color ? { color } : undefined}>
      {children}
    </span>
  );
}

function MatchBadge({ type, t }: { type: MatchType; t: (k: string) => string }) {
  const cls = getMatchClass(type);
  const key = `table.status_${type.toLowerCase()}`;
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {t(key)}
    </span>
  );
}

type OrderMode = 'section' | 'level';

function levelNum(level: string): number {
  if (!level || level.trim() === '') return Number.NEGATIVE_INFINITY;
  const n = Number(level);
  return Number.isFinite(n) ? n : Number.NEGATIVE_INFINITY;
}

function compareSections(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function compareByOrder(a: ComparisonResult, b: ComparisonResult, mode: OrderMode): number {
  const la = levelNum(a.level);
  const lb = levelNum(b.level);
  if (mode === 'level') {
    if (lb !== la) return lb - la;
    return compareSections(a.section, b.section);
  }
  const s = compareSections(a.section, b.section);
  return s !== 0 ? s : lb - la;
}

export function ResultsTable({ filters: filtersProp }: ResultsTableProps = {}) {
  const filtersFromSession = useSession((s) => s.filters);
  const filters = filtersProp ?? filtersFromSession;
  const { data: results, isLoading, error } = useResults();
  const { t } = useTranslation();

  const [sorting, setSorting] = useState<SortingState>([]);
  const [orderMode, setOrderMode] = useState<OrderMode>('section');

  const filteredData = useMemo(
    () => filterResults(results ?? [], filters),
    [results, filters],
  );
  const orderedData = useMemo(
    () => [...filteredData].sort((a, b) => compareByOrder(a, b, orderMode)),
    [filteredData, orderMode],
  );

  const idColumns = useMemo<ColumnDef<ComparisonResult, unknown>[]>(() => {
    const sectionCol: ColumnDef<ComparisonResult, unknown> = {
      accessorKey: 'section',
      header: t('table.col_section'),
      size: 100,
    };
    const sectorCol: ColumnDef<ComparisonResult, unknown> = {
      accessorKey: 'sector',
      header: t('table.col_sector', { defaultValue: 'Sector' }),
      size: 90,
      cell: ({ getValue }) => {
        const sector = getValue<string>();
        return sector === '' ? '—' : sector;
      },
    };
    const levelCol: ColumnDef<ComparisonResult, unknown> = {
      accessorKey: 'level',
      header: t('table.col_level', { defaultValue: 'Nivel' }),
      size: 70,
      cell: ({ getValue }) => {
        const level = getValue<string>();
        return level === '' ? '—' : level;
      },
    };
    const benchCol: ColumnDef<ComparisonResult, unknown> = {
      accessorKey: 'bench_num',
      header: t('table.col_bench'),
      size: 70,
      cell: ({ getValue }) => `B${getValue<number>()}`,
    };
    return orderMode === 'level'
      ? [sectorCol, levelCol, sectionCol, benchCol]
      : [sectionCol, sectorCol, levelCol, benchCol];
  }, [t, orderMode]);

  const columns = useMemo<ColumnDef<ComparisonResult, unknown>[]>(
    () => [
      ...idColumns,
      {
        accessorKey: 'type',
        header: t('table.col_type'),
        size: 90,
        cell: ({ getValue }) => <MatchBadge type={getValue() as MatchType} t={t} />,
      },
      {
        accessorKey: 'delta_crest',
        header: t('table.col_delta_crest', { defaultValue: 'Δ Cresta' }),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'delta_toe',
        header: t('table.col_delta_toe', { defaultValue: 'Δ Pata' }),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      // Height group
      {
        accessorKey: 'height_design',
        header: t('table.col_height_design'),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'height_real',
        header: t('table.col_height_real'),
        size: 90,
        cell: ({ row, getValue }) => (
          <StatusValue status={row.original.height_status}>
            {formatMeters(getValue<number | null>())}
          </StatusValue>
        ),
      },
      {
        accessorKey: 'height_dev',
        header: t('table.col_height_dev'),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      // Angle group
      {
        accessorKey: 'angle_design',
        header: t('table.col_angle_design'),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatDegrees(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'angle_real',
        header: t('table.col_angle_real'),
        size: 90,
        cell: ({ row, getValue }) => (
          <StatusValue status={row.original.angle_status}>
            {formatDegrees(getValue<number | null>())}
          </StatusValue>
        ),
      },
      {
        accessorKey: 'angle_dev',
        header: t('table.col_angle_dev'),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      // Berm group
      {
        accessorKey: 'berm_design',
        header: t('table.col_berm_design'),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'berm_real',
        header: t('table.col_berm_real'),
        size: 90,
        cell: ({ row, getValue }) => (
          <StatusValue status={row.original.berm_status}>
            {formatMeters(getValue<number | null>())}
          </StatusValue>
        ),
      },
      {
        accessorKey: 'berm_min',
        header: t('table.col_berm_min'),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'spill_width',
        header: t('table.col_spill', { defaultValue: 'B. Derrame (m)' }),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'effective_berm',
        header: t('table.col_berm_effective', { defaultValue: 'B. Efectiva (m)' }),
        size: 90,
        cell: ({ getValue }) => (
          <span>{formatMeters(getValue<number | null>())}</span>
        ),
      },
    ],
    [t, idColumns],
  );

  const table = useReactTable({
    data: orderedData,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: { pageSize: 25 },
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 gap-3" style={{ color: 'var(--color-text-muted)' }}>
        <svg className="animate-spin h-5 w-5" style={{ color: 'var(--color-mine-blue)' }} viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        {t('table.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-sm" style={{ color: 'var(--status-nok-text)' }}>
        {t('table.loading_error')}
      </div>
    );
  }

  if (filteredData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        {t('table.empty')}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <label htmlFor="results-order" className="text-text-muted">
          {t('table.order_label', { defaultValue: 'Orden' })}
        </label>
        <select
          id="results-order"
          value={orderMode}
          onChange={(e) => setOrderMode(e.target.value as OrderMode)}
          className="h-8 rounded-md border border-border bg-surface-sunken px-2 text-xs text-text-primary"
        >
          <option value="section">{t('table.order_by_section', { defaultValue: 'Por Sección' })}</option>
          <option value="level">{t('table.order_by_level', { defaultValue: 'Por Nivel' })}</option>
        </select>
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-border">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className={`cursor-pointer select-none whitespace-nowrap px-3 py-2 text-xs font-medium text-text-muted hover:text-text-primary ${ID_COLUMNS.has(header.column.id) ? 'text-left' : 'text-right'}`}
                    style={{ width: header.getSize() }}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <div className={`flex items-center gap-1 ${ID_COLUMNS.has(header.column.id) ? '' : 'justify-end'}`}>
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {{
                        asc: ' ↑',
                        desc: ' ↓',
                      }[header.column.getIsSorted() as string] ?? ''}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-border last:border-b-0 hover:bg-surface-muted">
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={`whitespace-nowrap px-3 py-1.5 text-text-primary ${ID_COLUMNS.has(cell.column.id) ? 'text-left' : 'text-right tabular-nums'}`}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      <div className="flex items-center justify-between px-1 text-xs text-text-muted">
        <div className="flex items-center gap-2">
          <span>
            {t('table.page_info', {
              page: table.getState().pagination.pageIndex + 1,
              total: table.getPageCount(),
            })}
          </span>
          <span aria-hidden="true">·</span>
          <span>{t('table.n_results', { count: filteredData.length })}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
            className="rounded-md border border-border px-2 py-0.5 text-xs text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            «
          </button>
          <button
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            className="rounded-md border border-border px-2 py-0.5 text-xs text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            ‹
          </button>
          <button
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            className="rounded-md border border-border px-2 py-0.5 text-xs text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            ›
          </button>
          <button
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
            className="rounded-md border border-border px-2 py-0.5 text-xs text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            »
          </button>
        </div>
      </div>
    </div>
  );
}
