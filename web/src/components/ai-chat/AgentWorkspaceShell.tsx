import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useWorkspaceMode } from '../../stores/workspaceMode';
import { LoadingSpinner } from '../LoadingSpinner';
import { ChatPanel } from './ChatPanel';
import { CopilotResizeHandle } from './CopilotResizeHandle';
import { useAgentChatInvalidationBridge } from './FloatingChatButton';
import { CanvasVisibilityContext } from './canvasVisibility';
import './AgentWorkspaceShell.css';

const WIDTH_KEY = 'conciliacion.agentWorkspace.copilotWidth.v1';
function initialWidth() {
  try {
    const value = Number(localStorage.getItem(WIDTH_KEY));
    return Number.isFinite(value) && value >= 320 && value <= 520 ? value : 390;
  } catch {
    return 390;
  }
}

// The left rail may stay open in copilot only if the shell keeps room for the
// canvas minimum (480 px) plus the chat minimum (320 px): 800 px. The shell's
// width is the viewport minus the expanded rail, whose width comes from
// useSidebarResize (persisted in `sidebar_width`, 360 px by default).
const MIN_SHELL_WITH_RAIL = 480 + 320;
const RAIL_WIDTH_KEY = 'sidebar_width';
function railWidth() {
  try {
    const value = parseInt(localStorage.getItem(RAIL_WIDTH_KEY) ?? '', 10);
    return Number.isFinite(value) && value >= 300 ? Math.min(value, 520) : 360;
  } catch {
    return 360;
  }
}
function roomForRail() {
  return window.innerWidth - railWidth() >= MIN_SHELL_WITH_RAIL;
}

interface AgentWorkspaceShellProps {
  children: ReactNode;
  canvasHeader?: ReactNode;
  /** True while the initial data is still being entered (workflow not complete). */
  dataEntry?: boolean;
}

