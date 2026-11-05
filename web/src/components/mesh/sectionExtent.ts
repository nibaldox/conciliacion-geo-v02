import type { SectionResponse } from '../../api/types';

export interface SectionExtent {
  lowerStation: number;
  upperStation: number;
  start: [number, number];
  end: [number, number];
}

export function getSectionExtent(section: SectionResponse): SectionExtent {
  const hasAsymmetricLengths = section.length_up != null && section.length_down != null;
  const lowerStation = hasAsymmetricLengths ? -section.length_down! : -section.length / 2;
  const upperStation = hasAsymmetricLengths ? section.length_up! : section.length / 2;
  const azimuthRadians = (section.azimuth * Math.PI) / 180;
  const directionX = Math.sin(azimuthRadians);
  const directionY = Math.cos(azimuthRadians);
  const [originX, originY] = section.origin;

  return {
    lowerStation,
    upperStation,
    start: [originX + directionX * lowerStation, originY + directionY * lowerStation],
    end: [originX + directionX * upperStation, originY + directionY * upperStation],
  };
}
