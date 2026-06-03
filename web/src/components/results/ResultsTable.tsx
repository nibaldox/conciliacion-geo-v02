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

function StatusBadge({ status }: { status: string }) {
  const cls = getStatusClass(status);
  if (!cls) return <span className="text-gray-400 text-xs">—</span>;
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
}

function MatchBadge({ type }: { type: MatchType }) {
  const cls = getMatchClass(type);
  const labels: Record<MatchType, string> = {
    MATCH: 'Match',
    MISSING: 'Faltante',
    EXTRA: 'Extra',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {labels[type] ?? type}
    </span>
  );
}

export function ResultsTable() {
  const { filters } = useSession();
  const { data: results, isLoading, error } = useResults();

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
        header: 'Sección',
        size: 100,
      },
      {
        accessorKey: 'bench_num',
        header: 'Banco',
        size: 70,
        cell: ({ getValue }) => `B${getValue<number>()}`,
      },
      {
        accessorKey: 'type',
        header: 'Tipo',
        size: 90,
        cell: ({ getValue }) => <MatchBadge type={getValue() as MatchType} />,
      },
      // Height group
      {
        accessorKey: 'height_design',
        header: 'Alt. Diseño (m)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'height_real',
        header: 'Alt. Real (m)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'height_dev',
        header: 'Desv. (m)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'height_status',
        header: 'Estado',
        size: 110,
        cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
      },
      // Angle group
      {
        accessorKey: 'angle_design',
        header: 'Áng. Diseño (°)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDegrees(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'angle_real',
        header: 'Áng. Real (°)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDegrees(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'angle_dev',
        header: 'Desv. (°)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatDeviation(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'angle_status',
        header: 'Estado',
        size: 110,
        cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
      },
      // Berm group
      {
        accessorKey: 'berm_design',
        header: 'Berma D. (m)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'berm_real',
        header: 'Berma R. (m)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'berm_min',
        header: 'Mín. (m)',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs">{formatMeters(getValue<number | null>())}</span>
        ),
      },
      {
        accessorKey: 'berm_status',
        header: 'Estado',
        size: 110,
        cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
      },
    ],
    [],
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
        Cargando resultados...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-sm" style={{ color: '#ef4444' }}>
        Error al cargar los resultados
      </div>
    );
  }

  if (filteredData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        No hay resultados disponibles. Ejecuta el procesamiento primero.
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
            Página {table.getState().pagination.pageIndex + 1} de{' '}
            {table.getPageCount()}
          </span>
          <span style={{ color: 'var(--color-border-strong)' }}>|</span>
          <span>{filteredData.length} resultados</span>
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
