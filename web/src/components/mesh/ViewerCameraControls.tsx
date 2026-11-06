import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { CameraOption, CameraToggles, CameraView } from './viewerCameraState';

const icons = {
  reset: <><path d="M3 11 12 3l9 8M5 10v10h14V10M9 20v-6h6v6" /></>,
  plan: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M12 17V7m-3 3 3-3 3 3" /></>,
  north: <><path d="M12 3v18M7 8l5-5 5 5M6 20h12" /></>,
  east: <><path d="M3 12h18m-5-5 5 5-5 5M4 6v12" /></>,
  grid: <><rect x="3" y="3" width="18" height="18" /><path d="M9 3v18M15 3v18M3 9h18M3 15h18" /></>,
  pivot: <><circle cx="12" cy="12" r="3" /><path d="M12 3v5m0 8v5M3 12h5m8 0h5" /></>,
  setPivot: <><circle cx="12" cy="12" r="7" /><path d="M12 2v6m0 8v6M2 12h6m8 0h6" /><circle cx="12" cy="12" r="1" /></>,
};

export function ViewerCameraControls({ toggles, onView, onToggle, pickingPivot = false, onPickPivot = () => {} }: {
  toggles: CameraToggles;
  onView: (view: CameraView) => void;
  onToggle: (option: CameraOption) => void;
  pickingPivot?: boolean;
  onPickPivot?: (active: boolean) => void;
}) {
  const { t } = useTranslation();
  useEffect(() => {
    if (!pickingPivot) return;
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') onPickPivot(false); };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [pickingPivot, onPickPivot]);
  const buttonClass = 'flex h-9 w-9 shrink-0 items-center justify-center rounded hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent';
  const tools = [
    ...(['reset', 'plan', 'north', 'east'] as const).map((key) => ({ key, click: () => onView(key), pressed: undefined as boolean | undefined })),
    ...(['grid', 'pivot'] as const).map((key) => ({ key, click: () => onToggle(key), pressed: toggles[key] })),
    { key: 'setPivot' as const, click: () => onPickPivot(!pickingPivot), pressed: pickingPivot },
  ];
  return <div data-testid="camera-controls" role="group" aria-label={t('viewer.camera.title')} className="absolute left-2 top-2 z-20 flex max-w-[calc(100%-1rem)] flex-wrap gap-1 rounded border border-border bg-surface-raised p-1 text-text-primary shadow-lg">
    {tools.map(({ key, click, pressed }) => <button key={key} type="button" className={`${buttonClass} ${pressed ? 'bg-surface-muted text-accent-bright' : ''}`} aria-label={t(`viewer.camera.${key}`)} title={t(`viewer.camera.${key}`)} aria-pressed={pressed} onClick={click}><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{icons[key]}</svg></button>)}
  </div>;
}
