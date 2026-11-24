import { useTranslation } from 'react-i18next';
import { useAIChat } from '../../stores/aiChat';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import { ChatPet } from './ChatPet';
import { Spinner } from '../ui/Spinner';

export function CopilotHeader({ hasModel, providerLabel, model, onRefresh, onClear, onClearBlur, refreshing, busy, clearing, confirmingClear }: {
  hasModel: boolean;
  providerLabel: string;
  model: string | null;
  onRefresh: () => void;
  onClear: () => void;
  onClearBlur: () => void;
  refreshing: boolean;
  busy: boolean;
  clearing: boolean;
  confirmingClear: boolean;
}) {
  const { t } = useTranslation();
  const pending = useAIChat((state) => state.pendingConfirmation);
  const messages = useAIChat((state) => state.messages);
  const streaming = useAIChat((state) => state.streaming || state.sendInFlight);
  const error = useAIChat((state) => state.providerStateError || state.notice?.severity === 'error');
  const status = pending ? 'confirm'
    : messages.some((message) => message.kind === 'tool' && message.status === 'running') ? 'tool'
      : streaming ? 'thinking'
        : error ? 'error'
          : !hasModel ? 'off' : 'ready';
  const description = [providerLabel, model].filter(Boolean).join(' · ');
  return (
    <div>
      <div className="flex min-w-0 items-center gap-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center [&_.ai-pet__svg]:!h-6 [&_.ai-pet__svg]:!w-6"><ChatPet streaming={streaming} /></span>
        <span data-testid="ai-chat-status" className="min-w-0 flex-1 truncate text-sm font-medium">{t('aiChat.copilot.agent')} <span className="font-normal text-text-muted">· {t(`aiChat.copilot.status_${status}`)}</span></span>
        <button type="button" data-testid="ai-chat-models-refresh" aria-label={t('aiChat.model.refresh')} title={t('aiChat.model.refresh')} onClick={onRefresh} disabled={refreshing || busy} className="h-7 w-7 shrink-0 rounded text-text-muted hover:text-text-primary disabled:opacity-50">↻</button>
        <button type="button" data-testid="ai-chat-clear" aria-label={confirmingClear ? t('aiChat.clear_confirm') : t('aiChat.clear')} title={confirmingClear ? t('aiChat.clear_confirm') : t('aiChat.clear')} onClick={onClear} onBlur={onClearBlur} disabled={busy} aria-busy={clearing} className="h-7 w-7 shrink-0 rounded text-text-muted hover:text-text-primary disabled:opacity-50">{clearing ? <Spinner size="sm" /> : confirmingClear ? '✓' : <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mx-auto h-4 w-4"><path d="M4 7h16M10 4h4M7 7l1 13h8l1-13M10 10v7m4-7v7" /></svg>}</button>
        <button type="button" data-testid="ai-chat-focus-conversation" aria-label={t('agentWorkspace.focus')} title={t('agentWorkspace.focus')} onClick={() => useWorkspaceMode.getState().focusConversation()} className="flex h-7 w-7 shrink-0 items-center justify-center rounded text-text-muted hover:text-text-primary">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5m11-5v5h-5M4 4l6 6m10-6-6 6M4 20l6-6m10 6-6-6" /></svg>
        </button>
      </div>
      {description && <div title={description} className="truncate pl-8 text-xs text-text-muted"><span data-testid="ai-chat-local-badge">{providerLabel}</span>{model && <> · <span data-testid="ai-chat-model-chip">{model}</span></>}</div>}
    </div>
  );
}
