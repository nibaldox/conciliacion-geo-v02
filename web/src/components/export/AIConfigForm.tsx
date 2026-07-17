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

interface FieldsetProps {
  summary: string;
  open: boolean;
  onToggle: () => void;
  testId: string;
  children: React.ReactNode;
}

function CollapsibleFieldset({
  summary,
  open,
  onToggle,
  testId,
  children,
}: FieldsetProps) {
  return (
    <div data-testid={testId}>
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="w-full flex items-center justify-between text-xs font-medium py-1"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        <span>{summary}</span>
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="pt-1 space-y-3">{children}</div>}
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

  return (
    <div
      className="rounded-xl shadow-sm p-5 space-y-3"
      style={{
        backgroundColor: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
      }}
      data-testid="ai-reporter-form"
    >
      <div>
        <label
          htmlFor="ai-provider"
          className="block text-xs font-medium mb-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('ai_reporter.form.provider_label')}
        </label>
        <select
          id="ai-provider"
          value={state.provider}
          onChange={(e) =>
            dispatch({ type: 'SET_PROVIDER', value: e.target.value })
          }
          disabled={!providers?.length}
          className="w-full px-3 py-2 rounded-lg text-sm outline-none"
          style={{
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-primary)',
            backgroundColor: 'var(--color-surface)',
          }}
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
        <label
          htmlFor="ai-model"
          className="block text-xs font-medium mb-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('ai_reporter.form.model_label')}
        </label>
        <input
          id="ai-model"
          type="text"
          value={state.model}
          onChange={(e) => dispatch({ type: 'SET_MODEL', value: e.target.value })}
          placeholder="model-name"
          className="w-full px-3 py-2 rounded-lg text-sm outline-none"
          style={{
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-primary)',
            backgroundColor: 'var(--color-surface)',
          }}
        />
      </div>

      <div>
        <label
          htmlFor="ai-notes"
          className="block text-xs font-medium mb-1"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {t('ai_reporter.form.notes_label')}
        </label>
        <textarea
          id="ai-notes"
          value={state.notes}
          onChange={(e) => dispatch({ type: 'SET_NOTES', value: e.target.value })}
          placeholder={t('ai_reporter.form.notes_placeholder')}
          rows={2}
          className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-y"
          style={{
            border: '1px solid var(--color-border)',
            color: 'var(--color-text-primary)',
            backgroundColor: 'var(--color-surface)',
          }}
        />
      </div>

      <CollapsibleFieldset
        summary={t('ai_reporter.advanced.toggle')}
        open={state.showAdvanced}
        onToggle={() => dispatch({ type: 'TOGGLE_ADVANCED' })}
        testId="ai-advanced"
      >
        <div>
          <label
            htmlFor="ai-temperature"
            className="block text-xs font-medium mb-1"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            {t('ai_reporter.advanced.temperature_label')} ({state.temperature.toFixed(2)})
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
            className="w-full"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label
              htmlFor="ai-max-tokens"
              className="block text-xs font-medium mb-1"
              style={{ color: 'var(--color-text-secondary)' }}
            >
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
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                backgroundColor: 'var(--color-surface)',
              }}
            />
          </div>
          <div>
            <label
              htmlFor="ai-timeout"
              className="block text-xs font-medium mb-1"
              style={{ color: 'var(--color-text-secondary)' }}
            >
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
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                backgroundColor: 'var(--color-surface)',
              }}
            />
          </div>
        </div>
        <label
          className="flex items-center gap-2 text-xs"
          style={{ color: 'var(--color-text-secondary)' }}
        >
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
        >
          {filterOptions.sectors.length > 0 && (
            <div>
              <div
                className="text-[10px] uppercase tracking-wider mb-1"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t('ai_reporter.filters.sector_label')}
              </div>
              <div className="flex flex-wrap gap-2">
                {filterOptions.sectors.map((s) => (
                  <label
                    key={s}
                    className="flex items-center gap-1 text-xs"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    <input
                      type="checkbox"
                      checked={filters.sector.includes(s)}
                      onChange={() => onToggleFilter('sector', s)}
                    />
                    {s}
                  </label>
                ))}
              </div>
            </div>
          )}
          {filterOptions.sections.length > 0 && (
            <div>
              <div
                className="text-[10px] uppercase tracking-wider mb-1"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t('ai_reporter.filters.section_label')}
              </div>
              <div className="flex flex-wrap gap-2">
                {filterOptions.sections.map((s) => (
                  <label
                    key={s}
                    className="flex items-center gap-1 text-xs"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    <input
                      type="checkbox"
                      checked={filters.section.includes(s)}
                      onChange={() => onToggleFilter('section', s)}
                    />
                    {s}
                  </label>
                ))}
              </div>
            </div>
          )}
          {filterOptions.benches.length > 0 && (
            <div>
              <div
                className="text-[10px] uppercase tracking-wider mb-1"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t('ai_reporter.filters.bench_label')}
              </div>
              <div className="flex flex-wrap gap-2">
                {filterOptions.benches.map((b) => (
                  <label
                    key={b}
                    className="flex items-center gap-1 text-xs"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    <input
                      type="checkbox"
                      checked={filters.bench.includes(b)}
                      onChange={() => onToggleFilter('bench', b)}
                    />
                    {b}
                  </label>
                ))}
              </div>
            </div>
          )}
        </CollapsibleFieldset>
      )}

      <fieldset className="space-y-1" data-testid="ai-stream-toggle">
        <legend
          className="text-[10px] uppercase tracking-wider mb-1"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {t('ai_reporter.stream.label')}
        </legend>
        <label
          className="flex items-center gap-2 text-xs"
          style={{ color: 'var(--color-text-secondary)' }}
        >
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
        <label
          className="flex items-center gap-2 text-xs"
          style={{ color: 'var(--color-text-secondary)' }}
        >
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
        fullWidth
        loading={generating}
        disabled={formDisabled}
        onClick={onGenerate}
      >
        {generating
          ? t('ai_reporter.form.generating')
          : t('ai_reporter.form.generate_button')}
      </Button>
    </div>
  );
}