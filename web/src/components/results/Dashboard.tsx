import { useMemo } from 'react';
import { useResults, useSections } from '../../api/hooks';
import { formatPct } from '../../utils/format';

interface KPICardProps {
  title: string;
  value: string;
  colorClass: string;
}

function KPICard({ title, value, colorClass }: KPICardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 flex flex-col items-center gap-1">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {title}
      </span>
      <span className={`text-3xl font-bold ${colorClass}`}>{value}</span>
    </div>
  );
}

function getColorClass(pct: number): string {
  if (pct > 0.8) return 'text-green-600';
  if (pct > 0.6) return 'text-yellow-600';
  return 'text-red-600';
}

function getBarColor(pct: number): string {
  if (pct > 0.8) return 'bg-mine-green';
  if (pct > 0.6) return 'bg-mine-yellow';
  return 'bg-mine-red';
}

export function Dashboard() {
  const { data: results } = useResults();
  const { data: sections } = useSections();

  const stats = useMemo(() => {
    if (!results || results.length === 0) {
      return {
        total: 0,
        globalPct: 0,
        heightPct: 0,
        anglePct: 0,
        bermPct: 0,
        nSections: 0,
      };
    }

    const total = results.length;

    // Global compliance: all three statuses are CUMPLE
    const globalOk = results.filter(
      (r) =>
        r.height_status === 'CUMPLE' &&
        r.angle_status === 'CUMPLE' &&
        r.berm_status === 'CUMPLE',
    ).length;

    // Per-parameter compliance
    const heightOk = results.filter((r) => r.height_status === 'CUMPLE').length;
    const angleOk = results.filter((r) => r.angle_status === 'CUMPLE').length;
    const bermOk = results.filter((r) => r.berm_status === 'CUMPLE').length;

    return {
      total,
      globalPct: globalOk / total,
      heightPct: heightOk / total,
      anglePct: angleOk / total,
      bermPct: bermOk / total,
      nSections: sections?.length ?? 0,
    };
  }, [results, sections]);

  if (!results || results.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        Sin resultados para mostrar. Ejecuta el procesamiento primero.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary text */}
      <p className="text-sm text-gray-500">
        <span className="font-semibold text-gray-700">{stats.total}</span> resultados
        de <span className="font-semibold text-gray-700">{stats.nSections}</span> secciones
      </p>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard
          title="Cumplimiento Global"
          value={formatPct(stats.globalPct)}
          colorClass={getColorClass(stats.globalPct)}
        />
        <KPICard
          title="Altura"
          value={formatPct(stats.heightPct)}
          colorClass={getColorClass(stats.heightPct)}
        />
        <KPICard
          title="Ángulo"
          value={formatPct(stats.anglePct)}
          colorClass={getColorClass(stats.anglePct)}
        />
        <KPICard
          title="Berma"
          value={formatPct(stats.bermPct)}
          colorClass={getColorClass(stats.bermPct)}
        />
      </div>

      {/* Visual bars */}
      <div className="space-y-3">
        {([
          ['Cumplimiento Global', stats.globalPct],
          ['Altura', stats.heightPct],
          ['Ángulo', stats.anglePct],
          ['Berma', stats.bermPct],
        ] as const).map(([label, pct]) => (
          <div key={label} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-gray-600">{label}</span>
              <span className={`font-semibold ${getColorClass(pct)}`}>
                {formatPct(pct)}
              </span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2.5">
              <div
                className={`h-full rounded-full transition-all duration-500 ${getBarColor(pct)}`}
                style={{ width: `${Math.round(pct * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
