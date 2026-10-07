export interface HorizontalDeviationMessage {
  readonly key: string;
  readonly options?: Record<string, string | number>;
}

export function horizontalDeviationWarning(message: string): HorizontalDeviationMessage {
  const [code, ...parts] = message.split(':');
  if (code === 'coarsened_resolution') return { key: 'horizontalDeviation.warning.resolution_limit' };
  if (code === 'rejected_section_pair' || code === 'sector_sections_not_contiguous') {
    return { key: 'horizontalDeviation.warning.rejected_section_pair' };
  }
  if (code === 'section_pair_gap_too_large') return { key: 'horizontalDeviation.warning.section_gap' };
  if (code === 'section_pair_azimuth_change_too_large') return { key: 'horizontalDeviation.warning.direction_change' };
  if (code === 'section_pair_zero_spacing') return { key: 'horizontalDeviation.warning.zero_spacing' };
  if (code === 'section_pair_has_no_cells') return { key: 'horizontalDeviation.warning.no_cells' };
  if (code === 'no_design_faces_intersected_the_selected_sector' || code === 'no_design_faces_available') {
    return { key: 'horizontalDeviation.warning.no_design_faces' };
  }
  if (code === 'incomplete_cell_corners' || code === 'missing_or_ambiguous_corner') {
    return { key: 'horizontalDeviation.warning.incomplete_cells' };
  }
  if (code === 'insufficient_sections' || message.includes('At least two configured sections')) {
    return { key: 'horizontalDeviation.warning.two_sections' };
  }
  if (code === 'sector_required') return { key: 'horizontalDeviation.warning.sector_required' };
  if (code === 'invalid_detection_setting') return { key: 'horizontalDeviation.warning.invalid_detection_setting' };
  if (code === 'no_compatible_section_pairs') return { key: 'horizontalDeviation.warning.no_compatible_section_pairs' };
  if (message.includes('No adjacent section pair')) {
    return { key: 'horizontalDeviation.warning.rejected_section_pair' };
  }
  if (message.startsWith('Requested grid needs more than') || message.startsWith('Requested grid exceeds')) {
    return { key: 'horizontalDeviation.warning.resolution_limit' };
  }
  if (parts.length > 0 && code.startsWith('section_pair_')) {
    return { key: 'horizontalDeviation.warning.rejected_section_pair' };
  }
  return { key: 'horizontalDeviation.warning.generic' };
}

export function horizontalDeviationError(error: unknown): HorizontalDeviationMessage | null {
  if (!error || typeof error !== 'object') return null;
  const shaped = error as {
    response?: { data?: { detail?: unknown; code?: unknown; message?: unknown } };
  };
  const data = shaped.response?.data;
  if (!data) return null;
  if (typeof data.code === 'string') return horizontalDeviationWarning(data.code);
  if (typeof data.detail === 'string') return horizontalDeviationWarning(data.detail);
  if (data.detail && typeof data.detail === 'object') {
    const detail = data.detail as Record<string, unknown>;
    if (typeof detail.code === 'string') return horizontalDeviationWarning(detail.code);
    if (typeof detail.message === 'string') return horizontalDeviationWarning(detail.message);
  }
  if (typeof data.message === 'string') return horizontalDeviationWarning(data.message);
  return null;
}
