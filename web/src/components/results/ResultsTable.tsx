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
        header: 'Alt. Diseño',
        size: 90,
        cell: ({ getValue }) => formatMeters(getValue<number | null>()),
      },
      {
        accessorKey: 'height_real',
        header: 'Alt. Real',
        size: 90,
        cell: ({ getValue }) => formatMeters(getValue<number | null>()),
      },
      {
        accessorKey: 'height_dev',
        header: 'Alt. Desv.',
        size: 90,
        cell: ({ getValue }) => formatDeviation(getValue<number | null>()),
      },
      {
        accessorKey: 'height_status',
        header: 'Alt. Estado',
        size: 110,
        cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
      },
      // Angle group
      {
        accessorKey: 'angle_design',
        header: 'Áng. Diseño',
        size: 90,
        cell: ({ getValue }) => formatDegrees(getValue<number | null>()),
      },
      {
        accessorKey: 'angle_real',
        header: 'Áng. Real',
        size: 90,
        cell: ({ getValue }) => formatDegrees(getValue<number | null>()),
      },
      {
        accessorKey: 'angle_dev',
        header: 'Áng. Desv.',
        size: 90,
        cell: ({ getValue }) => formatDeviation(getValue<number | null>()),
      },
      {
        accessorKey: 'angle_status',
        header: 'Áng. Estado',
        size: 110,
        cell: ({ getValue }) => <StatusBadge status={getValue<string>()} />,
      },
      // Berm group
      {
        accessorKey: 'berm_design',
        header: 'Berma Diseño',
        size: 100,
        cell: ({ getValue }) => formatMeters(getValue<number | null>()),
      },
      {
        accessorKey: 'berm_real',
        header: 'Berma Real',
        size: 100,
        cell: ({ getValue }) => formatMeters(getValue<number | null>()),
      },
      {
        accessorKey: 'berm_min',
        header: 'Berma Mín.',
        size: 100,
        cell: ({ getValue }) => formatMeters(getValue<number | null>()),
      },
      {
        accessorKey: 'berm_status',
        header: 'Berma Estado',
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
      <div className="flex items-center justify-center h-64 gap-3 text-gray-500">
        <svg className="animate-spin h-5 w-5 text-mine-blue" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Cargando resultados...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-red-500 text-sm">
        Error al cargar los resultados
      </div>
    );
  }

  if (filteredData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
        No hay resultados disponibles. Ejecuta el procesamiento primero.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="bg-gray-50 border-b border-gray-200">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 whitespace-nowrap cursor-pointer hover:bg-gray-100 select-none"
                    style={{ width: header.getSize() }}
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
                className={`border-b border-gray-100 hover:bg-gray-50 transition-colors ${
                  i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'
                }`}
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className="px-3 py-2 text-gray-700 whitespace-nowrap"
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
      <div className="flex items-center justify-between text-sm text-gray-600">
        <div className="flex items-center gap-2">
          <span>
            Página {table.getState().pagination.pageIndex + 1} de{' '}
            {table.getPageCount()}
          </span>
          <span className="text-gray-400">|</span>
          <span>{filteredData.length} resultados</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => table.setPageIndex(0)}
            disabled={!table.getCanPreviousPage()}
            className="px-2 py-1 rounded border border-gray-300 text-xs hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            «
          </button>
          <button
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
            className="px-2 py-1 rounded border border-gray-300 text-xs hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ‹
          </button>
          <button
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
            className="px-2 py-1 rounded border border-gray-300 text-xs hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ›
          </button>
          <button
            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
            disabled={!table.getCanNextPage()}
            className="px-2 py-1 rounded border border-gray-300 text-xs hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            »
          </button>
        </div>
      </div>
    </div>
  );
}
