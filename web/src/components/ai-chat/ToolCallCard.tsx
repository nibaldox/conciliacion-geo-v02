import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { downloadExportFile, extractExportDownload } from '../../api/aiChat';
import type { ChatMessage } from '../../stores/aiChat';
import { useAIChat } from '../../stores/aiChat';
import { Spinner } from '../ui/Spinner';

export type ToolCardMessage = Extract<ChatMessage, { kind: 'tool' }>;
export type ConfirmationCardMessage = Extract<
  ChatMessage,
  { kind: 'confirmation' }
>;

function ExportDownloadButton({ message }: { message: ToolCardMessage }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const info =
    message.name === 'export_report' && message.status === 'ok'
      ? extractExportDownload(message.summary)
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
 * One agent tool step: "ejecutando…" while in flight, then the result
 * summary (ok) or the error (failure). Content is ALWAYS plain text —
 * tool summaries come from the server and are never rendered as HTML
 * or markdown. An ok export_report result additionally renders a
 * Download action that fetches the export endpoint with the session
 * headers and saves the blob under the server-provided filename.
 */
export function ToolCallCard({ message }: { message: ToolCardMessage }) {
  const { t } = useTranslation();
  return (
    <div
      data-slot="ai-chat-tool-card"
      data-status={message.status}
      className="rounded-lg border border-border bg-surface px-3 py-2 text-xs"
    >
      <div className="flex items-center gap-2">
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
        <span className="font-medium text-text-primary">
          {message.status === 'running'
            ? t('aiChat.tool.running', { name: message.name })
            : message.name}
        </span>
        {message.status === 'ok' && (
          <span className="text-text-muted">{t('aiChat.tool.status_ok')}</span>
        )}
        {message.status === 'error' && (
          <span className="text-[var(--status-nok-text)]">
            {t('aiChat.tool.status_error')}
          </span>
        )}
      </div>
      {message.status !== 'running' && message.summary && (
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
  );
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
      className="rounded-lg border border-[var(--color-status-warning)] bg-surface px-3 py-2 text-xs"
      role="alertdialog"
      aria-label={t('aiChat.confirm.title')}
    >
      <p className="font-semibold text-text-primary">
        {t('aiChat.confirm.title')}
      </p>
      <p className="mt-1 font-medium text-text-primary">{message.name}</p>
      <p className="mt-1 whitespace-pre-wrap break-words text-text-secondary">
        {message.argsSummary}
      </p>
      {message.resolution === 'pending' ? (
        <div className="mt-2 flex gap-2">
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
