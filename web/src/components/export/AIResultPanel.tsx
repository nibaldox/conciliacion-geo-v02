import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
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
        <div className="flex flex-wrap items-center justify-end gap-2">
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
        className="min-w-0 max-w-full overflow-x-auto text-sm leading-7"
        style={{ color: 'var(--color-text-primary)' }}
        data-testid="ai-reporter-content"
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => <h1 className="mb-4 mt-2 text-2xl font-semibold leading-tight" style={{ color: 'var(--color-text-primary)' }}>{children}</h1>,
            h2: ({ children }) => <h2 className="mb-3 mt-6 border-b pb-2 text-xl font-semibold leading-tight" style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}>{children}</h2>,
            h3: ({ children }) => <h3 className="mb-2 mt-5 text-lg font-semibold leading-tight" style={{ color: 'var(--color-text-primary)' }}>{children}</h3>,
            h4: ({ children }) => <h4 className="mb-2 mt-4 text-base font-semibold" style={{ color: 'var(--color-text-primary)' }}>{children}</h4>,
            p: ({ children }) => <p className="my-3 whitespace-pre-wrap">{children}</p>,
            ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
            ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
            li: ({ children }) => <li className="pl-1">{children}</li>,
            blockquote: ({ children }) => <blockquote className="my-4 border-l-2 pl-4" style={{ borderColor: 'var(--color-accent)', color: 'var(--color-text-secondary)' }}>{children}</blockquote>,
            a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2" style={{ color: 'var(--color-accent-bright)' }}>{children}</a>,
            hr: () => <hr className="my-5" style={{ borderColor: 'var(--color-border)' }} />,
            pre: ({ children }) => <pre className="my-4 overflow-x-auto rounded-lg border p-4 text-xs leading-5" style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface-sunken)', color: 'var(--color-text-primary)' }}>{children}</pre>,
            code: ({ children, className }) => <code className={className ? 'font-mono' : 'rounded px-1.5 py-0.5 font-mono text-[0.9em]'} style={{ backgroundColor: className ? undefined : 'var(--color-surface-sunken)', color: 'var(--color-text-primary)' }}>{children}</code>,
            table: ({ children }) => <div className="my-4 max-w-full overflow-x-auto rounded-lg border" style={{ borderColor: 'var(--color-border)' }}><table className="w-full min-w-[32rem] border-collapse text-left text-sm">{children}</table></div>,
            thead: ({ children }) => <thead style={{ backgroundColor: 'var(--color-surface-raised)' }}>{children}</thead>,
            th: ({ children, style }) => <th className="border-b px-3 py-2 font-semibold" style={{ borderColor: 'var(--color-border)', textAlign: style?.textAlign }}>{children}</th>,
            td: ({ children, style }) => <td className="border-b px-3 py-2 align-top" style={{ borderColor: 'var(--color-border)', textAlign: style?.textAlign }}>{children}</td>,
          }}
        >
          {report.content}
        </ReactMarkdown>
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
