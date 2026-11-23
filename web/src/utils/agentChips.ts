import type { SectionRef } from './workspaceTargets';

export type AgentChip =
  | { kind: 'section'; sectionId: string; name: string; start: number; end: number }
  | { kind: 'bench'; sectionId: string; sectionName: string; designBench: number; label: string; start: number; end: number };

/** Caracteres de palabra: una mención solo cuenta si no está pegada a uno de ellos. */
const WORD_CLASS = String.raw`[\p{L}\p{N}_]`;

/** «banco N» o «Banco N», con N de 1 a 3 dígitos ASCII. */
const BENCH_PATTERN = new RegExp(String.raw`(?<!${WORD_CLASS})[Bb]anco ([0-9]{1,3})(?!${WORD_CLASS})`, 'gu');

/** Mención de nombre de sección en el texto. `section` es null si el nombre está duplicado. */
interface NameMatch {
  start: number;
  end: number;
  name: string;
  section: SectionRef | null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Busca todas las menciones posibles de nombres, incluidas las superpuestas.
 * El lookahead con captura devuelve, en cada posición, la coincidencia más larga válida.
 */
function findNameMatches(text: string, sections: readonly SectionRef[]): NameMatch[] {
  const counts = new Map<string, number>();
  const firstByName = new Map<string, SectionRef>();
  for (const section of sections) {
    if (section.name.length === 0) continue;
    counts.set(section.name, (counts.get(section.name) ?? 0) + 1);
    if (!firstByName.has(section.name)) firstByName.set(section.name, section);
  }
  const names = [...counts.keys()].sort((a, b) => b.length - a.length);
  if (names.length === 0) return [];

  const alternatives = names.map(escapeRegExp).join('|');
  const pattern = new RegExp(String.raw`(?=(?<!${WORD_CLASS})(${alternatives})(?!${WORD_CLASS}))`, 'gu');
  const matches: NameMatch[] = [];
  for (const match of text.matchAll(pattern)) {
    const name = match[1];
    const start = match.index;
    const count = counts.get(name) ?? 0;
    const section = count === 1 ? (firstByName.get(name) ?? null) : null;
    matches.push({ start, end: start + name.length, name, section });
  }
  return matches;
}

function overlapsTaken(taken: Uint8Array, start: number, end: number): boolean {
  for (let index = start; index < end; index += 1) {
    if (taken[index] === 1) return true;
  }
  return false;
}

/** Prefiere las coincidencias más largas y no deja solapes. Marca las posiciones ocupadas en `taken`. */
function selectNameMatches(candidates: readonly NameMatch[], taken: Uint8Array): NameMatch[] {
  const ordered = [...candidates].sort((a, b) => (b.end - b.start) - (a.end - a.start) || a.start - b.start);
  const selected: NameMatch[] = [];
  for (const candidate of ordered) {
    if (overlapsTaken(taken, candidate.start, candidate.end)) continue;
    taken.fill(1, candidate.start, candidate.end);
    selected.push(candidate);
  }
  return selected.sort((a, b) => a.start - b.start);
}

/**
 * Sección de un banco: la mención de nombre anterior más cercana.
 * Si esa mención está duplicada no hay sección; no se usa el contexto para no atribuir mal el banco.
 */
function resolveBenchSection(
  start: number,
  mentions: readonly NameMatch[],
  sections: readonly SectionRef[],
  contextSectionId: string | null | undefined,
): SectionRef | null {
  let nearest: NameMatch | null = null;
  for (const mention of mentions) {
    if (mention.start < start) nearest = mention;
  }
  if (nearest) return nearest.section;
  if (!contextSectionId) return null;
  return sections.find((section) => section.id === contextSectionId) ?? null;
}

/**
 * Encuentra chips en el TEXTO PLANO de un segmento Markdown (el llamador ya excluye código y enlaces).
 * - Sección: nombre exacto de `sections` como palabra completa: no hay chip para «S-3» dentro de «S-37».
 *   Ante nombres duplicados, no hay chip. Ganan las coincidencias más largas y no se solapan.
 * - Banco: «banco N» / «Banco N» (N de 1 a 3 dígitos ASCII `[0-9]`, regex sin \d). La sección es la mención
 *   anterior más cercana en el mismo texto; si no hay, `contextSectionId`; si tampoco, no hay chip.
 *   `label` es el texto original («Banco 2»).
 * Devuelve los chips ordenados por `start`, sin solapes.
 */
export function findAgentChips(text: string, sections: readonly SectionRef[], contextSectionId?: string | null): AgentChip[] {
  const taken = new Uint8Array(text.length);
  const mentions = selectNameMatches(findNameMatches(text, sections), taken);
  const chips: AgentChip[] = [];
  for (const mention of mentions) {
    if (mention.section) {
      chips.push({ kind: 'section', sectionId: mention.section.id, name: mention.name, start: mention.start, end: mention.end });
    }
  }
  for (const match of text.matchAll(BENCH_PATTERN)) {
    const start = match.index;
    const end = start + match[0].length;
    if (overlapsTaken(taken, start, end)) continue;
    const section = resolveBenchSection(start, mentions, sections, contextSectionId);
    if (!section) continue;
    chips.push({
      kind: 'bench',
      sectionId: section.id,
      sectionName: section.name,
      designBench: Number(match[1]),
      label: match[0],
      start,
      end,
    });
  }
  return chips.sort((a, b) => a.start - b.start);
}
