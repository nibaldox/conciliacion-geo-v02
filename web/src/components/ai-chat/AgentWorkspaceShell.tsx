import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { ChatPanel } from './ChatPanel';
import { useAgentChatInvalidationBridge } from './FloatingChatButton';
import './AgentWorkspaceShell.css';

export function AgentWorkspaceShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const design = useSession((s) => s.designMeshId);
  const topo = useSession((s) => s.topoMeshId);
  const setSidebarCollapsed = useSession((s) => s.setSidebarCollapsed);
  const hasMesh = Boolean(design?.trim() || topo?.trim());
  const [opened, setOpened] = useState(hasMesh);
  const [wide, setWide] = useState(!hasMesh);
  const [mobileView, setMobileView] = useState<'chat' | 'workspace'>('workspace');
  const previousMesh = useRef(hasMesh);
  useAgentChatInvalidationBridge();

  useEffect(() => { setSidebarCollapsed(true); }, [setSidebarCollapsed]);
  useEffect(() => {
    if (hasMesh && !previousMesh.current) {
      setOpened(true);
      setWide(false);
      setMobileView('workspace');
    }
    previousMesh.current = hasMesh;
  }, [hasMesh]);

  const openWorkspace = () => { setOpened(true); setWide(false); setMobileView('workspace'); };
  return (
    <div className={`agent-shell ${wide ? 'agent-shell--wide' : 'agent-shell--docked'} agent-shell--mobile-${mobileView}`}>
      <div className="agent-shell__chat">
        <div className="agent-shell__chat-inner">
          {wide && <div className="agent-shell__intro"><p>CONCILIACIÓN GEO</p><h1>{t('agentWorkspace.heading')}</h1></div>}
          <div className="agent-shell__panel"><ChatPanel presentation="embedded" onClose={openWorkspace} /></div>
          {wide && <button className="agent-shell__action" type="button" onClick={openWorkspace}>{t('agentWorkspace.open')} <span aria-hidden="true">→</span></button>}
        </div>
      </div>
      {opened && <div className="agent-shell__workspace">{children}</div>}
      {opened && <nav className="agent-shell__controls" aria-label={t('agentWorkspace.navigation')}>
        <button type="button" onClick={() => { setWide(true); setMobileView('chat'); }}>{t('agentWorkspace.expandChat')}</button>
        <button type="button" onClick={() => { setWide(false); setMobileView('chat'); }} aria-pressed={!wide && mobileView === 'chat'}>{t('agentWorkspace.chat')}</button>
        <button type="button" onClick={openWorkspace} aria-pressed={!wide && mobileView === 'workspace'}>{t('agentWorkspace.workspace')}</button>
      </nav>}
    </div>
  );
}
