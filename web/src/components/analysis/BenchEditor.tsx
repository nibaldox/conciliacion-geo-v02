import { useState, useCallback, useMemo } from 'react';
import { useProfile, useUpdateReconciled } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { formatMeters, formatDegrees } from '../../utils/format';
import type { BenchParams } from '../../api/types';

// ─── Helper: compute derived values from crest/toe positions ──

function computeBenchValues(bench: Partial<BenchParams>): {
  bench_height: number;
  face_angle: number;
  berm_width: number;
} {
  const crestElev = bench.crest_elevation ?? 0;
  const toeElev = bench.toe_elevation ?? 0;
  const crestDist = bench.crest_distance ?? 0;
  const toeDist = bench.toe_distance ?? 0;

  const benchHeight = Math.abs(crestElev - toeElev);
  const horizontalDist = Math.abs(crestDist - toeDist);
  const faceAngle = benchHeight > 0 ? Math.atan2(benchHeight, horizontalDist) * (180 / Math.PI) : 0;
  const bermWidth = horizontalDist;

  return { bench_height: benchHeight, face_angle: faceAngle, berm_width: bermWidth };
}

// ─── Editable row ────────────────────────────────────────────

function EditableCell({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <input
      type="number"
      step="0.1"
      value={value.toFixed(2)}
      onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      className="w-20 px-2 py-1 rounded text-xs text-center outline-none"
      style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
    />
  );
}

function ReadOnlyCell({ value, format }: { value: number; format: 'meters' | 'degrees' }) {
  const display = format === 'meters' ? formatMeters(value) : formatDegrees(value);
  return (
    <span className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>{display}</span>
  );
}

// ─── Main Component ──────────────────────────────────────────

export function BenchEditor() {
  const selectedSection = useSession((s) => s.selectedSection);
  const { data: profile } = useProfile(selectedSection);
  const updateReconciled = useUpdateReconciled();

  const [localBenches, setLocalBenches] = useState<BenchParams[] | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Use local benches if edited, otherwise use profile data
  const benches = localBenches ?? profile?.benches_topo ?? null;

  // Computed values for each bench
  const computed = useMemo(() => {
    if (!benches) return [];
    return benches.map((b) => computeBenchValues(b));
  }, [benches]);

  const handleFieldChange = useCallback(
    (index: number, field: keyof BenchParams, value: number) => {
      if (!benches) return;
      const updated = [...benches];
      updated[index] = { ...updated[index], [field]: value };
      setLocalBenches(updated);
      setHasChanges(true);
    },
    [benches],
  );

  const handleRecalculate = useCallback(() => {
    if (!benches || !selectedSection) return;

    // Update each bench's computed values
    const updated = benches.map((b) => {
      const derived = computeBenchValues(b);
      return { ...b, ...derived };
    });

    setLocalBenches(updated);

    // Send to API
    updateReconciled.mutate(
      { sectionId: selectedSection, benches: updated },
      {
        onSuccess: () => {
          setHasChanges(false);
        },
      },
    );
  }, [benches, selectedSection, updateReconciled]);

  if (!selectedSection) {
    return (
      <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        Selecciona una sección para editar bancos.
      </div>
    );
  }

  if (!profile && !benches) {
    return (
      <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        Sin datos de perfil disponibles. Ejecuta el procesamiento primero.
      </div>
    );
  }

  if (!benches || benches.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        No se detectaron bancos en esta sección.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            Editor de Bancos
          </h4>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
            Sección: <span className="font-medium" style={{ color: 'var(--color-text-secondary)' }}>{profile?.section_name ?? selectedSection}</span>
            {profile?.sector && (
              <> — Sector: <span className="font-medium" style={{ color: 'var(--color-text-secondary)' }}>{profile.sector}</span></>
            )}
          </p>
        </div>
        <button
          onClick={handleRecalculate}
          disabled={!hasChanges || updateReconciled.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2"
          style={hasChanges && !updateReconciled.isPending
            ? { backgroundColor: 'var(--color-mine-blue)', color: '#fff' }
            : { backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)', cursor: 'not-allowed' }
          }
        >
          {updateReconciled.isPending ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Calculando...
            </>
          ) : (
            '🔄 Recalcular'
          )}
        </button>
      </div>

      {/* Bench table */}
      <div className="rounded-xl shadow-sm overflow-hidden" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr style={{ backgroundColor: 'var(--color-surface-muted)', borderBottom: '1px solid var(--color-border)' }}>
                <th className="px-3 py-2.5 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>Banco</th>
                <th className="px-3 py-2.5 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }} colSpan={2}>Cresta</th>
                <th className="px-3 py-2.5 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }} colSpan={2}>Toe</th>
                <th className="px-3 py-2.5 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>Altura</th>
                <th className="px-3 py-2.5 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>Ángulo</th>
                <th className="px-3 py-2.5 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>Berma</th>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                <th className="px-3 py-1" />
                <th className="px-3 py-1 text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>Dist (m)</th>
                <th className="px-3 py-1 text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>Elev (m)</th>
                <th className="px-3 py-1 text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>Dist (m)</th>
                <th className="px-3 py-1 text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>Elev (m)</th>
                <th className="px-3 py-1" />
                <th className="px-3 py-1" />
                <th className="px-3 py-1" />
              </tr>
            </thead>
            <tbody>
              {benches.map((bench, i) => {
                const derived = computed[i];
                return (
                  <tr key={bench.bench_number}>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold"
                        style={bench.is_ramp
                          ? { backgroundColor: 'var(--status-warn-bg)', color: 'var(--status-warn-text)' }
                          : { backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-secondary)' }
                        }
                      >
                        {bench.bench_number}
                      </span>
                    </td>
                    {/* Cresta editable */}
                    <td className="px-3 py-2">
                      <EditableCell
                        value={bench.crest_distance}
                        onChange={(v) => handleFieldChange(i, 'crest_distance', v)}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <EditableCell
                        value={bench.crest_elevation}
                        onChange={(v) => handleFieldChange(i, 'crest_elevation', v)}
                      />
                    </td>
                    {/* Toe editable */}
                    <td className="px-3 py-2">
                      <EditableCell
                        value={bench.toe_distance}
                        onChange={(v) => handleFieldChange(i, 'toe_distance', v)}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <EditableCell
                        value={bench.toe_elevation}
                        onChange={(v) => handleFieldChange(i, 'toe_elevation', v)}
                      />
                    </td>
                    {/* Computed (read-only) */}
                    <td className="px-3 py-2 text-center">
                      <ReadOnlyCell value={derived.bench_height} format="meters" />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <ReadOnlyCell value={derived.face_angle} format="degrees" />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <ReadOnlyCell value={derived.berm_width} format="meters" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Status feedback */}
      {updateReconciled.isError && (
        <p className="text-xs text-center" style={{ color: 'var(--color-mine-red)' }}>
          Error al actualizar. Verifica la conexión con el servidor.
        </p>
      )}
      {updateReconciled.isSuccess && !hasChanges && (
        <p className="text-xs text-center" style={{ color: 'var(--color-mine-green)' }}>
          ✓ Bancos actualizados correctamente.
        </p>
      )}
    </div>
  );
}
