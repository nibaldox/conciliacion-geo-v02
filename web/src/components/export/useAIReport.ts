import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import client from '../../api/client';
import { useGenerateAIStream } from '../../api/hooks';
import type {
  AIGenerateRequest,
  AIResponseChunk,
  ComparisonResult,
  SectionResponse,
} from '../../api/types';
import { type AIErrorState, type AIErrorKind } from './useAIConfig';

const RATE_LIMIT_COUNTDOWN_CAP_SECONDS = 60;

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

export function classifyError(err: unknown): AIErrorState {
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
      kind: 'rate_limited' satisfies AIErrorKind,
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

interface SessionFilters {
  sector: string[];
  section: string[];
  bench: number[];
}

interface BuildPayloadArgs {
  cfg: {
    provider: string;
    model: string;
    notes: string;
    temperature: number;
    maxTokens: number;
    timeoutS: number;
    useCache: boolean;
    streamMode: 'single' | 'stream';
  };
  filters: SessionFilters;
  rows: ComparisonResult[] | undefined;
  sections: SectionResponse[] | undefined;
}

export function buildAIGeneratePayload({
  cfg,
  filters,
  rows,
  sections,
}: BuildPayloadArgs): AIGenerateRequest {
  const rowsArr: ComparisonResult[] = Array.isArray(rows) ? rows : [];
  const active = (arr: string[] | number[]) => arr.length > 0;
  const filteredComparisons = rowsArr.filter((r) => {
    if (active(filters.sector) && !filters.sector.includes(r.sector)) return false;
    if (active(filters.section) && !filters.section.includes(r.section)) return false;
    if (active(filters.bench) && !filters.bench.includes(r.bench_num)) return false;
    return true;
  });
  const sectionsArr: SectionResponse[] = sections ?? [];
  const trimmedNotes = cfg.notes.trim();
  const hasActiveFilters =
    active(filters.sector) || active(filters.section) || active(filters.bench);
  return {
    results: { comparisons: filteredComparisons },
    sections: sectionsArr,
    provider: cfg.provider,
    model: cfg.model,
    stream: cfg.streamMode === 'stream',
    metadata: trimmedNotes ? { notes: trimmedNotes } : {},
    notes: trimmedNotes || undefined,
    max_tokens: cfg.maxTokens,
    temperature: cfg.temperature,
    timeout_s: cfg.timeoutS,
    use_cache: cfg.useCache,
    filters: hasActiveFilters
      ? {
          sector: filters.sector.length ? filters.sector : undefined,
          section: filters.section.length ? filters.section : undefined,
          bench: filters.bench.length ? filters.bench : undefined,
        }
      : undefined,
  };
}

export interface UseAIReportArgs {
  buildPayload: () => AIGenerateRequest;
  enabled: boolean;
}

export interface UseAIReportResult {
  report: AIResponseChunk | null;
  errorState: AIErrorState | null;
  countdown: number;
  copied: boolean;
  latencyMs: number | null;
  isGenerating: boolean;
  generate: () => void;
  copy: () => Promise<void>;
  download: () => void;
}

/**
 * Orchestrates the AI report lifecycle: non-streaming mutation, streaming
 * fetch, rate-limit countdown, copy/download actions. Stateless apart from
 * refs and result state — purely composes the API hooks.
 */
export function useAIReport({
  buildPayload,
  enabled,
}: UseAIReportArgs): UseAIReportResult {
  const streamHook = useGenerateAIStream();
  const [report, setReport] = useState<AIResponseChunk | null>(null);
  const [errorState, setErrorState] = useState<AIErrorState | null>(null);
  const [countdown, setCountdown] = useState<number>(0);
  const [copied, setCopied] = useState<boolean>(false);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const startRef = useRef<number>(0);

  // Rate-limit countdown ticker.
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

  const generateMutation = useMutation<AIResponseChunk, unknown, AIGenerateRequest>({
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

  const isGenerating = generateMutation.isPending || streamHook.isPending;

  const generate = useCallback(() => {
    if (!enabled) return;
    setReport(null);
    setErrorState(null);
    setCopied(false);
    setLatencyMs(null);
    const payload = buildPayload();
    startRef.current = Date.now();
    if (payload.stream) {
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
      generateMutation.mutate(payload);
    }
  }, [enabled, buildPayload, streamHook, generateMutation]);

  const copy = useCallback(async () => {
    if (!report?.content) return;
    try {
      await navigator.clipboard.writeText(report.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, [report]);

  const download = useCallback(() => {
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
  }, [report]);

  return useMemo(
    () => ({
      report,
      errorState,
      countdown,
      copied,
      latencyMs,
      isGenerating,
      generate,
      copy,
      download,
    }),
    [report, errorState, countdown, copied, latencyMs, isGenerating, generate, copy, download],
  );
}

export function computeTps(
  report: AIResponseChunk | null,
  latencyMs: number | null,
): number | null {
  if (!report?.usage || !latencyMs || latencyMs <= 0) return null;
  return report.usage.completion_tokens / (latencyMs / 1000);
}

const LOCAL_PROVIDERS = new Set<string>(['ollama', 'lmstudio']);
const CLOUD_PROMPT_RATE_USD_PER_TOKEN = 0.1 / 1_000_000;
const CLOUD_COMPLETION_RATE_USD_PER_TOKEN = 0.3 / 1_000_000;

export function estimateCost(
  provider: string,
  usage: AIResponseChunk['usage'],
): number | null {
  if (!usage) return null;
  if (usage.cost_usd != null) return usage.cost_usd;
  if (LOCAL_PROVIDERS.has(provider)) return 0;
  return (
    usage.prompt_tokens * CLOUD_PROMPT_RATE_USD_PER_TOKEN +
    usage.completion_tokens * CLOUD_COMPLETION_RATE_USD_PER_TOKEN
  );
}