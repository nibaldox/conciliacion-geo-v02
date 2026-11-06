import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ViewerCameraControls } from '../ViewerCameraControls';
import { cameraView, defaultCameraToggles, setPivot, isPivotClick } from '../viewerCameraState';
import es from '../../../locales/es.json';
import en from '../../../locales/en.json';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

describe('camera tools', () => {
  it('uses the selected pivot for plan and resets to center', () => {
    const pivot = setPivot([12, 4, -7]);
    expect(cameraView('plan', 100, pivot)).toEqual({ position: [12, 204, -7], up: [0, 0, -1], target: pivot });
    expect(cameraView('reset', 100, pivot).target).toEqual([0, 0, 0]);
  });
  it('rejects a drag', () => {
    expect(isPivotClick([10, 10], [12, 12])).toBe(true);
    expect(isPivotClick([10, 10], [20, 10])).toBe(false);
  });
  it('renders seven accessible icon-only tools and toggles pivot mode with Escape', () => {
    const onPickPivot = vi.fn();
    const { rerender } = render(<ViewerCameraControls toggles={defaultCameraToggles} onView={vi.fn()} onToggle={vi.fn()} pickingPivot={false} onPickPivot={onPickPivot} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(7);
    for (const button of buttons) {
      expect(button.textContent).toBe('');
      expect(button.querySelector('svg')).not.toBeNull();
      expect(button.getAttribute('title')).toBe(button.getAttribute('aria-label'));
    }
    const pick = screen.getByRole('button', { name: 'viewer.camera.setPivot' });
    expect(pick.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(pick);
    expect(onPickPivot).toHaveBeenCalledWith(true);
    rerender(<ViewerCameraControls toggles={defaultCameraToggles} onView={vi.fn()} onToggle={vi.fn()} pickingPivot onPickPivot={onPickPivot} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onPickPivot).toHaveBeenCalledWith(false);
    expect(screen.getByRole('button', { name: 'viewer.camera.grid' }).getAttribute('aria-pressed')).toBe('true');
  });
  it('has matching translated tool keys', () => {
    expect(Object.keys(es.viewer.camera).sort()).toEqual(Object.keys(en.viewer.camera).sort());
    expect(es.viewer.camera.setPivot).toBeTruthy();
    expect(en.viewer.camera.setPivot).toBeTruthy();
  });
});
