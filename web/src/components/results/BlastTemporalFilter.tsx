import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { BlastTemporalFilter as TemporalMetadata } from '../../api/types';

interface Props {
  surveyDate: string;
  onApply: (date: string) => void;
  metadata?: TemporalMetadata;
}

export function BlastTemporalFilter({ surveyDate, onApply, metadata }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(surveyDate);

  return (
    <section className="border-t border-border py-3 space-y-3" aria-label={t('blast.temporal.title')}>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-48 flex-col gap-1 text-sm">
          <span>{t('blast.temporal.surveyDate')}</span>
          <input type="date" value={draft} onChange={(event) => setDraft(event.target.value)} className="min-h-10 rounded border border-border bg-surface px-3 text-text-primary" />
        </label>
        <button type="button" disabled={!draft || draft === surveyDate} onClick={() => onApply(draft)} className="min-h-10 rounded border border-border px-3 text-sm disabled:opacity-50">{t('blast.temporal.apply')}</button>
        {surveyDate && <button type="button" onClick={() => { setDraft(''); onApply(''); }} className="min-h-10 rounded border border-border px-3 text-sm">{t('blast.temporal.clear')}</button>}
      </div>
      <p className="text-sm text-text-secondary">{t('blast.temporal.scope')}</p>
      {!surveyDate && <p role="status" className="text-sm text-text-secondary">{t('blast.temporal.noCutoff')}</p>}
      {surveyDate && !metadata?.enabled && <p role="status" className="text-sm text-text-secondary">{t('blast.temporal.pending', { date: surveyDate })}</p>}
      {surveyDate && metadata?.enabled && <div role="status" className="space-y-1 text-sm text-text-secondary">
        <p>{t('blast.temporal.cutoff', { date: metadata.effective_cutoff_date, days: metadata.buffer_days })}</p>
        <p>{t('blast.temporal.counts', { included: metadata.included, excluded: metadata.excluded, missing: metadata.missing })}</p>
      </div>}
    </section>
  );
}
