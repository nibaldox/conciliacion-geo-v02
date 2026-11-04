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
  getStatusClass,
  getMatchClass,
} from '../../utils/format';
import type { ComparisonResult, MatchType } from '../../api/types';
import { filterResults, type ResultFilterState } from './resultFilters.utils';

interface ResultsTableProps {
  filters?: ResultFilterState;
  onFiltersChange?: (filters: ResultFilterState) => void;
  ResultFiltersComponent?: React.ComponentType<{ results: ComparisonResult[]; filters: ResultFilterState; onChange: (filters: ResultFilterState) => void }>;
}

function MatchBadge({ type, t }: { type: MatchType; t: (k: string) => string }) {
  const cls = getMatchClass(type);
  const key = `table.status_${type.toLowerCase()}`;
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
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
          <span className="font-mono text-xs">{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'delta_toe',
        header: t('table.col_delta_toe', { defaultValue: 'Δ Pata' }),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      // Height group
      {
        accessorKey: 'height_design',
        header: t('table.col_height_design'),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'height_real',
        header: t('table.col_height_real'),
        size: 90,
        cell: ({ row, getValue }) => (
          <span className={`inline-block px-2 py-0.5 rounded font-mono text-xs font-semibold ${getStatusClass(row.original.height_status)}`}>
            {formatMeters(getValue<number | null>())}
          </span>
        ),
      },
      {
        accessorKey: 'height_dev',
        header: t('table.col_height_dev'),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      // Angle group
      {
        accessorKey: 'angle_design',
        header: t('table.col_angle_design'),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDegrees(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'angle_real',
        header: t('table.col_angle_real'),
        size: 90,
        cell: ({ row, getValue }) => (
          <span className={`inline-block px-2 py-0.5 rounded font-mono text-xs font-semibold ${getStatusClass(row.original.angle_status)}`}>
            {formatDegrees(getValue<number | null>())}
          </span>
        ),
      },
      {
        accessorKey: 'angle_dev',
        header: t('table.col_angle_dev'),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      // Berm group
      {
        accessorKey: 'berm_design',
        header: t('table.col_berm_design'),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'berm_real',
        header: t('table.col_berm_real'),
        size: 90,
        cell: ({ row, getValue }) => (
          <span className={`inline-block px-2 py-0.5 rounded font-mono text-xs font-semibold ${getStatusClass(row.original.berm_status)}`}>
            {formatMeters(getValue<number | null>())}
          </span>
        ),
      },
      {
        accessorKey: 'berm_min',
        header: t('table.col_berm_min'),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'spill_width',
        header: t('table.col_spill', { defaultValue: 'B. Derrame (m)' }),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'effective_berm',
        header: t('table.col_berm_effective', { defaultValue: 'B. Efectiva (m)' }),
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
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
      <div className="flex items-center justify-center h-64 text-sm" style={{ color: '#ef4444' }}>
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
      <div className="flex items-center gap-2 text-sm">
        <label htmlFor="results-order" style={{ color: 'var(--color-text-secondary)' }}>
          {t('table.order_label', { defaultValue: 'Orden' })}
        </label>
        <select
          id="results-order"
          value={orderMode}
          onChange={(e) => setOrderMode(e.target.value as OrderMode)}
          className="px-2 py-1 rounded"
          style={{ border: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}
        >
          <option value="section">{t('table.order_by_section', { defaultValue: 'Por Sección' })}</option>
          <option value="level">{t('table.order_by_level', { defaultValue: 'Por Nivel' })}</option>
        </select>
      </div>
      <div className="overflow-x-auto rounded-lg shadow-sm" style={{ border: '1px solid var(--color-border)' }}>
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} style={{ backgroundColor: 'var(--color-surface-muted)', borderBottom: '2px solid var(--color-border)' }}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide whitespace-nowrap cursor-pointer select-none"
                    style={{ width: header.getSize(), color: 'var(--color-text-secondary)' }}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <div className="flex items-center gap-1">
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
            {table.getRowModel().rows.map((row, i) => (
              <tr
                key={row.id}
                className="transition-colors"
                style={{
                  backgroundColor: i % 2 === 0 ? 'var(--color-surface)' : 'var(--color-surface-muted)',
                  borderBottom: '1px solid var(--color-border)',
                }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className="px-3 py-2 whitespace-nowrap"
                    style={{ color: 'var(--color-text-primary)' }}
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
      <div className="flex items-center justify-between text-sm px-1" style={{ color: 'var(--color-text-muted)' }}>
        <div className="flex items-center gap-2">
          <span>
            {t('table.page_info', {
              page: table.getState().pagination.pageIndex + 1,
              total: table.getPageCount(),
            })}
          </span>
          <span style={{ color: 'var(--color-border-strong)' }}>|</span>
          <span>{t('table.n_results', { count: filteredData.length })}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
            className="px-2 py-1 rounded text-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            «
          </button>
          <button
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            className="px-2 py-1 rounded text-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            ‹
          </button>
          <button
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            className="px-2 py-1 rounded text-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            ›
          </button>
          <button
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
            className="px-2 py-1 rounded text-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            »
          </button>
        </div>
      </div>
    </div>
  );
}
