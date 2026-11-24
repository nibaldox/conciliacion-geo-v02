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
  it('ignores non-primary pointer drags', () => {
    vi.stubGlobal('PointerEvent', MouseEvent);
    render(<Harness />);
    const handle = screen.getByRole('separator');
    handle.setPointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { button: 2, clientX: 500 });
    fireEvent.pointerMove(handle, { buttons: 2, clientX: 400 });
    expect(handle).toHaveAttribute('aria-valuenow', '390');
    expect(handle.setPointerCapture).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
  it('ends a drag when buttons are released and commits only once', () => {
    vi.stubGlobal('PointerEvent', MouseEvent);
    const change = vi.fn();
    const commit = vi.fn();
    render(<CopilotResizeHandle width={390} onChange={change} onCommit={commit} />);
    const handle = screen.getByRole('separator');
    handle.setPointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { button: 0, buttons: 1, clientX: 500 });
    fireEvent.pointerMove(handle, { buttons: 1, clientX: 450 });
    expect(commit).not.toHaveBeenCalled();
    fireEvent.pointerMove(handle, { buttons: 0, clientX: 440 });
    expect(commit).toHaveBeenCalledTimes(1);
    fireEvent.pointerMove(handle, { buttons: 1, clientX: 400 });
    expect(change).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
  it('uses measured chat width and available maximum for accessibility and dragging', () => {
    vi.stubGlobal('PointerEvent', MouseEvent);
    const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      const width = this.dataset.testid === 'grid' ? 850 : this.dataset.testid === 'chat' ? 350 : 0;
      return { width, height: 500, x: 0, y: 0, top: 0, bottom: 500, left: 0, right: width, toJSON: () => ({}) };
    });
    const change = vi.fn();
    render(<div data-testid="grid"><div data-testid="chat"><CopilotResizeHandle width={500} onChange={change} /></div></div>);
    const handle = screen.getByRole('separator');
    expect(handle).toHaveAttribute('aria-valuenow', '350');
    expect(handle).toHaveAttribute('aria-valuemax', '370');
    handle.setPointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { button: 0, buttons: 1, clientX: 500 });
    fireEvent.pointerMove(handle, { buttons: 1, clientX: 490 });
    expect(change).toHaveBeenLastCalledWith(360);
    rect.mockRestore();
    vi.unstubAllGlobals();
  });
  it('widens the chat while the pointer moves left', () => {
    vi.stubGlobal('PointerEvent', MouseEvent);
    render(<Harness />);
    const handle = screen.getByRole('separator');
    handle.setPointerCapture = vi.fn();
    fireEvent.pointerDown(handle, { clientX: 500, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 450, pointerId: 1, buttons: 1 });
    expect(handle).toHaveAttribute('aria-valuenow', '440');
    fireEvent.pointerUp(handle, { clientX: 450, pointerId: 1 });
    vi.unstubAllGlobals();
  });
});
