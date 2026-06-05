/**
 * Step3Content — the "ANÁLISIS" step (MISIÓN 03).
 *
 * Mission Control layout: a column of cards on the left (the
 * process trigger + the live progress log) and a settings panel
 * on the right with the launch button. Everything sits in a
 * Card dashed/elevated frame to feel like a "mission control
 * console".
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ProcessButton } from './ProcessButton';
import { ProcessProgress } from './ProcessProgress';
import { Tooltip } from '../ui/Tooltip';
import { Button, Card, StatusBar } from '../ui';
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

  return (
    <div className="flex flex-col md:flex-row gap-4 md:gap-6 h-full min-h-0">
      {/* Left column — Process trigger + live progress */}
      <div className="flex-1 flex flex-col gap-4 shrink-0 min-h-0">
        <Card
          variant="elevated"
          eyebrow="CONCILIATION ENGINE"
          icon="⚙"
          title={t('step3.title')}
          subtitle={t('step3.subtitle')}
          data-slot="step3-trigger"
        >
          <div className="flex flex-col items-center gap-4 py-2">
            <ProcessButton />
            <ProcessProgress />
          </div>
        </Card>

        {/* Live status feed — fake "mission control" log */}
        <StatusBar
          title="ANÁLISIS · TELEMETRÍA"
          showCursor={!isComplete}
          entries={[
            { level: 'system', text: 'Process engine initialised' },
            ...(isProcessing
              ? [
                  { level: 'scan' as const, text: `Processing section ${status?.current_section ?? '?'} of ${status?.total_sections ?? '?'}` },
                  { level: 'geo' as const, text: 'Extracting benches, computing areas…' },
                ]
              : []),
            ...(isComplete
              ? [
                  { level: 'info' as const, text: `Completed: ${status?.n_results ?? 0} results ready` },
                ]
              : []),
          ]}
        />
      </div>

      {/* Right column — Settings + nav */}
      <div className="w-full md:w-80 shrink-0 overflow-auto">
        <Card
          variant="solid"
          eyebrow="PROCESS PARAMETERS"
          icon="⚡"
          title={t('step3.settings_title')}
        >
          <div className="space-y-3">
            <LabeledField
              label={t('step3.params_resolution', { defaultValue: 'Resolución (m)' })}
              tooltipKey="tooltip.simplify_epsilon"
            >
              <input
                type="number"
                step={0.1}
                min={0.1}
                value={localSettings.resolution}
                onChange={(e) => handleSettingChange('resolution', parseFloat(e.target.value) || 0.5)}
                disabled={isProcessing}
                className="w-full px-3 py-1.5 rounded-md text-sm outline-none focus:ring-2 focus:ring-accent/30 tabular-nums"
                style={{
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  backgroundColor: 'var(--color-surface-sunken)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
            </LabeledField>

            <LabeledField
              label={t('step3.params_face', { defaultValue: 'Cara (°)' })}
              tooltipKey="tooltip.face_threshold"
            >
              <input
                type="number"
                step={1}
                min={1}
                value={localSettings.face_threshold}
                onChange={(e) => handleSettingChange('face_threshold', parseFloat(e.target.value) || 40)}
                disabled={isProcessing}
                className="w-full px-3 py-1.5 rounded-md text-sm outline-none focus:ring-2 focus:ring-accent/30 tabular-nums"
                style={{
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  backgroundColor: 'var(--color-surface-sunken)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
            </LabeledField>

            <LabeledField
              label={t('step3.params_berm', { defaultValue: 'Berma (°)' })}
              tooltipKey="tooltip.berm_threshold"
            >
              <input
                type="number"
                step={1}
                min={1}
                value={localSettings.berm_threshold}
                onChange={(e) => handleSettingChange('berm_threshold', parseFloat(e.target.value) || 20)}
                disabled={isProcessing}
                className="w-full px-3 py-1.5 rounded-md text-sm outline-none focus:ring-2 focus:ring-accent/30 tabular-nums"
                style={{
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                  backgroundColor: 'var(--color-surface-sunken)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
            </LabeledField>

            <Button
              variant="terminal"
              onClick={handleSaveSettings}
              disabled={isProcessing || updateSettings.isPending}
              loading={updateSettings.isPending}
              fullWidth
              className="mt-2"
            >
              {updateSettings.isPending ? t('common.loading') : t('step3.save')}
            </Button>
          </div>
        </Card>

        {/* Nav */}
        <div className="flex items-center gap-2 mt-3">
          <Button variant="secondary" onClick={prevStep} disabled={isProcessing} fullWidth>
            {t('step3.prev')}
          </Button>
          <Button onClick={nextStep} disabled={!isComplete} fullWidth>
            {t('step3.next')}
          </Button>
        </div>
      </div>
    </div>
  );
}

function LabeledField({
  label,
  tooltipKey,
  children,
}: {
  label: string;
  tooltipKey: string;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1">
        <label
          className="text-[10px] uppercase tracking-widest font-semibold"
          style={{
            color: 'var(--color-text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {label}
        </label>
        <Tooltip content={t(tooltipKey)} side="right">
          <span
            aria-label={t(tooltipKey)}
            className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full text-[10px] font-bold cursor-help"
            style={{
              backgroundColor: 'var(--color-surface-muted)',
              color: 'var(--color-text-muted)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            ?
          </span>
        </Tooltip>
      </div>
      {children}
    </div>
  );
}
