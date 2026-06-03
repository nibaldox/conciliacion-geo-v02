import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';

export function SectionSelector() {
  const { data: sections, isLoading } = useSections();
  const { selectedSection, setSelectedSection } = useSession();

  return (
    <div className="flex items-center gap-3">
      <label className="text-sm font-medium whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
        Sección:
      </label>
      <select
        value={selectedSection ?? ''}
        onChange={(e) => setSelectedSection(e.target.value || null)}
        disabled={isLoading}
        className="flex-1 min-w-[200px] px-3 py-2 rounded-lg text-sm outline-none"
        style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
      >
        <option value="">— Seleccionar sección —</option>
        {sections?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name} (Az: {s.azimuth.toFixed(1)}° — {s.sector})
          </option>
        ))}
      </select>
    </div>
  );
}
