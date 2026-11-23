import { create } from 'zustand';

export type WorkspaceMode = 'protagonist' | 'copilot';
export type CopilotReason = 'meshesReady' | 'resultsRestored' | 'demo' | 'manualView';
export type ModeReason = 'initial' | CopilotReason | 'focusConversation' | 'newSession';

export interface WorkspaceModeState {
  mode: WorkspaceMode;
  lastReason: ModeReason;
  /** Pasa a copiloto (idempotente: si ya está en copiloto, solo actualiza lastReason). */
  enterCopilot: (reason: CopilotReason) => void;
  /** Única vuelta explícita al modo protagonista (botón «Enfocar conversación»). */
  focusConversation: () => void;
  /** Reinicio por cambio o borrado de sesión: fija el modo derivado del estado hidratado. */
  resetForSession: (mode: WorkspaceMode, reason: ModeReason) => void;
}

export const useWorkspaceMode = create<WorkspaceModeState>((set) => ({
  mode: 'protagonist',
  lastReason: 'initial',
  enterCopilot: (reason) => set({ mode: 'copilot', lastReason: reason }),
  focusConversation: () => set({ mode: 'protagonist', lastReason: 'focusConversation' }),
  resetForSession: (mode, reason) => set({ mode, lastReason: reason }),
}));
