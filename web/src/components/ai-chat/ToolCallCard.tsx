import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  downloadExportFile,
  exportDownloadFromEvent,
  extractExportDownload,
  type ExportDownloadInfo,
} from '../../api/aiChat';
import type { ChatMessage } from '../../stores/aiChat';
import { useAIChat } from '../../stores/aiChat';
import { Spinner } from '../ui/Spinner';

export type ToolCardMessage = Extract<ChatMessage, { kind: 'tool' }>;
export type ConfirmationCardMessage = Extract<
  ChatMessage,
  { kind: 'confirmation' }
>;

/**
 * The tool_result `download` payload wins when present (it carries the
 * export filters); the summary is only the fallback for results without it.
 */
function exportDownloadInfoOf(
  message: ToolCardMessage,
): ExportDownloadInfo | null {
  if (message.download) return exportDownloadFromEvent(message.download);
  return extractExportDownload(message.summary);
}

function ExportDownloadButton({ message }: { message: ToolCardMessage }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const info =
    message.name === 'export_report' && message.status === 'ok'
      ? exportDownloadInfoOf(message)
      : null;
  if (!info) return null;
  const handleDownload = async () => {
    setBusy(true);
    try {
      await downloadExportFile(info);
    } catch {
      useAIChat.setState({
        notice: { severity: 'error', key: 'aiChat.notice.download_failed' },
      });
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      data-testid="ai-chat-tool-download"
      onClick={() => void handleDownload()}
      disabled={busy}
      className="mt-2 w-full rounded-md border border-border px-3 py-1 text-[11px] font-medium text-text-secondary hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
    >
      {busy
        ? t('aiChat.tool.downloading')
        : t('aiChat.tool.download', { filename: info.filename })}
    </button>
  );
}

/**
 * One agent tool step: a collapsed, dimmed one-line card — spinner +
 * "ejecutando «name»…" while in flight, then tool name + status. The
 * result summary (ok) or the error (failure) and the export download
 * action live inside a details panel collapsed by default (hidden
 * attribute). Content is ALWAYS plain text — tool summaries come from
 * the server and are never rendered as HTML or markdown.
 */
export function ToolCallCard({ message }: { message: ToolCardMessage }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const detailsId = `ai-chat-tool-details-${message.id}`;
  return (
    <div
      data-slot="ai-chat-tool-card"
      data-status={message.status}
      className="rounded-lg border border-border/60 bg-surface-muted px-2.5 py-1.5 text-[11px] text-text-secondary"
    >
      <button
        type="button"
        data-testid="ai-chat-tool-toggle"
        aria-expanded={expanded}
        aria-controls={detailsId}
        title={t(expanded ? 'aiChat.tool.collapse' : 'aiChat.tool.expand')}
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 rounded text-left font-medium text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span
          aria-hidden="true"
          className="w-3 shrink-0 text-text-muted"
        >
          {expanded ? '▾' : '▸'}
        </span>
        {message.status === 'running' ? (
          <Spinner size="sm" />
        ) : (
          <span
            aria-hidden="true"
            className={`inline-block h-2 w-2 shrink-0 rounded-full ${
              message.status === 'ok'
                ? 'bg-[var(--status-ok-text)]'
                : 'bg-[var(--status-nok-text)]'
            }`}
          />
        )}
        <span className="min-w-0 flex-1 truncate">
          {message.status === 'running'
            ? t('aiChat.tool.running', { name: message.name })
            : message.name}
        </span>
        {message.status === 'ok' && (
          <span className="shrink-0 text-text-muted">
            {t('aiChat.tool.status_ok')}
          </span>
        )}
        {message.status === 'error' && (
          <span className="shrink-0 text-[var(--status-nok-text)]">
            {t('aiChat.tool.status_error')}
          </span>
        )}
      </button>
      <div id={detailsId} data-testid="ai-chat-tool-details" hidden={!expanded}>
        {message.summary && (
          <p className="mt-1 whitespace-pre-wrap break-words text-text-secondary">
            {message.summary}
          </p>
        )}
        {message.status === 'error' && message.error && (
          <p className="mt-1 whitespace-pre-wrap break-words text-[var(--status-nok-text)]">
            {message.error}
          </p>
        )}
        {message.status === 'ok' && <ExportDownloadButton message={message} />}
      </div>
    </div>
  );
}

function ActivityStep({ message }: { message: ToolCardMessage }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  const unknown = message.status === 'error' && message.invocationId.startsWith('restored_') && !message.error?.trim();
  const duration = message.durationMs == null ? null : message.durationMs < 1000
    ? t('aiChat.tool.duration_ms', { ms: message.durationMs })
    : t('aiChat.tool.duration_s', { s: (message.durationMs / 1000).toFixed(1) });
  return <div className="min-w-0">
    <button type="button" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded((value) => !value)} className="flex w-full min-w-0 items-center gap-2 text-left focus-visible:ring-2 focus-visible:ring-accent">
      <span className="shrink-0">{expanded ? '▾' : '▸'}</span>
      {message.status === 'running' && <Spinner size="sm" />}
      <span className="shrink-0">{t(`aiChat.activity.names.${message.name}`, { defaultValue: message.name })}</span>
      {message.status === 'ok' && <span className="sr-only">{t('aiChat.tool.status_ok')}</span>}
      {unknown && <span className="shrink-0">{t('aiChat.activity.unrecorded')}</span>}
      {!unknown && message.status === 'error' && <span className="shrink-0 text-[var(--status-nok-text)]">{t('aiChat.tool.status_error')}</span>}
      {duration && <span className="shrink-0">{duration}</span>}
      {message.summary && <span title={message.summary} className="min-w-0 truncate">⎿ {message.summary}</span>}
    </button>
    <div id={id} hidden={!expanded} className="min-w-0 pl-4">
      <p className="break-all font-mono">{message.name}</p>
      <p>{duration ?? t('aiChat.tool.no_duration')}</p>
      {message.args && <><p>{t('aiChat.tool.params')}</p><table className="w-full table-fixed"><tbody>{Object.entries(message.args).map(([key, value]) => <tr key={key}><th className="break-all text-left">{key}</th><td className="break-all">{formatParameter(value)}</td></tr>)}</tbody></table></>}
      {message.summary && <p className="whitespace-pre-wrap break-words">{message.summary}</p>}
      {message.status === 'error' && message.error && <p className="whitespace-pre-wrap break-words text-[var(--status-nok-text)]">{message.error}</p>}
      {message.status === 'ok' && <ExportDownloadButton message={message} />}
    </div>
  </div>;
}

