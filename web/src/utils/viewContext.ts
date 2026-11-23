import type { SectionRef } from './workspaceTargets';

export type WorkspaceViewId = '3d' | 'profiles' | 'dashboard' | 'blast' | 'export-ai';

export interface ViewContextInput {
  view: WorkspaceViewId;
  profilesMode: 'grid' | 'detail';
  section: SectionRef | null;              // solo si el usuario la eligió y existe en los datos actuales
  bench: { designBench: number } | null;   // banco seleccionado en el inspector (C4), si hay
}

export interface ViewContext {
  view: WorkspaceViewId;
  mode?: 'grid' | 'detail';                // solo en profiles
  sectionName?: string;                    // en profiles (detalle) y dashboard con sección elegida
  designBench?: number;                    // solo en profiles en detalle con sección
}

/** Describe la vista activa con los datos mínimos que necesita la UI para armar el contexto. */
export function describeViewContext(input: ViewContextInput): ViewContext {
  if (input.view === 'dashboard') {
    return input.section ? { view: 'dashboard', sectionName: input.section.name } : { view: 'dashboard' };
  }
  if (input.view !== 'profiles') return { view: input.view };
  if (input.profilesMode === 'grid') return { view: 'profiles', mode: 'grid' };

  const context: ViewContext = { view: 'profiles', mode: 'detail' };
  if (!input.section) return context;
  context.sectionName = input.section.name;
  if (input.bench) context.designBench = input.bench.designBench;
  return context;
}
