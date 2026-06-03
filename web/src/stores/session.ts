import { create } from 'zustand';

interface SessionState {
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

  // Actions
  setStep: (step: number) => void;
  nextStep: () => void;
  prevStep: () => void;
  setSelectedSection: (id: string | null) => void;
  setDesignMeshId: (id: string | null) => void;
  setTopoMeshId: (id: string | null) => void;
  setFilters: (filters: Partial<SessionState['filters']>) => void;
  resetFilters: () => void;
  reset: () => void;
}

const initialState = {
  currentStep: 1,
  selectedSection: null,
  designMeshId: null,
  topoMeshId: null,
  filters: { sector: [], section: [], level: [] },
};

export const useSession = create<SessionState>((set) => ({
  ...initialState,

  setStep: (step) => set({ currentStep: step }),
  nextStep: () => set((s) => ({ currentStep: Math.min(s.currentStep + 1, 4) })),
  prevStep: () => set((s) => ({ currentStep: Math.max(s.currentStep - 1, 1) })),
  setSelectedSection: (id) => set({ selectedSection: id }),
  setDesignMeshId: (id) => set({ designMeshId: id }),
  setTopoMeshId: (id) => set({ topoMeshId: id }),
  setFilters: (filters) => set((s) => ({ filters: { ...s.filters, ...filters } })),
  resetFilters: () => set({ filters: { sector: [], section: [], level: [] } }),
  reset: () => set(initialState),
}));
