import { useTranslation } from 'react-i18next';
import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';

export function SectionSelector() {
  const { data: sections, isLoading } = useSections();
  const selectedSection = useSession((s) => s.selectedSection);
  const setSelectedSection = useSession((s) => s.setSelectedSection);
  const { t } = useTranslation();

  return (
    <div className="flex items-center gap-3">
      <label className="text-sm font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
        {t('step4.select_section_label')}
      </label>
      <select
        value={selectedSection ?? ''}
        onChange={(e) => setSelectedSection(e.target.value || null)}
        disabled={isLoading}
        className="flex-1 min-w-[200px] px-3 py-2 rounded-lg text-sm outline-none"
        style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
      >
        <option value="">{t('step4.section_select_default')}</option>
        {sections?.map((s) => (
          <option key={s.id} value={s.id}>
            {t('step4.section_option', {
              name: s.name,
              azimuth: s.azimuth.toFixed(1),
              sector: s.sector,
            })}
          </option>
        ))}
      </select>
    </div>
  );
}
