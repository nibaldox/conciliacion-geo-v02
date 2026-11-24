import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { getSessionId } from '../../api/client';
import { useRecentSessions } from '../../api/sessions';
import { RecentSessionsDialog } from './RecentSessionsDialog';
import { openSession } from './openSession';

export function RecentSessionsList() {
  const { t } = useTranslation();
  const query = useRecentSessions();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);

  if (!query.isSuccess || !Array.isArray(query.data?.sessions) || !query.data.sessions.length) return null;

  return (
    <section className="border-b border-border pb-3">
      <h3 className="ui-section-title">{t('recentSessions.title')}</h3>
      <ul className="mt-2 space-y-2">
        {query.data.sessions.slice(0, 5).map((session) => (
          <li key={session.session_id} className="text-xs text-text-secondary">
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 break-words">{session.design_filename ?? '—'} / {session.topo_filename ?? '—'}</span>
              {session.session_id === getSessionId()
                ? <span>{t('recentSessions.current')}</span>
                : <button type="button" onClick={() => openSession(session.session_id, queryClient)}>{t('recentSessions.open')}</button>}
            </div>
            <p className="text-text-muted">{t('recentSessions.sections', { count: session.n_sections })} · {t('recentSessions.results', { count: session.n_results })}</p>
          </li>
        ))}
      </ul>
      {query.data.sessions.length > 5 && <button type="button" onClick={() => setDialogOpen(true)}>{t('recentSessions.view_all')}</button>}
      {dialogOpen && <RecentSessionsDialog data={query.data} error={false} onClose={() => setDialogOpen(false)} />}
    </section>
  );
}
