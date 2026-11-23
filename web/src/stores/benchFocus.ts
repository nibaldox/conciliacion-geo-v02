import { create } from 'zustand';

export interface BenchFocusRequest {
  sectionId: string;
  designBench: number;
  nonce: number;
}

export interface BenchFocusCurrent {
  sectionId: string;
  benchNumber: number;
  designBenchNumber: number | null;
}

export interface BenchFocusState {
  request: BenchFocusRequest | null;
  current: BenchFocusCurrent | null;
  requestBench: (sectionId: string, designBench: number) => void;
  consumeRequest: (nonce: number) => void;
  publishCurrent: (current: BenchFocusCurrent | null) => void;
}

let nonce = 0;

export const useBenchFocus = create<BenchFocusState>((set) => ({
  request: null,
  current: null,
  requestBench: (sectionId, designBench) => set({ request: { sectionId, designBench, nonce: ++nonce } }),
  consumeRequest: (requestNonce) => set((state) => (
    state.request?.nonce === requestNonce ? { request: null } : state
  )),
  publishCurrent: (current) => set({ current }),
}));
