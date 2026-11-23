/** Sección con identificador estable y nombre visible. */
export interface SectionRef {
  id: string;
  name: string;
}

/**
 * Coincidencia exacta y única por nombre. Devuelve null si no existe o si hay nombres duplicados.
 */
export function resolveSectionByName(name: string, sections: readonly SectionRef[]): SectionRef | null {
  let match: SectionRef | null = null;
  for (const section of sections) {
    if (section.name !== name) continue;
    if (match) return null;
    match = section;
  }
  return match;
}
