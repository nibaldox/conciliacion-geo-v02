import { useTranslation } from 'react-i18next';
import { useAIChat } from '../../stores/aiChat';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import { ChatPet } from './ChatPet';

export function CopilotHeader({ hasModel }: { hasModel: boolean }) {
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
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="w-7 shrink-0 [&_.ai-pet__svg]:h-7 [&_.ai-pet__svg]:w-7"><ChatPet streaming={streaming} /></span>
      <span className="min-w-0 flex-1 truncate text-sm font-semibold">{t('aiChat.copilot.agent')} <span className="font-normal text-text-muted">· {t(`aiChat.copilot.status_${status}`)}</span></span>
      <button type="button" data-testid="ai-chat-focus-conversation" aria-label={t('agentWorkspace.focus')} title={t('agentWorkspace.focus')} onClick={() => useWorkspaceMode.getState().focusConversation()} className="shrink-0 rounded p-1 text-text-muted hover:text-text-primary">
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5m11-5v5h-5M4 4l6 6m10-6-6 6M4 20l6-6m10 6-6-6" /></svg>
      </button>
    </div>
  );
}
