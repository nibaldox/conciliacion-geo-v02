import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSettings, useUpdateSettings } from '../../api/hooks';

/**
 * Defaults for the per-session blast tunables. Mirror `core.config.BlastDefaults`
 * on the backend and the inline `BLAST_DEFAULTS` that previously lived in
 * BlastCorrelation.tsx — keep the three in sync.
 */
const BLAST_DEFAULTS = { rock_density_tm3: 2.7, height_fallback_m: 15.0 };

/**
 * Hook that owns the local blast-settings state for the density control
 * panel: global rock density (ρ, ton/m³), global height fallback (m), and a
 * sparse per-sector override map.
 *
 * Behaviour (kept identical to the previous in-component implementation):
 *   - The three values are initialised from ``BLAST_DEFAULTS`` and re-synced
 *     whenever the ``useSettings`` query data changes (e.g. after a PUT or an
 *     external update). Stored ``sector_density`` values are merged into local
 *     state without dropping any sector the user is actively editing.
 *   - ``invalid`` is true when any value is non-finite or non-positive, OR
 *     when any staged sector override is non-finite / non-positive.
 *   - ``saveSettings`` PUTs only the ``blast`` block (no process/tolerances)
 *     and invalidates the ``['blast-correlation']`` and
 *     ``['blast-damage-model']`` queries so the table + OLS fit refetch with
 *     the new ρ. The PUT router merges the block into stored settings
 *     server-side; ``sector_density`` is sent wholesale because the router
 *     overwrites the stored map on apply.
 *
 * The hook is intentionally UI-free — it owns state + side-effects only and
 * is consumed by the density/height control panel.
 */
export function useBlastSettings() {
  const qc = useQueryClient();
  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();

  const [density, setDensity] = useState<number>(BLAST_DEFAULTS.rock_density_tm3);
  const [height, setHeight] = useState<number>(BLAST_DEFAULTS.height_fallback_m);
  // Per-sector ρ overrides. Local edits are staged here and committed via
  // ``saveSettings`` alongside the global density / height. ``sectorDensity``
  // is a sparse map: a sector present in the map overrides the global ρ for
  // that sector; absent sectors fall back to the global ``rock_density_tm3``.
  const [sectorDensity, setSectorDensity] = useState<Record<string, number>>({});

  // Resync local state whenever the settings query data changes.
  useEffect(() => {
    const b = settings?.blast;
    if (b) {
      setDensity(Number(b.rock_density_tm3 ?? BLAST_DEFAULTS.rock_density_tm3));
      setHeight(Number(b.height_fallback_m ?? BLAST_DEFAULTS.height_fallback_m));
      // Merge stored sector densities into local state without dropping any
      // sector the user is actively editing. Stored values win on reload.
      const stored = b.sector_density ?? {};
      setSectorDensity((prev) => {
        const merged: Record<string, number> = {};
        for (const sec of Object.keys({ ...prev, ...stored })) {
          const sv = Number(stored[sec]);
          merged[sec] = Number.isFinite(sv) ? sv : Number(prev[sec]);
        }
        return merged;
      });
    }
  }, [settings]);

  const invalid =
    !Number.isFinite(density) ||
    !Number.isFinite(height) ||
    density <= 0 ||
    height <= 0 ||
    // Every sector override must be a positive finite number when present.
    Object.values(sectorDensity).some(
      (v) => !Number.isFinite(v) || v <= 0,
    );

  const saveSettings = () => {
    if (invalid) return;
    // Send only the blast block — the PUT router merges it into stored
    // settings without touching process/tolerances (exclude_unset merge).
    // ``sector_density`` is sent in full (the router overwrites the stored
    // map wholesale, which is the intended apply semantics).
    updateSettings.mutate({
      blast: {
        rock_density_tm3: density,
        height_fallback_m: height,
        sector_density: { ...sectorDensity },
      },
    });
    // Refetch the correlation table + damage model so pf_g_per_ton and the
    // OLS fit recompute with the new per-sector ρ.
    qc.invalidateQueries({ queryKey: ['blast-correlation'] });
    qc.invalidateQueries({ queryKey: ['blast-damage-model'] });
  };

  return {
    density,
    setDensity,
    height,
    setHeight,
    sectorDensity,
    setSectorDensity,
    invalid,
    isPending: updateSettings.isPending,
    isError: updateSettings.isError,
    saveSettings,
  };
}