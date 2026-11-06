import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { cameraView, defaultCameraToggles, toggleCameraOption } from '../viewerCameraState';
import { ViewerCameraControls } from '../ViewerCameraControls';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

describe('camera views', () => {
  it('frames the centered model in the original diagonal view', () => {
    expect(cameraView('reset', 100)).toEqual({ position: [100, 80, 100], up: [0, 1, 0], target: [0, 0, 0] });
  });
  it('looks down with north at the top', () => {
    expect(cameraView('plan', 100)).toEqual({ position: [0, 200, 0], up: [0, 0, -1], target: [0, 0, 0] });
  });
  it('looks from north and east', () => {
    expect(cameraView('north', 100).position).toEqual([0, 0, -200]);
    expect(cameraView('east', 100).position).toEqual([200, 0, 0]);
  });
  it('toggles only the selected option', () => {
    expect(toggleCameraOption(defaultCameraToggles, 'pivot')).toEqual({ pivot: false, grid: true, compass: true });
  });
});

describe('camera controls', () => {
  it('exposes toggles and dispatches plan view', () => {
    const onView = vi.fn();
    const onToggle = vi.fn();
    render(<ViewerCameraControls toggles={defaultCameraToggles} onView={onView} onToggle={onToggle} />);
    expect(screen.getByRole('button', { name: 'viewer.camera.pivot' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'viewer.camera.plan' }));
    expect(onView).toHaveBeenCalledWith('plan');
    fireEvent.click(screen.getByRole('button', { name: 'viewer.camera.grid' }));
    expect(onToggle).toHaveBeenCalledWith('grid');
  });
});
