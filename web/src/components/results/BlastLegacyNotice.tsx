import { useTranslation } from 'react-i18next';

export function BlastLegacyNotice({ onData }: { onData: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded border border-[var(--status-warn-text)] p-3 text-sm text-text-primary">
      <span>{t('blast.legacy_reimport')}</span>
      <button type="button" className="min-h-10 underline" onClick={onData}>{t('blast.go_data')}</button>
    </div>
  );
}
