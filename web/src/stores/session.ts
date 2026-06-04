import { create } from 'zustand';

/** Shape of the precomputed demo payload served from /demo/precomputed.json.
 *  See scripts/generate_demo_data.py for the producer. */
export interface DemoData {
  summary: {
    n_sections: number;
    n_comparisons: number;
    n_match: number;
    compliance: Record<
      string,
      { label: string; cumple: number; fuera: number; no_cumple: number; pct: number }
    >;
  };
  vertices: {
    design: { x: number[]; y: number[]; z: number[] };
    topo: { x: number[]; y: number[]; z: number[] };
  };
  sections: Array<{
    section_name: string;
    sector: string;
    origin: number[];
    azimuth: number;
    design_profile: { distances: number[]; elevations: number[] };
    topo_profile: { distances: number[]; elevations: number[] };
    reconciled_topo: { distances: number[]; elevations: number[] };
    benches_topo: Array<{
      bench_number: number;
      crest_elevation: number;
      crest_distance: number;
      toe_elevation: number;
      toe_distance: number;
      bench_height: number;
      face_angle: number;
      berm_width: number;
      is_ramp: boolean;
    }>;
  }>;
  comparisons: Array<{
    sector: string;
    section: string;
    bench_num: number;
    type: 'MATCH' | 'MISSING' | 'EXTRA';
    level: string;
    height_design: number | null;
    height_real: number | null;
    height_dev: number | null;
    height_status: string;
    angle_design: number | null;
    angle_real: number | null;
    angle_dev: number | null;
    angle_status: string;
    berm_design: number | null;
    berm_real: number | null;
    berm_min: number | null;
    berm_status: string;
    delta_crest: number | null;
    delta_toe: number | null;
  }>;
}

interface SessionState {
  // Top-level navigation. 'landing' shows the public marketing
  // page (default for first-time visitors); 'app' shows the
  // wizard. Hash routing (#/app) lets us deep-link straight to
  // the wizard for power users.
  view: 'landing' | 'app';

  // Wizard navigation
  currentStep: number;

  // Selections
  selectedSection: string | null;
  designMeshId: string | null;
  topoMeshId: string | null;

  // Filters for results table
  filters: {
    sector: string[];
    section: string[];
    level: string[];
  };

  // ── Demo mode ───────────────────────────────────────────
  // When true, all data hooks return precomputed synthetic data
  // loaded from /demo/precomputed.json. No backend calls are made.
  demoMode: boolean;
  demoData: DemoData | null;
  demoLoading: boolean;
  demoError: string | null;

  // Actions
  setView: (view: 'landing' | 'app') => void;
  setStep: (step: number) => void;
  nextStep: () => void;
  prevStep: () => void;
  setSelectedSection: (id: string | null) => void;
  setDesignMeshId: (id: string | null) => void;
  setTopoMeshId: (id: string | null) => void;
  setFilters: (filters: Partial<SessionState['filters']>) => void;
  resetFilters: () => void;
  loadDemo: () => Promise<void>;
  exitDemo: () => void;
  reset: () => void;
}

const initialState = {
  view: 'landing' as const,
  currentStep: 1,
  selectedSection: null,
  designMeshId: null,
  topoMeshId: null,
  filters: { sector: [], section: [], level: [] },
  demoMode: false,
  demoData: null,
  demoLoading: false,
  demoError: null,
};

/** Magic IDs for demo mode — recognised by the data hooks as virtual
 *  meshes that should be served from in-memory demo data, not the API. */
export const DEMO_MESH_IDS = {
  design: '__demo_design__',
  topo: '__demo_topo__',
} as const;

export const useSession = create<SessionState>((set, get) => ({
  ...initialState,

  setView: (view) => {
    set({ view });
    // Keep the URL hash in sync so the wizard can be deep-linked
    // and the back button does the right thing.
    if (typeof window !== 'undefined') {
      const target = view === 'app' ? '#/app' : '#/';
      if (window.location.hash !== target) {
        window.history.replaceState(null, '', target);
      }
    }
  },
  setStep: (step) => set({ currentStep: step }),
  nextStep: () => set((s) => ({ currentStep: Math.min(s.currentStep + 1, 4) })),
  prevStep: () => set((s) => ({ currentStep: Math.max(s.currentStep - 1, 1) })),
  setSelectedSection: (id) => set({ selectedSection: id }),
  setDesignMeshId: (id) => set({ designMeshId: id }),
  setTopoMeshId: (id) => set({ topoMeshId: id }),
  setFilters: (filters) => set((s) => ({ filters: { ...s.filters, ...filters } })),
  resetFilters: () => set({ filters: { sector: [], section: [], level: [] } }),

  loadDemo: async () => {
    // Re-use already-loaded data so clicking twice doesn't refetch.
    const existing = get().demoData;
    if (existing) {
      set({
        demoMode: true,
        designMeshId: DEMO_MESH_IDS.design,
        topoMeshId: DEMO_MESH_IDS.topo,
        currentStep: 4,            // skip straight to results
        selectedSection: existing.sections[0]?.section_name ?? null,
        demoLoading: false,
        demoError: null,
      });
      return;
    }
    set({ demoLoading: true, demoError: null });
    try {
      // `import.meta.env.BASE_URL` is the Vite base path — works in
      // both /conciliacion-geo-v02/ (default) and / (custom domain).
      const base = import.meta.env.BASE_URL.replace(/\/$/, '');
      const res = await fetch(`${base}/demo/precomputed.json`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: DemoData = await res.json();
      set({
        demoMode: true,
        demoData: data,
        demoLoading: false,
        demoError: null,
        designMeshId: DEMO_MESH_IDS.design,
        topoMeshId: DEMO_MESH_IDS.topo,
        currentStep: 4,
        selectedSection: data.sections[0]?.section_name ?? null,
      });
    } catch (err) {
      set({
        demoLoading: false,
        demoError: err instanceof Error ? err.message : String(err),
      });
    }
  },

  exitDemo: () =>
    set({
      demoMode: false,
      demoData: null,
      demoLoading: false,
      demoError: null,
      designMeshId: null,
      topoMeshId: null,
      selectedSection: null,
      currentStep: 1,
    }),

  reset: () => set(initialState),
}));
