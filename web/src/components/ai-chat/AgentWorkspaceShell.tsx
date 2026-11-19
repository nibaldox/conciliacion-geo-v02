import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ChatPanel } from './ChatPanel';
import { useAgentChatInvalidationBridge } from './FloatingChatButton';
import './AgentWorkspaceShell.css';

export function AgentWorkspaceShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [mobileView, setMobileView] = useState<'chat' | 'workspace'>('workspace');
  useAgentChatInvalidationBridge();

  return (
    <div className={`agent-shell agent-shell--mobile-${mobileView}`}>
      <nav className="agent-shell__controls" aria-label={t('agentWorkspace.navigation')}>
        <button type="button" onClick={() => setMobileView('workspace')} aria-pressed={mobileView === 'workspace'}>{t('agentWorkspace.workspace')}</button>
        <button type="button" onClick={() => setMobileView('chat')} aria-pressed={mobileView === 'chat'}>{t('agentWorkspace.chat')}</button>
      </nav>
      <div className="agent-shell__workspace">{children}</div>
      <div className="agent-shell__chat">
        <ChatPanel presentation="embedded" onClose={() => setMobileView('workspace')} />
      </div>
    </div>
  );
}
