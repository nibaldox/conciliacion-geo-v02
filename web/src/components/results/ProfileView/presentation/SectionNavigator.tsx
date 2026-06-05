/**
 * SectionNavigator — prev/next arrow buttons for cross-section
 * navigation.
 *
 * Used inside the SectionHeader (compact icon buttons) and as
 * floating overlay buttons on the chart for one-click navigation.
 *
 * Logic: reads the section list from useSections and the current
 * selection from useSession. The previous/next section is computed
 * by index in the sections array. If there's no prev/next (first
 * or last section), the corresponding button is disabled.
 *
 * Visual: chevron icons (◀ ▶), tooltip shows the next section's
 * name. Click → setSelectedSection(next.id).
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../../../stores/session';
import { useSectionsQuery } from '../infrastructure/apiAdapter';

export interface SectionNavigatorProps {
  /** When true, render as compact icon buttons (used in the
   *  SectionHeader). When false, render as large floating overlay
   *  buttons (used over the chart). */
  readonly variant?: 'compact' | 'overlay';
  /** Show the next/prev section's name as text (only works in
   *  overlay variant — compact just shows the icon). */
  readonly showLabels?: boolean;
}

export function SectionNavigator({ variant = 'compact', showLabels = false }: SectionNavigatorProps) {
  const { t } = useTranslation();
  const { data: sections } = useSectionsQuery();
  const { selectedSection, setSelectedSection } = useSession();

  const { prev, next } = useMemo(() => {
    if (!selectedSection || sections.length === 0) return { prev: null, next: null };
    const idx = sections.findIndex((s) => s.id === selectedSection);
    if (idx === -1) return { prev: null, next: null };
    return {
      prev: idx > 0 ? sections[idx - 1]! : null,
      next: idx < sections.length - 1 ? sections[idx + 1]! : null,
    };
  }, [sections, selectedSection]);

  if (variant === 'overlay') {
    return (
      <>
        <OverlayButton
          direction="prev"
          label={prev ? prev.name : null}
          showLabels={showLabels}
          disabled={!prev}
          onClick={() => prev && setSelectedSection(prev.id)}
          t={t}
        />
        <OverlayButton
          direction="next"
          label={next ? next.name : null}
          showLabels={showLabels}
          disabled={!next}
          onClick={() => next && setSelectedSection(next.id)}
          t={t}
        />
      </>
    );
  }

  return (
    <div data-slot="section-navigator" className="inline-flex items-center gap-1">
      <CompactButton
        direction="prev"
        label={prev ? prev.name : null}
        disabled={!prev}
        onClick={() => prev && setSelectedSection(prev.id)}
        t={t}
      />
      <CompactButton
        direction="next"
        label={next ? next.name : null}
        disabled={!next}
        onClick={() => next && setSelectedSection(next.id)}
        t={t}
      />
    </div>
  );
}

// ─── Variants ───────────────────────────────────────────────

function CompactButton({
  direction,
  label,
  disabled,
  onClick,
  t,
}: {
  direction: 'prev' | 'next';
  label: string | null;
  disabled: boolean;
  onClick: () => void;
  t: ReturnType<typeof useTranslation>['t'];
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={
        disabled
          ? t('profileView.nav.none', { defaultValue: 'Sin más secciones' })
          : t('profileView.nav.to', {
              defaultValue: '{{name}} ({{dir}})',
              name: label,
              dir: direction === 'prev' ? '←' : '→',
            })
      }
      aria-label={
        direction === 'prev'
          ? t('profileView.nav.prev', { defaultValue: 'Sección anterior' })
          : t('profileView.nav.next', { defaultValue: 'Siguiente sección' })
      }
      data-direction={direction}
      data-testid={`nav-${direction}`}
      className={[
        'inline-flex items-center justify-center w-7 h-7 rounded-md text-sm font-semibold',
        'transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
        disabled
          ? 'opacity-30 cursor-not-allowed'
          : 'cursor-pointer hover:opacity-80 hover:scale-105',
      ].join(' ')}
      style={{
        color: 'var(--color-text-primary)',
        backgroundColor: 'var(--color-surface-muted)',
        border: '1px solid var(--color-border)',
      }}
    >
      {direction === 'prev' ? '‹' : '›'}
    </button>
  );
}

function OverlayButton({
  direction,
  label,
  showLabels,
  disabled,
  onClick,
  t,
}: {
  direction: 'prev' | 'next';
  label: string | null;
  showLabels: boolean;
  disabled: boolean;
  onClick: () => void;
  t: ReturnType<typeof useTranslation>['t'];
}) {
  const isLeft = direction === 'prev';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={
        disabled
          ? t('profileView.nav.none', { defaultValue: 'Sin más secciones' })
          : t('profileView.nav.to', {
              defaultValue: '{{name}}',
              name: label,
            })
      }
      aria-label={
        direction === 'prev'
          ? t('profileView.nav.prev', { defaultValue: 'Sección anterior' })
          : t('profileView.nav.next', { defaultValue: 'Siguiente sección' })
      }
      data-direction={direction}
      data-testid={`overlay-nav-${direction}`}
      className={[
        'absolute top-1/2 -translate-y-1/2 z-10',
        'flex items-center gap-2',
        isLeft ? 'left-2' : 'right-2',
        'px-3 py-2 rounded-full shadow-md',
        'transition-all duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1',
        disabled
          ? 'opacity-30 cursor-not-allowed'
          : 'cursor-pointer hover:opacity-90 hover:scale-105',
      ].join(' ')}
      style={{
        backgroundColor: 'var(--color-surface)',
        color: 'var(--color-text-primary)',
        border: '1px solid var(--color-border)',
      }}
    >
      {isLeft && <span aria-hidden="true">‹</span>}
      {showLabels && label && (
        <span className="text-xs font-medium hidden md:inline">{label}</span>
      )}
      {!isLeft && <span aria-hidden="true">›</span>}
    </button>
  );
}
