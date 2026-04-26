import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';

export function SectionSelector() {
  const { data: sections, isLoading } = useSections();
  const { selectedSection, setSelectedSection } = useSession();

  return (
    <div className="flex items-center gap-3">
      <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
        Sección:
      </label>
      <select
        value={selectedSection ?? ''}
        onChange={(e) => setSelectedSection(e.target.value || null)}
        disabled={isLoading}
        className="flex-1 min-w-[200px] px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none disabled:bg-gray-50 disabled:text-gray-400"
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
