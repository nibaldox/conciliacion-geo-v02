import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ProcessButton } from './ProcessButton';
import { ProcessProgress } from './ProcessProgress';
import { Tooltip } from '../ui/Tooltip';
import { Button } from '../ui/Button';
import { useSession } from '../../stores/session';
import { useProcessStatus, useSettings, useUpdateSettings } from '../../api/hooks';
import { DEFAULT_SETTINGS } from '../../utils/constants';
import type { ProcessSettings } from '../../api/types';

export function Step3Content() {
  const { prevStep, nextStep } = useSession();
  const { data: status } = useProcessStatus();
  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();
  const { t } = useTranslation();

  const isComplete = status?.status === 'complete';
  const isProcessing = status?.status === 'processing';

  const currentProcess = settings?.process ?? DEFAULT_SETTINGS;

  const [localSettings, setLocalSettings] = useState<ProcessSettings>({
    resolution: currentProcess.resolution,
    face_threshold: currentProcess.face_threshold,
    berm_threshold: currentProcess.berm_threshold,
  });

  const handleSettingChange = <K extends keyof ProcessSettings>(
    key: K,
    value: number,
  ) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveSettings = () => {
    if (!settings) return;
    updateSettings.mutate({
      process: localSettings,
      tolerances: settings.tolerances,
    });
  };

  /** Reusable label-with-?(tooltip) row. */
  const LabeledField = ({
    label,
    tooltipKey,
    children,
  }: {
    label: string;
    tooltipKey: string;
    children: React.ReactNode;
  }) => (
    <div>
      <div className="flex items-center gap-1.5 mb-1">
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          {label}
        </label>
        <Tooltip content={t(tooltipKey)} side="right">
          <span aria-label={t(tooltipKey)} className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full text-[10px] font-bold cursor-help" style={{ backgroundColor: 'var(--color-surface-muted)', color: 'var(--color-text-muted)' }}>?</span>
        </Tooltip>
      </div>
      {children}
    </div>
  );

  return (
    <div className="flex flex-col md:flex-row gap-4 md:gap-6 h-full min-h-0">
      {/* Left column — Process controls */}
      <div className="flex-1 flex flex-col items-center justify-center gap-4 md:gap-6 shrink-0">
        <div className="text-center">
          <h3 className="text-xl font-bold mb-1" style={{ color: 'var(--color-text-primary)' }}>
            {t('step3.title')}
          </h3>
          <p className="text-sm max-w-md" style={{ color: 'var(--color-text-muted)' }}>
            {t('step3.subtitle')}
          </p>
        </div>

        <ProcessButton />
        <ProcessProgress />

        {/* Navigation */}
        <div className="flex items-center gap-4 mt-2">
          <Button variant="secondary" onClick={prevStep} disabled={isProcessing}>
            {t('step3.prev')}
          </Button>
          <Button onClick={nextStep} disabled={!isComplete}>
            {t('step3.next')}
          </Button>
        </div>
      </div>

      {/* Right column — Settings panel */}
      <div className="w-full md:w-80 rounded-xl shadow-sm p-4 md:p-5 self-start shrink-0 overflow-auto max-h-full" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <h4 className="font-semibold mb-4 text-sm" style={{ color: 'var(--color-text-primary)' }}>
          {t('step3.settings_title')}
        </h4>

        <div className="space-y-4">
          <LabeledField label={t('step3.params_resolution')} tooltipKey="tooltip.simplify_epsilon">
            <input
              type="number"
              step={0.1}
              min={0.1}
              value={localSettings.resolution}
              onChange={(e) => handleSettingChange('resolution', parseFloat(e.target.value) || 0.5)}
              disabled={isProcessing}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </LabeledField>

          <LabeledField label={t('step3.params_face')} tooltipKey="tooltip.face_threshold">
            <input
              type="number"
              step={1}
              min={1}
              value={localSettings.face_threshold}
              onChange={(e) => handleSettingChange('face_threshold', parseFloat(e.target.value) || 40)}
              disabled={isProcessing}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </LabeledField>

          <LabeledField label={t('step3.params_berm')} tooltipKey="tooltip.berm_threshold">
            <input
              type="number"
              step={1}
              min={1}
              value={localSettings.berm_threshold}
              onChange={(e) => handleSettingChange('berm_threshold', parseFloat(e.target.value) || 20)}
              disabled={isProcessing}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            />
          </LabeledField>
        </div>

        <Button
          onClick={handleSaveSettings}
          disabled={isProcessing || updateSettings.isPending}
          loading={updateSettings.isPending}
          fullWidth
          className="mt-4"
        >
          {updateSettings.isPending ? t('common.loading') : t('step3.save')}
        </Button>
      </div>
    </div>
  );
}
