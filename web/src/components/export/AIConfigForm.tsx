import { useTranslation } from 'react-i18next';
import { useMemo, type Dispatch } from 'react';
import { Button } from '../ui/Button';
import type { ComparisonResult } from '../../api/types';
import {
  buildFilterOptions,
  type AIConfigAction,
  type AIConfigState,
  type StreamMode,
} from './useAIConfig';

const FIELD_CLASS =
  'w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-text-primary outline-none focus:border-accent';
const LABEL_CLASS = 'mb-1 block text-xs text-text-muted';

interface FieldsetProps {
  summary: string;
  open: boolean;
  onToggle: () => void;
  testId: string;
  badge?: number;
  children: React.ReactNode;
}

function CollapsibleFieldset({
  summary,
  open,
  onToggle,
  testId,
  badge,
  children,
}: FieldsetProps) {
  return (
    <div data-testid={testId} className="flex flex-col gap-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="inline-flex items-center gap-1.5 self-start text-xs font-medium text-text-secondary hover:text-text-primary"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 12 12"
          className={`h-3 w-3 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M4.5 2.5 8 6l-3.5 3.5" />
        </svg>
        <span>{summary}</span>
        {badge !== undefined && badge > 0 && (
          <span className="ui-chip !px-1.5 !py-0 tabular-nums" data-tone="accent">{badge}</span>
        )}
      </button>
      {open && <div className="flex flex-col gap-3 pl-4">{children}</div>}
    </div>
  );
}

function CheckboxGroup<T extends string | number>({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: T[];
  selected: T[];
  onToggle: (value: T) => void;
}) {
  if (options.length === 0) return null;
  return (
    <div>
      <div className={LABEL_CLASS}>{label}</div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {options.map((option) => (
          <label key={String(option)} className="flex items-center gap-1.5 text-xs text-text-secondary">
            <input
              type="checkbox"
              checked={selected.includes(option)}
              onChange={() => onToggle(option)}
            />
            {option}
          </label>
        ))}
      </div>
    </div>
  );
}

interface AIConfigFormProps {
  state: AIConfigState;
  dispatch: Dispatch<AIConfigAction>;
  providers: string[] | undefined;
  results: ComparisonResult[] | undefined;
  filters: {
    sector: string[];
    section: string[];
    bench: number[];
  };
  onToggleFilter: (
    key: 'sector' | 'section' | 'bench',
    value: string | number,
  ) => void;
  generating: boolean;
  formDisabled: boolean;
  onGenerate: () => void;
}

export function AIConfigForm({
  state,
  dispatch,
  providers,
  results,
  filters,
  onToggleFilter,
  generating,
  formDisabled,
  onGenerate,
}: AIConfigFormProps) {
  const { t } = useTranslation();

  const filterOptions = useMemo(
    () => buildFilterOptions(results),
    [results],
  );

  const hasResults = !!results && results.length > 0;
  const activeFilterCount = filters.sector.length + filters.section.length + filters.bench.length;

  return (
    <div className="flex flex-col gap-3" data-testid="ai-reporter-form">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div>
          <label htmlFor="ai-provider" className={LABEL_CLASS}>
            {t('ai_reporter.form.provider_label')}
          </label>
          <select
            id="ai-provider"
            value={state.provider}
            onChange={(e) =>
              dispatch({ type: 'SET_PROVIDER', value: e.target.value })
            }
            disabled={!providers?.length}
            className={FIELD_CLASS}
          >
            {!providers?.length && (
              <option value="">{t('ai_reporter.health.pending')}</option>
            )}
            {(providers ?? []).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="ai-model" className={LABEL_CLASS}>
            {t('ai_reporter.form.model_label')}
          </label>
          <input
            id="ai-model"
            type="text"
            value={state.model}
            onChange={(e) => dispatch({ type: 'SET_MODEL', value: e.target.value })}
            placeholder="model-name"
            className={`${FIELD_CLASS} font-mono`}
          />
        </div>

        <div className="md:col-span-2 xl:col-span-2">
          <label htmlFor="ai-notes" className={LABEL_CLASS}>
            {t('ai_reporter.form.notes_label')}
          </label>
          <textarea
            id="ai-notes"
            value={state.notes}
            onChange={(e) => dispatch({ type: 'SET_NOTES', value: e.target.value })}
            placeholder={t('ai_reporter.form.notes_placeholder')}
            rows={2}
            className={`${FIELD_CLASS} resize-y`}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <CollapsibleFieldset
          summary={t('ai_reporter.advanced.toggle')}
          open={state.showAdvanced}
          onToggle={() => dispatch({ type: 'TOGGLE_ADVANCED' })}
          testId="ai-advanced"
        >
          <div>
            <label htmlFor="ai-temperature" className={LABEL_CLASS}>
              {t('ai_reporter.advanced.temperature_label')}{' '}
              <span className="font-mono tabular-nums">({state.temperature.toFixed(2)})</span>
            </label>
            <input
              id="ai-temperature"
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={state.temperature}
              onChange={(e) =>
                dispatch({
                  type: 'SET_TEMPERATURE',
                  value: Number(e.target.value),
                })
              }
              data-testid="ai-temperature"
              className="w-full max-w-xs"
            />
          </div>
          <div className="grid max-w-xs grid-cols-2 gap-3">
            <div>
              <label htmlFor="ai-max-tokens" className={LABEL_CLASS}>
                {t('ai_reporter.advanced.max_tokens_label')}
              </label>
              <input
                id="ai-max-tokens"
                type="number"
                min={64}
                max={16384}
                step={64}
                value={state.maxTokens}
                onChange={(e) =>
                  dispatch({
                    type: 'SET_MAX_TOKENS',
                    value: Number(e.target.value),
                  })
                }
                data-testid="ai-max-tokens"
                className={`${FIELD_CLASS} tabular-nums`}
              />
            </div>
            <div>
              <label htmlFor="ai-timeout" className={LABEL_CLASS}>
                {t('ai_reporter.advanced.timeout_label')}
              </label>
              <input
                id="ai-timeout"
                type="number"
                min={5}
                max={600}
                step={5}
                value={state.timeoutS}
                onChange={(e) =>
                  dispatch({
                    type: 'SET_TIMEOUT_S',
                    value: Number(e.target.value),
                  })
                }
                data-testid="ai-timeout"
                className={`${FIELD_CLASS} tabular-nums`}
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-text-secondary">
            <input
              type="checkbox"
              checked={state.useCache}
              onChange={(e) =>
                dispatch({ type: 'SET_USE_CACHE', value: e.target.checked })
              }
              data-testid="ai-use-cache"
            />
            {t('ai_reporter.advanced.cache_label')}
          </label>
        </CollapsibleFieldset>

        {hasResults && (
          <CollapsibleFieldset
            summary={t('ai_reporter.filters.toggle')}
            open={state.showFilters}
            onToggle={() => dispatch({ type: 'TOGGLE_FILTERS' })}
            testId="ai-filters"
            badge={activeFilterCount}
          >
            <CheckboxGroup
              label={t('ai_reporter.filters.sector_label')}
              options={filterOptions.sectors}
              selected={filters.sector}
              onToggle={(value) => onToggleFilter('sector', value)}
            />
            <CheckboxGroup
              label={t('ai_reporter.filters.section_label')}
              options={filterOptions.sections}
              selected={filters.section}
              onToggle={(value) => onToggleFilter('section', value)}
            />
            <CheckboxGroup
              label={t('ai_reporter.filters.bench_label')}
              options={filterOptions.benches}
              selected={filters.bench}
              onToggle={(value) => onToggleFilter('bench', value)}
            />
          </CollapsibleFieldset>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-1" data-testid="ai-stream-toggle">
          <legend className="sr-only">{t('ai_reporter.stream.label')}</legend>
          <span aria-hidden="true" className="text-xs text-text-muted">{t('ai_reporter.stream.label')}</span>
          <label className="flex items-center gap-1.5 text-xs text-text-secondary">
            <input
              type="radio"
              name="ai-stream-mode"
              value="single"
              checked={state.streamMode === 'single'}
              onChange={() =>
                dispatch({
                  type: 'SET_STREAM_MODE',
                  value: 'single' satisfies StreamMode,
                })
              }
              data-testid="ai-stream-toggle-single"
            />
            {t('ai_reporter.stream.single')}
          </label>
          <label className="flex items-center gap-1.5 text-xs text-text-secondary">
            <input
              type="radio"
              name="ai-stream-mode"
              value="stream"
              checked={state.streamMode === 'stream'}
              onChange={() =>
                dispatch({
                  type: 'SET_STREAM_MODE',
                  value: 'stream' satisfies StreamMode,
                })
              }
              data-testid="ai-stream-toggle-stream"
            />
            {t('ai_reporter.stream.stream')}
          </label>
        </fieldset>

        <Button
          type="button"
          variant="primary"
          size="sm"
          className="w-full sm:w-auto sm:min-w-44"
          loading={generating}
          disabled={formDisabled}
          onClick={onGenerate}
        >
          {generating
            ? t('ai_reporter.form.generating')
            : t('ai_reporter.form.generate_button')}
        </Button>
      </div>
    </div>
  );
}
