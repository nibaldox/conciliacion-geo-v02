import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { getSessionId } from '../../api/client';
import type { RecentSessionsResponse } from '../../api/sessions';
import { openSession } from './openSession';
import { Button } from '../ui/Button';

interface Props {
  data: RecentSessionsResponse | undefined;
  error: boolean;
  onClose: () => void;
}

export function RecentSessionsDialog({ data, error, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  useEffect(() => { ref.current?.showModal(); }, []);
  const formatDate = (date: string) => new Intl.DateTimeFormat(navigator.language, {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(date));
  return (
    <dialog ref={ref} onCancel={(event) => { event.preventDefault(); onClose(); }} aria-labelledby="recent-sessions-title" className="m-auto w-[min(95vw,48rem)] max-h-[85vh] overflow-y-auto rounded-xl border border-border bg-surface p-6 text-text-primary shadow-2xl backdrop:bg-black/50">
      <div className="flex items-center justify-between gap-4">
        <h2 id="recent-sessions-title" className="text-lg font-semibold">{t('recentSessions.title')}</h2>
        <Button variant="ghost" onClick={onClose} aria-label={t('shortcuts.close')}>×</Button>
      </div>
      {error && <p role="alert">{t('recentSessions.error')}</p>}
      {!error && data?.sessions.length === 0 && <p>{t('recentSessions.empty')}</p>}
      <ul className="my-4 space-y-3">
        {data?.sessions.map((session) => <li key={session.session_id} className="rounded-lg border border-border p-3">
          <div className="flex items-center justify-between gap-3">
            <strong>{formatDate(session.last_used_at)}</strong>
            {session.session_id === getSessionId() ? <span className="ui-chip">{t('recentSessions.current')}</span> : <Button variant="secondary" size="sm" onClick={() => openSession(session.session_id, queryClient)}>{t('recentSessions.open')}</Button>}
          </div>
          <p>{session.design_filename ?? '—'} / {session.topo_filename ?? '—'}</p>
          <p>{t('recentSessions.sections', { count: session.n_sections })} · {t('recentSessions.results', { count: session.n_results })}</p>
          <p className="text-xs text-text-muted">{t('recentSessions.expires', { date: formatDate(session.expires_at) })}</p>
        </li>)}
      </ul>
      {data && <p className="text-xs text-text-muted">{t('recentSessions.retention', { days: data.ttl_days })}</p>}
    </dialog>
  );
}