function formatParameter(value: unknown): string {
  if (value !== null && typeof value === 'object') {
    try { return (JSON.stringify(value) ?? String(value)).slice(0, 300); } catch { return String(value).slice(0, 300); }
  }
  return String(value);
}

export function ToolActivityGroup({ messages }: { messages: ToolCardMessage[] }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const id = useId();
  const unknown = (m: ToolCardMessage) => m.status === 'error' && m.invocationId.startsWith('restored_') && !m.error?.trim();
  const error = messages.some((m) => m.status === 'error' && !unknown(m));
  const hasUnknown = messages.some(unknown);
  const running = messages.some((m) => m.status === 'running');
  const collapsed = messages.length > 6 && !showAll;
  return <div className="min-w-0 border-y border-border py-2 text-xs text-text-secondary">
    <button type="button" aria-expanded={expanded} aria-controls={id} onClick={() => setExpanded((v) => !v)} className="flex w-full items-center gap-2 text-left font-medium focus-visible:ring-2 focus-visible:ring-accent">
      <span aria-hidden="true">{expanded ? '▾' : '▸'}</span><span>{t('aiChat.activity.title')} · {messages.length}</span><span className={error ? 'text-[var(--status-nok-text)]' : ''}>{error ? t('aiChat.tool.status_error') : running ? t('aiChat.activity.running') : hasUnknown ? t('aiChat.activity.unrecorded') : t('aiChat.tool.status_ok')}</span>
    </button>
    <div id={id} hidden={!expanded} className="min-w-0 space-y-1 pt-2">
      {(collapsed ? messages.slice(0, 3) : messages).map((m) => <ActivityStep key={m.id} message={m} />)}
      {collapsed && <><button type="button" onClick={() => setShowAll(true)}>+{messages.length - 5}</button>{messages.slice(-2).map((m) => <ActivityStep key={m.id} message={m} />)}</>}
    </div>
  </div>;
}

interface ConfirmationCardProps {
  message: ConfirmationCardMessage;
  busy: boolean;
  onApprove: () => void;
  onDeny: () => void;
}

/**
 * Replace/EXPENSIVE_REPLACE confirmation: tool name + impact summary
 * (server-provided args_summary) + Confirmar/Cancelar. The buttons only
 * forward the decision — invocation id included, nothing else: the
 * frontend never sends provider, model, args or messages to /confirm.
 */
export function ConfirmationCard({
  message,
  busy,
  onApprove,
  onDeny,
}: ConfirmationCardProps) {
  const { t } = useTranslation();
  return (
    <div
      data-slot="ai-chat-confirmation-card"
      data-resolution={message.resolution}
      className="min-w-0 rounded-lg border border-[var(--color-status-warning)] bg-surface px-3 py-2 text-xs"
      role="alertdialog"
      aria-label={t('aiChat.confirm.title')}
    >
      <p data-slot="ai-chat-confirmation-title" className="font-semibold text-text-primary">
        {t('aiChat.confirm.title')}
      </p>
      <p className="mt-1 break-words font-medium text-text-primary">{t(`aiChat.activity.names.${message.name}`, { defaultValue: message.name })}</p>
      <p className="break-all font-mono text-text-muted">{message.name}</p>
      <p className="mt-1 whitespace-pre-wrap break-words text-text-secondary">
        {message.argsSummary}
      </p>
      {message.resolution === 'pending' ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="ai-chat-confirm-approve"
            disabled={busy}
            onClick={onApprove}
            className="rounded-md bg-accent px-3 py-1 font-medium text-accent-fg disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('aiChat.confirm.approve')}
          </button>
          <button
            type="button"
            data-testid="ai-chat-confirm-deny"
            disabled={busy}
            onClick={onDeny}
            className="rounded-md border border-border px-3 py-1 text-text-secondary hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('aiChat.confirm.deny')}
          </button>
        </div>
      ) : (
        <p className="mt-2 text-text-muted">
          {message.resolution === 'approved'
            ? t('aiChat.confirm.approved_chip')
            : t('aiChat.tool.denied_note')}
        </p>
      )}
    </div>
  );
}
