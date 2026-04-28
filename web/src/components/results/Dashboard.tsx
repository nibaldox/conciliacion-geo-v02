import { useMemo } from 'react';
import { useResults, useSections } from '../../api/hooks';
import { formatPct } from '../../utils/format';

interface KPICardProps {
  title: string;
  value: string;
  valueColor: string;
}

function KPICard({ title, value, valueColor }: KPICardProps) {
  return (
    <div className="rounded-xl shadow-sm p-5 flex flex-col items-center gap-1" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
      <span className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--color-text-muted)' }}>
        {title}
      </span>
      <span className="text-3xl font-bold" style={{ color: valueColor }}>{value}</span>
    </div>
  );
}

function getValueColor(pct: number): string {
  if (pct > 0.8) return 'var(--color-mine-green)';
  if (pct > 0.6) return 'var(--color-mine-yellow)';
  return 'var(--color-mine-red)';
}

function getBarColor(pct: number): string {
  if (pct > 0.8) return 'var(--color-mine-green)';
  if (pct > 0.6) return 'var(--color-mine-yellow)';
  return 'var(--color-mine-red)';
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
      <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        Sin resultados para mostrar. Ejecuta el procesamiento primero.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary text */}
      <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
        <span className="font-semibold" style={{ color: 'var(--color-text-secondary)' }}>{stats.total}</span> resultados
        de <span className="font-semibold" style={{ color: 'var(--color-text-secondary)' }}>{stats.nSections}</span> secciones
      </p>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard
          title="Cumplimiento Global"
          value={formatPct(stats.globalPct)}
          valueColor={getValueColor(stats.globalPct)}
        />
        <KPICard
          title="Altura"
          value={formatPct(stats.heightPct)}
          valueColor={getValueColor(stats.heightPct)}
        />
        <KPICard
          title="Ángulo"
          value={formatPct(stats.anglePct)}
          valueColor={getValueColor(stats.anglePct)}
        />
        <KPICard
          title="Berma"
          value={formatPct(stats.bermPct)}
          valueColor={getValueColor(stats.bermPct)}
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
              <span style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
              <span className="font-semibold" style={{ color: getValueColor(pct) }}>
                {formatPct(pct)}
              </span>
            </div>
            <div className="w-full rounded-full h-2.5" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.round(pct * 100)}%`, backgroundColor: getBarColor(pct) }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
