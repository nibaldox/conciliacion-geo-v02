export type CameraView = 'reset' | 'plan' | 'north' | 'east';
export type CameraOption = 'pivot' | 'grid' | 'compass';
export type CameraToggles = Record<CameraOption, boolean>;
export type Pivot = [number, number, number];
export const defaultCameraToggles: CameraToggles = { pivot: true, grid: true, compass: true };

export function toggleCameraOption(state: CameraToggles, option: CameraOption): CameraToggles {
  return { ...state, [option]: !state[option] };
}

export function setPivot(point: Pivot): Pivot {
  return [...point];
}

export function isPivotClick(start: [number, number], end: [number, number]): boolean {
  return Math.hypot(end[0] - start[0], end[1] - start[1]) <= 5;
}

export function cameraView(view: CameraView, maxDim: number, pivot: Pivot = [0, 0, 0]): { position: Pivot; up: Pivot; target: Pivot } {
  const d = Number.isFinite(maxDim) && maxDim > 0 ? maxDim : 100;
  const target: Pivot = view === 'reset' ? [0, 0, 0] : setPivot(pivot);
  const offset: Pivot = view === 'reset' ? [d, d * 0.8, d]
    : view === 'plan' ? [0, d * 2, 0]
      : view === 'north' ? [0, 0, -d * 2] : [d * 2, 0, 0];
  const position: Pivot = [target[0] + offset[0], target[1] + offset[1], target[2] + offset[2]];
  return { position, up: view === 'plan' ? [0, 0, -1] : [0, 1, 0], target };
}
