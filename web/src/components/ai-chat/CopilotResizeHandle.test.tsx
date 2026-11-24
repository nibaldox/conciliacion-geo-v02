import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { CopilotResizeHandle } from './CopilotResizeHandle';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
function Harness() {
  const [width, setWidth] = useState(390);
  return <CopilotResizeHandle width={width} onChange={setWidth} />;
}
describe('CopilotResizeHandle', () => {
  it('widens the chat while the pointer moves left', () => {
    vi.stubGlobal('PointerEvent', MouseEvent);
    render(<Harness />);
    const handle = screen.getByRole('separator');
    handle.setPointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 450, pointerId: 1 });
    expect(handle).toHaveAttribute('aria-valuenow', '440');
    fireEvent.pointerUp(handle, { clientX: 450, pointerId: 1 });
    vi.unstubAllGlobals();
  });
});
