import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation } from '@tanstack/react-query';
import client from '../../api/client';
import { useResults, useSections, useGenerateAIStream } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { Button } from '../ui/Button';
import type {
  AIGenerateRequest,
  AIResponseChunk,
  AIUsageMetrics,
  ComparisonResult,
  SectionResponse,
} from '../../api/types';

interface AIHealthResponse {
  status: string;
  version?: string;
  providers?: string[];
}

interface AIProvidersResponse {
  providers: string[];
}

type AIErrorKind = 'rate_limited' | 'server' | 'network';

interface AIErrorState {
  kind: AIErrorKind;
  detail: string;
  retryAfter?: number;
}

type StreamMode = 'single' | 'stream';

const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  ollama: 'llama3.1:8b',
  lmstudio: 'loaded-model',
  openai: 'gpt-4o-mini',
  openrouter: 'nvidia/nemotron-3-ultra-550b-a55b:free',
  minimax: 'MiniMax-M3',
  glm: 'glm-5.2',
  grok: 'grok-4.20',
};

const HEALTH_REFETCH_MS = 30_000;
const RATE_LIMIT_COUNTDOWN_CAP_SECONDS = 60;

const LOCAL_PROVIDERS = new Set<string>(['ollama', 'lmstudio']);
const CLOUD_PROMPT_RATE_USD_PER_TOKEN = 0.1 / 1_000_000;
const CLOUD_COMPLETION_RATE_USD_PER_TOKEN = 0.3 / 1_000_000;

const DEFAULT_TEMPERATURE = 0.7;
const DEFAULT_MAX_TOKENS = 2000;
const DEFAULT_TIMEOUT_S = 60;

function estimateCost(provider: string, usage: AIUsageMetrics | null): number | null {
  if (!usage) return null;
  if (usage.cost_usd != null) return usage.cost_usd;
  if (LOCAL_PROVIDERS.has(provider)) return 0;
  return (
    usage.prompt_tokens * CLOUD_PROMPT_RATE_USD_PER_TOKEN +
    usage.completion_tokens * CLOUD_COMPLETION_RATE_USD_PER_TOKEN
  );
}

function useAIHealth() {
  return useQuery({
    queryKey: ['ai-health'],
    queryFn: () => client.get<AIHealthResponse>('/ai/health').then((r) => r.data),
    refetchInterval: HEALTH_REFETCH_MS,
    retry: false,
  });
}

function useAIProviders(enabled: boolean) {
  return useQuery({
    queryKey: ['ai-providers'],
    queryFn: () =>
      client.get<AIProvidersResponse>('/ai/providers').then((r) => r.data),
    enabled,
    staleTime: 60_000,
  });
}

function readHeader(headers: unknown, key: string): string | undefined {
  if (!headers || typeof headers !== 'object') return undefined;
  const h = headers as Record<string, unknown>;
  if (typeof h.get === 'function') {
    const v = (h.get as (k: string) => unknown)(key);
    return typeof v === 'string' ? v : undefined;
  }
  const lower = h[key.toLowerCase()];
  if (typeof lower === 'string') return lower;
  const raw = h[key];
  return typeof raw === 'string' ? raw : undefined;
}

function classifyError(err: unknown): AIErrorState {
  if (!err || typeof err !== 'object') {
    return { kind: 'network', detail: '' };
  }
  const e = err as {
    response?: { status?: number; data?: { detail?: string }; headers?: unknown };
    message?: string;
  };
  const status = e.response?.status;
  if (status === 429) {
    const raw = readHeader(e.response?.headers, 'retry-after');
    const parsed = raw ? Number.parseInt(raw, 10) : NaN;
    return {
      kind: 'rate_limited',
      detail: '',
      retryAfter: Number.isFinite(parsed) ? parsed : undefined,
    };
  }
  if (status === 502 || status === 504) {
    return { kind: 'server', detail: e.response?.data?.detail ?? '' };
  }
  if (status === undefined) {
    return { kind: 'network', detail: '' };
  }
  return { kind: 'server', detail: e.response?.data?.detail ?? e.message ?? '' };
}

interface FieldsetProps {
  summary: string;
  open: boolean;
  onToggle: () => void;
  testId: string;
  children: React.ReactNode;
}