export function AgentWorkspaceShell({ children, canvasHeader, dataEntry = false }: AgentWorkspaceShellProps) {
  const { t } = useTranslation();
  const actualMode = useWorkspaceMode((s) => s.mode);
  const lastReason = useWorkspaceMode((s) => s.lastReason);
  const initialDecided = useWorkspaceMode((s) => s.initialDecided);
  const bothMeshes = useSession((s) => Boolean(s.designMeshId && s.topoMeshId));
  const waiting = !initialDecided && bothMeshes;
  const mode = waiting ? 'copilot' : actualMode;
  const wasInitiallyDecided = useRef(initialDecided);
  const [allowAnimation, setAllowAnimation] = useState(initialDecided);
  const skipInitialAnimation = !initialDecided || !allowAnimation;
  const setSidebarCollapsed = useSession((s) => s.setSidebarCollapsed);
  const [mobileView, setMobileView] = useState<'chat' | 'workspace'>('workspace');
  const [width, setWidth] = useState(initialWidth);
  const [canvasMounted, setCanvasMounted] = useState(mode === 'copilot');
  const [reduced, setReduced] = useState(() => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  const grid = useRef<HTMLDivElement>(null);
  const focusCanvas = useRef(false);
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
  useLayoutEffect(() => useWorkspaceMode.subscribe((state, old) => {
    if (state.lastReason === 'manualView' && window.innerWidth < 900) setMobileView('workspace');
    if (state.mode === 'copilot' && old.mode === 'protagonist' && state.lastReason === 'manualView') {
      focusCanvas.current = Boolean(document.activeElement?.closest('[data-slot="left-sidebar"]'));
    }
  }), []);
  useLayoutEffect(() => {
    if (focusCanvas.current && canvasMounted && !waiting) {
      grid.current?.querySelector<HTMLElement>('.agent-shell__workspace h2')?.focus();
      focusCanvas.current = false;
    }
  }, [canvasMounted, waiting, mode]);
  useLayoutEffect(() => {
    if (actualMode === 'protagonist' && lastReason === 'focusConversation' &&
      (document.activeElement === document.body || !document.activeElement?.isConnected ||
        document.activeElement?.closest('[data-testid="ai-chat-focus-conversation"]') ||
        document.activeElement?.closest('.agent-shell__workspace'))) {
      grid.current?.querySelector<HTMLElement>('[data-testid="ai-chat-input"]')?.focus();
    }
  }, [actualMode, lastReason]);
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
  // Acts only on transitions of `mode` or `dataEntry`, so a manual collapse or
  // expansion between transitions is respected. In copilot the rail stays open
  // while the initial data is entered (the next step lives in the rail) and
  // collapses once the analysis is complete or when there is no room for it.
  useLayoutEffect(() => {
    const desktop = typeof matchMedia !== 'function' || !matchMedia('(max-width: 767px)').matches;
    if (desktop) setSidebarCollapsed(mode === 'copilot' && (!dataEntry || !roomForRail()));
  }, [mode, dataEntry, setSidebarCollapsed]);
  useLayoutEffect(() => {
    const node = grid.current;
    const oldMode = previous.current;
    const changed = oldMode !== mode;
    const firstDecision = !wasInitiallyDecided.current;
    if (initialDecided) wasInitiallyDecided.current = true;
    previous.current = mode;
    if (!changed || !node) return;
    if (!firstDecision) setAllowAnimation(true);
    if (firstDecision || reduced || window.innerWidth < 900) {
      if (mode === 'copilot') setCanvasMounted(true);
      return;
    }
    const total = node.getBoundingClientRect().width;
    const targetChat = mode === 'copilot' ? Math.min(widthRef.current, Math.max(0, total - 480)) : total;
    const startChat = measured.current?.chat ?? (oldMode === 'protagonist' ? total : Math.min(widthRef.current, Math.max(0, total - 480)));
    const startCanvas = measured.current?.canvas ?? total - startChat;
    const canvas = node.querySelector<HTMLElement>('.agent-shell__canvas');
    const chat = node.querySelector<HTMLElement>('.agent-shell__chat > :not(.agent-shell__resize)');
    if (canvas) { canvas.style.width = `${mode === 'copilot' ? total - targetChat : startCanvas}px`; canvas.style.flex = 'none'; }
    if (chat) { chat.style.width = `${targetChat}px`; chat.style.flex = 'none'; }
    const release = () => {
      if (canvas) { canvas.style.width = ''; canvas.style.flex = ''; }
      if (chat) { chat.style.width = ''; chat.style.flex = ''; }
    };
    node.style.transition = 'none';
    node.style.gridTemplateColumns = `${startCanvas}px ${startChat}px`;
    void node.offsetWidth;
    node.style.transition = `grid-template-columns 200ms ${mode === 'copilot' ? 'cubic-bezier(0.2,0,0,1)' : 'cubic-bezier(0.4,0,1,1)'}`;
    node.style.gridTemplateColumns = `${Math.max(0, total - targetChat)}px ${targetChat}px`;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      node.style.transition = '';
      node.style.gridTemplateColumns = '';
      release();
      if (mode === 'copilot') setCanvasMounted(true);
    };
    const onEnd = (event: TransitionEvent) => { if (event.target === node && event.propertyName === 'grid-template-columns') finish(); };
    node.addEventListener('transitionend', onEnd);
    const timer = window.setTimeout(finish, 250);
    return () => { node.removeEventListener('transitionend', onEnd); window.clearTimeout(timer); node.style.transition = ''; node.style.gridTemplateColumns = ''; release(); };
  }, [mode, reduced, initialDecided]);
  const updateWidth = (value: number) => {
    const next = Math.min(520, Math.max(320, value));
    setWidth(next);
  };
  const persistWidth = (value: number) => {
    try { localStorage.setItem(WIDTH_KEY, String(value)); } catch { /* Storage is optional. */ }
  };
  const setDragging = (dragging: boolean) => {
    const canvas = grid.current?.querySelector<HTMLElement>('.agent-shell__canvas');
    if (!canvas) return;
    canvas.style.width = dragging ? `${canvas.getBoundingClientRect().width}px` : '';
    canvas.style.flex = dragging ? 'none' : '';
  };
  const style = { '--agent-chat-width': `${width}px` } as CSSProperties;
  return (
    <div className={`agent-shell agent-shell--${mode} agent-shell--mobile-${mobileView}${skipInitialAnimation ? ' agent-shell--no-animation' : ''}`} style={style}>
      {mode === 'copilot' && <nav className="agent-shell__controls" aria-label={t('agentWorkspace.navigation')}>
        <button type="button" onClick={() => setMobileView('workspace')} aria-pressed={mobileView === 'workspace'}>{t('agentWorkspace.workspace')}</button>
        <button type="button" onClick={() => setMobileView('chat')} aria-pressed={mobileView === 'chat'}>{t('agentWorkspace.chat')}</button>
      </nav>}
      <div className="agent-shell__grid" ref={grid}>
        <div className="agent-shell__workspace" aria-hidden={mode === 'protagonist' ? true : undefined} inert={mode === 'protagonist' ? true : undefined}>
          {canvasMounted ? <div className="agent-shell__canvas">{waiting ? <LoadingSpinner /> : <CanvasVisibilityContext.Provider value={mode === 'protagonist'}>{canvasHeader}{children}</CanvasVisibilityContext.Provider>}</div> : <div className="agent-shell__placeholder" aria-hidden="true" />}
        </div>
        <div className="agent-shell__chat">
          {mode === 'copilot' && <CopilotResizeHandle width={width} onChange={updateWidth} onCommit={persistWidth} onDragChange={setDragging} />}
          <ChatPanel presentation="embedded" layout={mode} onClose={() => setMobileView('workspace')} />
        </div>
      </div>
    </div>
  );
}
