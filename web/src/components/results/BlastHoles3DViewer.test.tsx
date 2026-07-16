import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import i18n from '../../i18n';
import { BlastHoles3DViewer, centerHoles } from './BlastHoles3DViewer';
import type { BlastHoleSummary } from '../../api/types';

// ─── Mocks ─────────────────────────────────────────────────

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="mocked-canvas">{children}</div>
  ),
}));

vi.mock('@react-three/drei', () => ({
  OrbitControls: () => <div data-testid="mocked-orbit-controls" />,
  Html: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="mocked-html">{children}</div>
  ),
}));

vi.mock('../../api/hooks', () => ({
  useBlastHolesBySession: vi.fn(),
}));

const { useBlastHolesBySession } = await import('../../api/hooks');

function mockHoles(overrides: Partial<ReturnType<typeof useBlastHolesBySession>> = {}) {
  vi.mocked(useBlastHolesBySession).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
    ...overrides,
  } as ReturnType<typeof useBlastHolesBySession>);
}

function renderViewer(props: { sessionId: string | null; sectionName?: string | null }) {
  return render(<BlastHoles3DViewer sessionId={props.sessionId} sectionName={props.sectionName} />);
}

// ─── Tests ─────────────────────────────────────────────────

describe('centerHoles', () => {
  it('returns correct center for a known list of holes', () => {
    const holes: BlastHoleSummary[] = [
      { hole_id: 'H1', x: 0, y: 0, z: 0, carga: 10, descarga: 5, hardness: 'soft' },
      { hole_id: 'H2', x: 2, y: 4, z: 6, carga: 20, descarga: 10, hardness: 'hard' },
    ];
    const result = centerHoles(holes);
    expect(result.center).toEqual([1, 2, 3]);
    expect(result.radius).toBeCloseTo(Math.sqrt(14));
  });

  it('returns default { center: [0,0,0], radius: 10 } for empty input', () => {
    expect(centerHoles([])).toEqual({ center: [0, 0, 0], radius: 10 });
  });
});

describe('<BlastHoles3DViewer />', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('es');
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the empty state when sessionId is null', () => {
    mockHoles();
    renderViewer({ sessionId: null });
    expect(screen.getByTestId('viewer-no-session')).toHaveTextContent('Sin sesión activa');
  });

  it('renders the loading state when query is pending', () => {
    mockHoles({ isLoading: true });
    renderViewer({ sessionId: 'sess-001' });
    expect(screen.getByTestId('viewer-loading')).toHaveTextContent('Cargando pozos…');
  });
});