function CollapsibleFieldset({ summary, open, onToggle, testId, children }: FieldsetProps) {
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

export function AIReporter() {
  const { t } = useTranslation();
  const demoMode = useSession((s) => s.demoMode);
  const filters = useSession((s) => s.filters);
  const setFilters = useSession((s) => s.setFilters);
  const health = useAIHealth();
  const healthState: 'pending' | 'ok' | 'unavailable' = health.isLoading
    ? 'pending'
    : health.isError || health.data?.status !== 'ok'
      ? 'unavailable'
      : 'ok';

  const providersQuery = useAIProviders(healthState === 'ok');
  const resultsQuery = useResults();
  const sectionsQuery = useSections();
  const hasResults = !!resultsQuery.data && resultsQuery.data.length > 0;
  const streamHook = useGenerateAIStream();

  const [provider, setProvider] = useState<string>('');
  const [model, setModel] = useState<string>('');
  const [notes, setNotes] = useState<string>('');
  const [report, setReport] = useState<AIResponseChunk | null>(null);
  const [errorState, setErrorState] = useState<AIErrorState | null>(null);
  const [countdown, setCountdown] = useState<number>(0);
  const [copied, setCopied] = useState<boolean>(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);
  const [showFilters, setShowFilters] = useState<boolean>(false);
  const [temperature, setTemperature] = useState<number>(DEFAULT_TEMPERATURE);
  const [maxTokens, setMaxTokens] = useState<number>(DEFAULT_MAX_TOKENS);
  const [timeoutS, setTimeoutS] = useState<number>(DEFAULT_TIMEOUT_S);
  const [useCache, setUseCache] = useState<boolean>(true);
  const [streamMode, setStreamMode] = useState<StreamMode>('single');

  const startRef = useRef<number>(0);

  useEffect(() => {
    if (!provider && providersQuery.data?.providers?.length) {
      const first = providersQuery.data.providers[0];
      setProvider(first);
      setModel(PROVIDER_DEFAULT_MODELS[first] ?? '');
    }
  }, [providersQuery.data, provider]);

  useEffect(() => {
    if (errorState?.kind !== 'rate_limited' || !errorState.retryAfter) {
      setCountdown(0);
      return;
    }
    const start = Math.min(
      Math.max(errorState.retryAfter, 1),
      RATE_LIMIT_COUNTDOWN_CAP_SECONDS,
    );
    setCountdown(start);
    const id = window.setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          window.clearInterval(id);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [errorState]);

  const filterOptions = useMemo(() => {
    const rows: ComparisonResult[] = Array.isArray(resultsQuery.data)
      ? resultsQuery.data
      : [];
    const sectors = new Set<string>();
    const sections = new Set<string>();
    const benches = new Set<number>();
    rows.forEach((r) => {
      if (r.sector) sectors.add(r.sector);
      if (r.section) sections.add(r.section);
      if (typeof r.bench_num === 'number') benches.add(r.bench_num);
    });
    return {
      sectors: Array.from(sectors).sort(),
      sections: Array.from(sections).sort(),
      benches: Array.from(benches).sort((a, b) => a - b),
    };
  }, [resultsQuery.data]);

  const generate = useMutation<AIResponseChunk, unknown, AIGenerateRequest>({
    mutationFn: (payload) =>
      client.post<AIResponseChunk>('/ai/generate', payload).then((r) => r.data),
    onSuccess: (data) => {
      setReport(data);
      setErrorState(null);
      setLatencyMs(Date.now() - startRef.current);
    },
    onError: (err) => {
      setErrorState(classifyError(err));
    },
  });

  const generating = generate.isPending || streamHook.isPending;
  const formDisabled =
    healthState !== 'ok' ||
    !hasResults ||
    !provider ||
    !model ||
    generating ||
    countdown > 0;

  const handleProviderChange = (next: string) => {
    setProvider(next);
    setModel(PROVIDER_DEFAULT_MODELS[next] ?? '');
  };

  const buildPayload = (): AIGenerateRequest => {
    const rows: ComparisonResult[] = Array.isArray(resultsQuery.data)
      ? resultsQuery.data
      : [];
    const active = (arr: string[] | number[]) => arr.length > 0;
    const filteredComparisons = rows.filter((r) => {
      if (active(filters.sector) && !filters.sector.includes(r.sector)) return false;
      if (active(filters.section) && !filters.section.includes(r.section)) return false;
      if (active(filters.bench) && !filters.bench.includes(r.bench_num)) return false;
      return true;
    });
    const sections: SectionResponse[] = sectionsQuery.data ?? [];
    const trimmedNotes = notes.trim();
    const hasActiveFilters =
      active(filters.sector) || active(filters.section) || active(filters.bench);
    return {
      results: { comparisons: filteredComparisons },
      sections,
      provider,
      model,
      stream: streamMode === 'stream',
      metadata: trimmedNotes ? { notes: trimmedNotes } : {},
      notes: trimmedNotes || undefined,
      max_tokens: maxTokens,
      temperature,
      timeout_s: timeoutS,
      use_cache: useCache,
      filters: hasActiveFilters
        ? {
            sector: filters.sector.length ? filters.sector : undefined,
            section: filters.section.length ? filters.section : undefined,
            bench: filters.bench.length ? filters.bench : undefined,
          }
        : undefined,
    };
  };

  const handleGenerate = () => {
    if (formDisabled) return;
    setReport(null);
    setErrorState(null);
    setCopied(false);
    setLatencyMs(null);
    const payload = buildPayload();
    startRef.current = Date.now();
    if (streamMode === 'stream') {
      streamHook.stream(payload, {
        onChunk: (acc) =>
          setReport({
            content: acc,
            finish_reason: null,
            usage: null,
            cached: false,
            chunk_index: 0,
          }),
        onDone: (full, usage, cached) => {
          setReport({
            content: full,
            finish_reason: 'stop',
            usage,
            cached,
            chunk_index: 0,
          });
          setLatencyMs(usage?.duration_ms ?? Date.now() - startRef.current);
          setErrorState(null);
        },
        onError: (err) => setErrorState(classifyError(err)),
      });
    } else {
      generate.mutate(payload);
    }
  };

  const handleCopy = async () => {
    if (!report?.content) return;
    try {
      await navigator.clipboard.writeText(report.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const handleDownload = () => {
    if (!report?.content) return;
    const blob = new Blob([report.content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `informe_${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const toggleFilter = (
    key: 'sector' | 'section' | 'bench',
    value: string | number,
  ) => {
    const current = filters[key] as Array<string | number>;
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    setFilters({ [key]: next } as Partial<typeof filters>);
  };

  const healthLabel =
    healthState === 'ok'
      ? t('ai_reporter.health.ok')
      : healthState === 'unavailable'
        ? t('ai_reporter.health.unavailable')
        : t('ai_reporter.health.pending');
  const healthIcon =
    healthState === 'ok' ? '✓' : healthState === 'unavailable' ? '⚠' : '…';

  const showUnavailable = healthState === 'unavailable';
  const showEmptyState = !hasResults && !demoMode && healthState === 'ok';
  const showForm = healthState === 'ok' && (hasResults || demoMode);

  const tps = useMemo(() => {
    if (!report?.usage || !latencyMs || latencyMs <= 0) return null;
    return report.usage.completion_tokens / (latencyMs / 1000);
  }, [report, latencyMs]);

  const costUsd = report?.usage ? estimateCost(provider, report.usage) : null;

  return (
    <div data-slot="ai-reporter" className="space-y-5">
      <div
        className="rounded-xl shadow-sm p-5"
        style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div className="flex items-center justify-between gap-3">
          <h4
            className="text-sm font-semibold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {t('ai_reporter.title')}
          </h4>
          <span
            className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full"
            style={{
              backgroundColor: 'var(--color-accent-soft)',
              color: 'var(--color-text-muted)',
            }}
          >
            {t('ai_reporter.ready_badge')}
          </span>
        </div>

        <div className="flex items-center gap-3 mt-3">
          <span aria-hidden="true" className="text-base">
            {healthIcon}
          </span>
          <div className="flex-1 min-w-0">
            <div
              className="text-[10px] uppercase tracking-wider mb-0.5"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {t('ai_reporter.backend_status')}
            </div>
            <div
              className="text-xs font-medium"
              style={{ color: 'var(--color-text-primary)' }}
              data-testid="ai-reporter-health"
            >
              {healthLabel}
            </div>
          </div>
        </div>
      </div>

      {showUnavailable && (
        <div
          className="rounded-xl shadow-sm p-5"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          data-testid="ai-reporter-unavailable"
        >
          <h5
            className="text-sm font-semibold mb-1"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {t('ai_reporter.error.unavailable_title')}
          </h5>
          <p
            className="text-xs leading-relaxed"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {t('ai_reporter.error.unavailable_description')}
          </p>
        </div>
      )}

      {showEmptyState && (
        <div
          className="rounded-xl shadow-sm p-5"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          data-testid="ai-reporter-empty"
        >
          <h5
            className="text-sm font-semibold mb-1"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {t('ai_reporter.empty.no_data_title')}
          </h5>
          <p
            className="text-xs leading-relaxed"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {t('ai_reporter.empty.no_data_description')}
          </p>
        </div>
      )}

      {showForm && (
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
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={!providersQuery.data?.providers?.length}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                backgroundColor: 'var(--color-surface)',
              }}
            >
              {!(providersQuery.data?.providers?.length) && (
                <option value="">{t('ai_reporter.health.pending')}</option>
              )}
              {(providersQuery.data?.providers ?? []).map((p) => (
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
              value={model}
              onChange={(e) => setModel(e.target.value)}
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
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
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
            open={showAdvanced}
            onToggle={() => setShowAdvanced((v) => !v)}
            testId="ai-advanced"
          >
            <div>
              <label
                htmlFor="ai-temperature"
                className="block text-xs font-medium mb-1"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {t('ai_reporter.advanced.temperature_label')} ({temperature.toFixed(2)})
              </label>
              <input
                id="ai-temperature"
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
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
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(Number(e.target.value))}
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
                  value={timeoutS}
                  onChange={(e) => setTimeoutS(Number(e.target.value))}
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
                checked={useCache}
                onChange={(e) => setUseCache(e.target.checked)}
                data-testid="ai-use-cache"
              />
              {t('ai_reporter.advanced.cache_label')}
            </label>
          </CollapsibleFieldset>

          {hasResults && (
            <CollapsibleFieldset
              summary={t('ai_reporter.filters.toggle')}
              open={showFilters}
              onToggle={() => setShowFilters((v) => !v)}
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
                          onChange={() => toggleFilter('sector', s)}
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
                          onChange={() => toggleFilter('section', s)}
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
                          onChange={() => toggleFilter('bench', b)}
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
                checked={streamMode === 'single'}
                onChange={() => setStreamMode('single')}
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
                checked={streamMode === 'stream'}
                onChange={() => setStreamMode('stream')}
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
            onClick={handleGenerate}
          >
            {generating
              ? t('ai_reporter.form.generating')
              : t('ai_reporter.form.generate_button')}
          </Button>
        </div>
      )}

      {errorState && (
        <div
          className="rounded-xl shadow-sm p-4"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          role="alert"
          data-testid="ai-reporter-error"
        >
          <p
            className="text-xs"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {errorState.kind === 'rate_limited' && countdown > 0
              ? t('ai_reporter.error.rate_limited', { seconds: countdown })
              : errorState.kind === 'network'
                ? t('ai_reporter.error.network_error')
                : errorState.detail
                  ? `${t('ai_reporter.error.server_error')}: ${errorState.detail}`
                  : t('ai_reporter.error.server_error')}
          </p>
          {errorState.kind !== 'rate_limited' && (
            <button
              type="button"
              onClick={handleGenerate}
              className="mt-2 text-xs underline"
              style={{ color: 'var(--color-accent)' }}
            >
              {t('common.retry')}
            </button>
          )}
        </div>
      )}

      {report && (
        <div
          className="rounded-xl shadow-sm p-5 space-y-3"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          data-testid="ai-reporter-result"
        >
          <div className="flex items-center justify-between gap-3">
            <h5
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {t('ai_reporter.report.title')}
            </h5>
            <div className="flex items-center gap-2">
              {report.cached && (
                <span
                  className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full"
                  style={{
                    backgroundColor: 'var(--color-accent-soft)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {t('ai_reporter.report.cached_badge')}
                </span>
              )}
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleCopy}
                disabled={!report.content}
              >
                {t('ai_reporter.form.copy_button')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleDownload}
                disabled={!report.content}
                data-testid="ai-download-md"
              >
                {t('ai_reporter.form.download_button')}
              </Button>
            </div>
          </div>

          <div
            className="text-xs leading-relaxed"
            style={{
              color: 'var(--color-text-primary)',
              maxHeight: '600px',
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              fontFamily: 'var(--font-mono, ui-monospace, monospace)',
            }}
            data-testid="ai-reporter-content"
          >
            {report.content}
          </div>

          {copied && (
            <p
              className="text-[10px]"
              style={{ color: 'var(--color-text-muted)' }}
              data-testid="ai-reporter-copied"
            >
              ✓
            </p>
          )}

          {report.usage && (
            <div
              className="flex items-center flex-wrap gap-2 text-[11px]"
              style={{ color: 'var(--color-text-secondary)' }}
              data-testid="ai-reporter-usage"
            >
              <span>
                {t('ai_reporter.report.tokens_label', {
                  prompt: report.usage.prompt_tokens,
                  completion: report.usage.completion_tokens,
                  total: report.usage.total_tokens,
                })}
              </span>
              {tps !== null && (
                <span data-testid="ai-reporter-tps">
                  {t('ai_reporter.report.tps_label', { tps: tps.toFixed(1) })}
                </span>
              )}
              {costUsd !== null && (
                <span data-testid="ai-reporter-cost">
                  {t('ai_reporter.report.cost_label', {
                    cost: costUsd.toFixed(4),
                  })}
                </span>
              )}
              {report.usage.is_synthetic && (
                <span
                  className="px-1.5 py-0.5 rounded-full text-[10px]"
                  style={{
                    backgroundColor: 'var(--color-accent-soft)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {t('ai_reporter.report.estimated_badge')}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
