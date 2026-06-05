/**
 * StatusBar — the "TERMINAL DE STATUS" panel from the reference
 * design. A monospace, dark, status-feed style component.
 *
 * Usage:
 *   <StatusBar
 *     title="TERMINAL DE STATUS"
 *     entries={[
 *       { level: 'system', text: 'Ingest core initialised…' },
 *       { level: 'scan', text: 'Waiting for surface data packets…' },
 *       { level: 'geo', text: 'Local coordinate set to EPSG:4326' },
 *     ]}
 *   />
 *
 * Each entry is one line of pseudo-log output. Renders with the
 * "console" font (mono), color-coded by level. Use sparingly
 * — this is the "mission control" aesthetic, not a real terminal.
 */

import { ReactNode } from 'react';

export type StatusLevel = 'system' | 'scan' | 'geo' | 'info' | 'warn' | 'error';

export interface StatusEntry {
  readonly level: StatusLevel;
  readonly text: ReactNode;
}

const LEVEL_PREFIX: Record<StatusLevel, string> = {
  system: '[SYSTEM]',
  scan: '[SCAN]',
  geo: '[GEO]',
  info: '[INFO]',
  warn: '[WARN]',
  error: '[ERROR]',
};

const LEVEL_COLOR: Record<StatusLevel, string> = {
  system: 'var(--color-text-secondary)',
  scan: 'var(--color-mine-blue)',
  geo: 'var(--color-accent-bright)',
  info: 'var(--color-text-secondary)',
  warn: 'var(--status-warn-text)',
  error: 'var(--status-nok-text)',
};

export interface StatusBarProps {
  readonly title?: ReactNode;
  readonly entries: readonly StatusEntry[];
  /** Show a blinking cursor at the end of the last line. */
  readonly showCursor?: boolean;
  readonly className?: string;
  readonly style?: React.CSSProperties;
}

export function StatusBar({
  title = 'TERMINAL DE STATUS',
  entries,
  showCursor = true,
  className = '',
  style,
}: StatusBarProps) {
  return (
    <section
      data-slot="status-bar"
      className={`rounded-lg overflow-hidden ${className}`}
      style={{
        backgroundColor: 'var(--color-surface-sunken)',
        border: '1px solid var(--color-border)',
        fontFamily: 'var(--font-mono)',
        ...style,
      }}
    >
      {title && (
        <header
          className="px-3 py-1.5 text-[10px] uppercase tracking-widest font-semibold"
          style={{
            backgroundColor: 'var(--color-surface)',
            color: 'var(--color-text-muted)',
            borderBottom: '1px solid var(--color-border)',
          }}
        >
          {title}
        </header>
      )}
      <div
        className="p-3 text-[12px] leading-relaxed overflow-auto max-h-40"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {entries.map((e, i) => {
          const isLast = i === entries.length - 1;
          return (
            <div key={i} className="flex gap-2">
              <span
                className="shrink-0 select-none"
                style={{ color: LEVEL_COLOR[e.level] }}
              >
                {LEVEL_PREFIX[e.level]}
              </span>
              <span className="flex-1 break-words" style={{ color: LEVEL_COLOR[e.level] }}>
                {e.text}
              </span>
              {showCursor && isLast && (
                <span
                  className="inline-block w-2 h-3.5 self-end animate-pulse"
                  style={{ backgroundColor: 'var(--color-accent-bright)' }}
                  aria-hidden="true"
                />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
