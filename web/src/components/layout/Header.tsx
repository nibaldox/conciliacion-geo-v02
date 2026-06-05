/**
 * Header — the top bar.
 *
 * Mission Control aesthetic: dark surface, subtle bottom border,
 * monospace brand text with the orange CG badge, right-aligned
 * utility actions. The brand mark is a square with the letters
 * 'CG' in the accent color (orange) on a dark bg.
 */

import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useQueryClient } from '@tanstack/react-query';
import { LanguageToggle } from './LanguageToggle';
import { KeyboardShortcutsHelp } from '../ui/KeyboardShortcutsHelp';
import { Button } from '../ui/Button';

export function Header() {
  const { reset, demoMode } = useSession();
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  const handleNewSession = () => {
    localStorage.removeItem('session_id');
    queryClient.clear();
    reset();
    window.location.href = window.location.pathname;
  };

  return (
    <header
      data-slot="app-header"
      className="flex items-center justify-between px-3 md:px-6 py-2.5 border-b shrink-0"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
    >
      {/* Brand block — the orange "CG" badge is the visual anchor. */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleNewSession}
          className="flex items-center gap-3 rounded-md px-2 py-1 -ml-2 hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          title={t('header.go_home')}
        >
          <div
            className="flex items-center justify-center w-9 h-9 rounded-md font-bold text-sm"
            style={{
              backgroundColor: 'var(--color-accent)',
              color: '#0a0e14',
              boxShadow: '0 0 12px rgba(249, 115, 22, 0.30)',
              fontFamily: 'var(--font-mono)',
            }}
            aria-label="CG logo"
          >
            CG
          </div>
          <div className="text-left">
            <h1
              className="text-sm font-semibold uppercase tracking-wider"
              style={{
                color: 'var(--color-text-primary)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {t('app.title')}
            </h1>
            <p
              className="text-[10px] uppercase tracking-widest"
              style={{
                color: 'var(--color-text-muted)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {t('app.tagline')}
              {demoMode && <span className="ml-1">· DEMO</span>}
            </p>
          </div>
        </button>
      </div>

      {/* Right side: utility actions. The "Nueva Sesión" button is
       *  terminal-style to keep with the Mission Control aesthetic. */}
      <div className="flex items-center gap-1.5 md:gap-2">
        <div className="hidden md:block">
          <KeyboardShortcutsHelp />
        </div>
        <LanguageToggle />
        <Button
          variant="terminal"
          size="sm"
          onClick={handleNewSession}
          title={t('header.new_session')}
        >
          {t('header.new_session')}
        </Button>
        <span
          className="text-[10px] uppercase tracking-widest hidden md:inline"
          style={{
            color: 'var(--color-text-dim)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {t('header.version')} 2.0
        </span>
      </div>
    </header>
  );
}
