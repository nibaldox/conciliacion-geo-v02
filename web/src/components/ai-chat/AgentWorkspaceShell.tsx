import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import { ChatPanel } from './ChatPanel';
import { CopilotResizeHandle } from './CopilotResizeHandle';
import { useAgentChatInvalidationBridge } from './FloatingChatButton';
import './AgentWorkspaceShell.css';

const WIDTH_KEY = 'conciliacion.agentWorkspace.copilotWidth.v1';
function initialWidth() {
  const value = Number(localStorage.getItem(WIDTH_KEY));
  return Number.isFinite(value) && value >= 320 && value <= 520 ? value : 390;
}

export function AgentWorkspaceShell({ children, canvasHeader }: { children: ReactNode; canvasHeader?: ReactNode }) {
  const { t } = useTranslation();
  const mode = useWorkspaceMode((s) => s.mode);
  const setSidebarCollapsed = useSession((s) => s.setSidebarCollapsed);
  const [mobileView, setMobileView] = useState<'chat' | 'workspace'>('workspace');
  const [width, setWidth] = useState(initialWidth);
  const [canvasMounted, setCanvasMounted] = useState(mode === 'copilot');
  const [reduced, setReduced] = useState(() => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  const grid = useRef<HTMLDivElement>(null);
  const previous = useRef(mode);
  const measured = useRef<{ canvas: number; chat: number } | null>(null);
  const widthRef = useRef(width);
  widthRef.current = width;
  useAgentChatInvalidationBridge();

  useEffect(() => {
    if (typeof matchMedia !== 'function') return;
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  useLayoutEffect(() => {
    const node = grid.current;
    if (!node || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      if (!node.style.transition) measured.current = { canvas: node.children[0].getBoundingClientRect().width, chat: node.children[1].getBoundingClientRect().width };
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node.children[0]);
    observer.observe(node.children[1]);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    const desktop = typeof matchMedia !== 'function' || !matchMedia('(max-width: 767px)').matches;
    if (desktop) setSidebarCollapsed(mode === 'copilot');
  }, [mode, setSidebarCollapsed]);
  useLayoutEffect(() => {
    const node = grid.current;
    const oldMode = previous.current;
    const changed = oldMode !== mode;
    previous.current = mode;
    if (!changed || !node) return;
    if (mode === 'copilot') setCanvasMounted(true);
    if (reduced || window.innerWidth < 900) {
      setCanvasMounted(mode === 'copilot');
      return;
    }
    const total = node.getBoundingClientRect().width;
    const targetChat = mode === 'copilot' ? Math.min(widthRef.current, Math.max(0, total - 480)) : total;
    const startChat = measured.current?.chat ?? (oldMode === 'protagonist' ? total : Math.min(widthRef.current, Math.max(0, total - 480)));
    const startCanvas = measured.current?.canvas ?? total - startChat;
    node.style.transition = 'none';
    node.style.gridTemplateColumns = `${startCanvas}px ${startChat}px`;
    void node.offsetWidth;
    node.style.transition = `grid-template-columns ${mode === 'copilot' ? 380 : 280}ms cubic-bezier(.2,.8,.2,1)`;
    node.style.gridTemplateColumns = `${Math.max(0, total - targetChat)}px ${targetChat}px`;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      node.style.transition = '';
      node.style.gridTemplateColumns = '';
      if (mode === 'protagonist') setCanvasMounted(false);
    };
    const onEnd = (event: TransitionEvent) => { if (event.target === node && event.propertyName === 'grid-template-columns') finish(); };
    node.addEventListener('transitionend', onEnd);
    const timer = window.setTimeout(finish, mode === 'copilot' ? 430 : 330);
    return () => { node.removeEventListener('transitionend', onEnd); window.clearTimeout(timer); node.style.transition = ''; node.style.gridTemplateColumns = ''; };
  }, [mode, reduced]);
  const updateWidth = (value: number) => {
    const next = Math.min(520, Math.max(320, value));
    setWidth(next);
    localStorage.setItem(WIDTH_KEY, String(next));
  };
  const style = { '--agent-chat-width': `${width}px` } as CSSProperties;
  return (
    <div className={`agent-shell agent-shell--${mode} agent-shell--mobile-${mobileView}`} style={style}>
      {mode === 'copilot' && <nav className="agent-shell__controls" aria-label={t('agentWorkspace.navigation')}>
        <button type="button" onClick={() => setMobileView('workspace')} aria-pressed={mobileView === 'workspace'}>{t('agentWorkspace.workspace')}</button>
        <button type="button" onClick={() => setMobileView('chat')} aria-pressed={mobileView === 'chat'}>{t('agentWorkspace.chat')}</button>
      </nav>}
      <div className="agent-shell__grid" ref={grid}>
        <div className="agent-shell__workspace" aria-hidden={mode === 'protagonist' ? true : undefined} inert={mode === 'protagonist' ? true : undefined}>
          {canvasMounted && <div className="agent-shell__canvas">{canvasHeader}{children}</div>}
        </div>
        <div className="agent-shell__chat">
          {mode === 'copilot' && <CopilotResizeHandle width={width} onChange={updateWidth} />}
          <ChatPanel presentation="embedded" layout={mode} onClose={() => setMobileView('workspace')} />
        </div>
      </div>
    </div>
  );
}
