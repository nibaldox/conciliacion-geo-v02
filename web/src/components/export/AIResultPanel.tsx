import { useTranslation } from 'react-i18next';
import { Button } from '../ui/Button';
import { type AIErrorState } from './useAIConfig';
import type { AIResponseChunk, AIUsageMetrics } from '../../api/types';

interface AIResultPanelProps {
  errorState: AIErrorState | null;
  countdown: number;
  onRetry: () => void;
  report: AIResponseChunk | null;
  tps: number | null;
  costUsd: number | null;
  copied: boolean;
  onCopy: () => void;
  onDownload: () => void;
}

export function AIResultPanel({
  errorState,
  countdown,
  onRetry,
  report,
  tps,
  costUsd,
  copied,
  onCopy,
  onDownload,
}: AIResultPanelProps) {
  const { t } = useTranslation();

  if (!errorState && !report) return null;

  return (
    <>
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
              onClick={onRetry}
              className="mt-2 text-xs underline"
              style={{ color: 'var(--color-accent)' }}
            >
              {t('common.retry')}
            </button>
          )}
        </div>
      )}

      {report && (
        <ResultCard
          report={report}
          tps={tps}
          costUsd={costUsd}
          copied={copied}
          onCopy={onCopy}
          onDownload={onDownload}
        />
      )}
    </>
  );
}

interface ResultCardProps {
  report: AIResponseChunk;
  tps: number | null;
  costUsd: number | null;
  copied: boolean;
  onCopy: () => void;
  onDownload: () => void;
}

function ResultCard({
  report,
  tps,
  costUsd,
  copied,
  onCopy,
  onDownload,
}: ResultCardProps) {
  const { t } = useTranslation();
  const usage: AIUsageMetrics | null = report.usage ?? null;

  return (
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
            onClick={onCopy}
            disabled={!report.content}
          >
            {t('ai_reporter.form.copy_button')}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onDownload}
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

      {usage && (
        <div
          className="flex items-center flex-wrap gap-2 text-[11px]"
          style={{ color: 'var(--color-text-secondary)' }}
          data-testid="ai-reporter-usage"
        >
          <span>
            {t('ai_reporter.report.tokens_label', {
              prompt: usage.prompt_tokens,
              completion: usage.completion_tokens,
              total: usage.total_tokens,
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
          {usage.is_synthetic && (
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
  );
}