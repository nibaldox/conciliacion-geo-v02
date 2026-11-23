import { useEffect, useRef } from 'react';
import { useProcessStatus } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { useWorkspaceMode } from '../../stores/workspaceMode';

export function useWorkspaceModeCoordinator() {
  const { data, isSuccess, isError } = useProcessStatus();
  const design = useSession((state) => state.designMeshId);
  const topo = useSession((state) => state.topoMeshId);
  const demo = useSession((state) => state.demoMode && Boolean(state.demoData));
  const initialized = useRef(false);
  const ownNavigation = useRef(false);
  const manualNavigation = useRef(false);
  const previousMeshes = useRef(false);
  const previousDemo = useRef(false);
  const previousComplete = useRef(false);

  useEffect(() => {
    const unsubscribeSession = useSession.subscribe((state, previous) => {
      if (!initialized.current || ownNavigation.current) return;
      if (state.demoMode && !previous.demoMode && state.demoData) return;
      if (state.activeWorkspaceView !== previous.activeWorkspaceView) {
        manualNavigation.current = true;
        useWorkspaceMode.getState().enterCopilot('manualView');
      }
    });
    const unsubscribeMode = useWorkspaceMode.subscribe((state, previous) => {
      if (state !== previous && state.lastReason === 'manualView') {
        manualNavigation.current = true;
      }
    });
    return () => {
      unsubscribeSession();
      unsubscribeMode();
    };
  }, []);

  useEffect(() => {
    const both = Boolean(design && topo);
    const complete = isSuccess && data?.status === 'complete';
    const navigate = (view: '3d' | 'dashboard') => {
      ownNavigation.current = true;
      try {
        useSession.getState().setActiveWorkspaceView(view);
      } finally {
        ownNavigation.current = false;
      }
    };

    if (!initialized.current) {
      if (!isSuccess && !isError) return;
      previousMeshes.current = both;
      previousDemo.current = demo;
      previousComplete.current = complete;
      if (manualNavigation.current) {
        initialized.current = true;
        return;
      }
      if (isSuccess && (demo || (complete && (data?.n_results ?? 0) > 0))) {
        useWorkspaceMode.getState().enterCopilot(demo ? 'demo' : 'resultsRestored');
        navigate('dashboard');
      } else if (both) {
        useWorkspaceMode.getState().enterCopilot('meshesReady');
        navigate('3d');
      }
      initialized.current = true;
      return;
    }

    if (demo && !previousDemo.current) {
      useWorkspaceMode.getState().enterCopilot('demo');
      if (!manualNavigation.current) navigate('dashboard');
    } else if (both && !previousMeshes.current) {
      useWorkspaceMode.getState().enterCopilot('meshesReady');
      if (!manualNavigation.current) navigate('3d');
    }
    if (complete && !previousComplete.current && useSession.getState().activeWorkspaceView === '3d') {
      navigate('dashboard');
    }
    previousMeshes.current = both;
    previousDemo.current = demo;
    if (isSuccess) previousComplete.current = complete;
  }, [data, isSuccess, isError, design, topo, demo]);
}
