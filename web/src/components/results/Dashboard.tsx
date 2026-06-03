import { useMemo } from 'react';
import { useResults, useSections } from '../../api/hooks';
import { formatPct } from '../../utils/format';

interface KPICardProps {
  title: string;
  value: string;
  valueColor: string;
  pct: number;
  icon: React.ReactNode;
}

function KPICard({ title, value, valueColor, pct, icon }: KPICardProps) {
  return (
    <div className="glass-card rounded-xl p-5 flex flex-col gap-4 relative overflow-hidden group">
      {/* Glow Effect */}
      <div 
        className="absolute -right-6 -bottom-6 w-24 h-24 rounded-full blur-2xl opacity-10 group-hover:opacity-20 transition-opacity duration-500 pointer-events-none"
        style={{ backgroundColor: valueColor }}
      />
      
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
          {title}
        </span>
        <div 
          className="w-9 h-9 rounded-lg flex items-center justify-center transition-transform group-hover:scale-105 duration-300"
          style={{ backgroundColor: `${valueColor}15`, color: valueColor }}
        >
          {icon}
        </div>
      </div>
      
      <div className="flex flex-col gap-2">
        <span className="text-3xl font-extrabold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>
          {value}
        </span>
        
        {/* Dynamic ambient progress bar */}
        <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
          <div 
            className="h-full rounded-full transition-all duration-1000 ease-out"
            style={{ width: `${Math.round(pct * 100)}%`, backgroundColor: valueColor }}
          />
        </div>
      </div>
    </div>
  );
}

function getValueColor(pct: number): string {
  if (pct > 0.8) return '#10b981'; // Vivid emerald
  if (pct > 0.6) return '#f59e0b'; // Vivid amber
  return '#ef4444'; // Vivid red
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

  // Beautiful SVG Icons
  const GlobalIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );

  const HeightIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="m8 3 4-4 4 4" />
      <path d="m8 21 4 4 4-4" />
      <line x1="12" y1="1" x2="12" y2="23" />
    </svg>
  );

  const AngleIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 21H3V3" />
      <path d="M3 21c7.5-7.5 10.5-12 18-18" />
    </svg>
  );

  const BermIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 17h6l4-10h10" />
      <path d="m18 3 4 4-4 4" />
      <line x1="22" y1="7" x2="12" y2="7" />
    </svg>
  );

  return (
    <div className="space-y-6">
      {/* Summary text */}
      <div className="flex items-center justify-between border-b pb-3 shrink-0" style={{ borderColor: 'var(--color-border)' }}>
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Resumen General de Conciliación
        </p>
        <span className="text-xs px-2.5 py-1 rounded-full font-semibold" style={{ backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-secondary)' }}>
          {stats.total} Bancos / {stats.nSections} Secciones
        </span>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KPICard
          title="Cumplimiento Global"
          value={formatPct(stats.globalPct)}
          valueColor={getValueColor(stats.globalPct)}
          pct={stats.globalPct}
          icon={GlobalIcon}
        />
        <KPICard
          title="Altura de Banco"
          value={formatPct(stats.heightPct)}
          valueColor={getValueColor(stats.heightPct)}
          pct={stats.heightPct}
          icon={HeightIcon}
        />
        <KPICard
          title="Ángulo de Cara"
          value={formatPct(stats.anglePct)}
          valueColor={getValueColor(stats.anglePct)}
          pct={stats.anglePct}
          icon={AngleIcon}
        />
        <KPICard
          title="Ancho de Berma"
          value={formatPct(stats.bermPct)}
          valueColor={getValueColor(stats.bermPct)}
          pct={stats.bermPct}
          icon={BermIcon}
        />
      </div>

      {/* Visual bars & detail statistics */}
      <div className="glass-panel rounded-xl p-5 space-y-4">
        <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--color-text-secondary)' }}>
          Desglose y Comparativa Geotécnica
        </p>
        <div className="space-y-4">
          {([
            ['Cumplimiento Global', stats.globalPct, GlobalIcon],
            ['Altura de Banco', stats.heightPct, HeightIcon],
            ['Ángulo de Cara', stats.anglePct, AngleIcon],
            ['Ancho de Berma', stats.bermPct, BermIcon],
          ] as const).map(([label, pct, icon]) => (
            <div key={label} className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <div className="flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
                  <span className="w-4 h-4 opacity-70">{icon}</span>
                  <span className="font-medium">{label}</span>
                </div>
                <span className="font-bold" style={{ color: getValueColor(pct) }}>
                  {formatPct(pct)}
                </span>
              </div>
              <div className="w-full rounded-full h-2 relative overflow-hidden" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
                {/* Ambient glow behind progress bar */}
                <div 
                  className="absolute h-full rounded-full blur-[1px] opacity-40 transition-all duration-1000"
                  style={{ width: `${Math.round(pct * 100)}%`, backgroundColor: getValueColor(pct) }}
                />
                <div
                  className="absolute h-full rounded-full transition-all duration-1000 ease-out"
                  style={{ width: `${Math.round(pct * 100)}%`, backgroundColor: getValueColor(pct) }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
