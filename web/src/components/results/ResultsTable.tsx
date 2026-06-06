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

function MatchBadge({ type, t }: { type: MatchType; t: (k: string) => string }) {
  const cls = getMatchClass(type);
  const key = `table.status_${type.toLowerCase()}`;
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {t(key)}
    </span>
  );
}

export function ResultsTable() {
  const { filters } = useSession();
  const { data: results, isLoading, error } = useResults();
  const { t } = useTranslation();

  const [sorting, setSorting] = useState<SortingState>([]);

  // Apply filters
  const filteredData = useMemo(() => {
    if (!results) return [];
    let data = results;

    if (filters.sector.length > 0) {
      data = data.filter((r) => filters.sector.includes(r.sector));
    }
    if (filters.section.length > 0) {
      data = data.filter((r) => filters.section.includes(r.section));
    }
    if (filters.level.length > 0) {
      data = data.filter((r) => filters.level.includes(r.level));
    }

    return data;
  }, [results, filters]);

  const columns = useMemo<ColumnDef<ComparisonResult, unknown>[]>(
    () => [
      {
        accessorKey: 'section',
        header: t('table.col_section'),
        size: 100,
      },
      {
        accessorKey: 'bench_num',
        header: t('table.col_bench'),
        size: 70,
        cell: ({ getValue }) => `B${getValue<number>()}`,
      },
      {
        accessorKey: 'type',
        header: t('table.col_type'),
        size: 90,
        cell: ({ getValue }) => <MatchBadge type={getValue() as MatchType} t={t} />,
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
    ],
    [t],
  );

  const table = useReactTable({
    data: filteredData,
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
