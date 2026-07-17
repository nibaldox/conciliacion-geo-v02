/**
 * Domain types for the ProfileView feature.
 *
 * These types are derived from the API DTOs (`web/src/api/types.ts`)
 * but are independent of the wire format. The infrastructure layer's
 * `apiAdapter` is the only place that knows how to translate between
 * the two. This way the domain can be unit-tested without a network
 * and can evolve independently of the backend.
 *
 * Strict TypeScript: no `any`, exhaustive switches via the
 * `assertNever` helper, and explicit nullability.
 */

import type { BenchParams, ComparisonResult, ProfileData, SectionResponse } from '../../../../api/types';

// ─── Status ──────────────────────────────────────────────────

/**
 * The compliance status of a bench, normalised from the backend's
 * heterogeneous `*_status` strings (which can be 'CUMPLE',
 * 'FUERA DE TOLERANCIA', 'NO CUMPLE', 'NO CONSTRUIDO', 'FALTA BANCO',
 * 'EXTRA', 'BANCO ADICIONAL').
 *
 * The seven API strings collapse into four semantically distinct
 * buckets we care about for the UI:
 *   - CUMPLE     → within tolerance
 *   - FUERA      → outside tolerance but not catastrophic
 *   - NO_CUMPLE  → catastrophic (no build, missing, etc.)
 *   - UNKNOWN    → not yet evaluated or status string was unrecognised
 */
export type BenchStatus = 'CUMPLE' | 'FUERA' | 'NO_CUMPLE' | 'UNKNOWN';

// ─── Profile data ───────────────────────────────────────────

/** A 2-D point along a section, in the section's local frame. */
export interface ProfilePoint {
  /** Distance from section origin, in metres. */
  distance: number;
  /** Elevation, in metres. */
  elevation: number;
}

/** A polyline along the section: design, topo, or reconciled. */
export interface ProfileLine {
  readonly kind: 'design' | 'topo' | 'reconciled_design' | 'reconciled_topo';
  readonly points: readonly ProfilePoint[];
}

// ─── Bench (domain) ─────────────────────────────────────────

/** A single bench, in the domain shape. Derived from `BenchParams`
 *  plus the comparison result for that bench. */
export interface Bench {
  readonly benchNumber: number;
  readonly crestElevation: number;
  readonly crestDistance: number;
  readonly toeElevation: number;
  readonly toeDistance: number;
  readonly height: number;
  readonly designHeight: number | null;
  readonly faceAngle: number;
  readonly designAngle: number | null;
  /** `null` if the bench has no berm (e.g. last bench in the pit). */
  readonly bermWidth: number | null;
  readonly designBerm: number | null;
  readonly isRamp: boolean;
  /** Worst-of-three compliance status (height / angle / berm). */
  readonly status: BenchStatus;
  readonly heightStatus: BenchStatus;
  readonly angleStatus: BenchStatus;
  readonly bermStatus: BenchStatus;
  /** `true` if this bench exists in both design and topo. */
  readonly matched: boolean;
  readonly deltaCrest: number | null;
  readonly deltaToe: number | null;
}

// ─── Section metadata ───────────────────────────────────────

/** The static metadata for a section (origin, azimuth, etc.). */
export interface SectionMeta {
  readonly id: string;
  readonly name: string;
  readonly sector: string;
  readonly azimuth: number;
  readonly length: number;
  readonly origin: readonly [number, number];
}

// ─── Profile view model ─────────────────────────────────────

/** The complete, ready-to-render view of a section. */
export interface ProfileViewModel {
  readonly section: SectionMeta;
  readonly lines: readonly ProfileLine[];
  readonly benches: readonly Bench[];
  readonly floorElevation?: number | null;
  readonly crestElevationMax?: number | null;
}

// ─── Source DTOs (narrowed) ─────────────────────────────────

/** The minimal slice of `ProfileData` the domain actually consumes. */
export type ProfileDataDto = ProfileData;

/** The minimal slice of `SectionResponse` the domain actually consumes. */
export type SectionResponseDto = SectionResponse;

/** The minimal slice of `ComparisonResult` the domain actually consumes. */
export type ComparisonResultDto = ComparisonResult;

/** The minimal slice of `BenchParams` the domain actually consumes. */
export type BenchParamsDto = BenchParams;

// ─── Utility ────────────────────────────────────────────────

/** Compile-time exhaustiveness guard. Use in the `default:` branch
 *  of switches over a union to make TypeScript complain if a new
 *  variant is added without handling. */
export function assertNever(x: never): never {
  throw new Error(`Unhandled discriminant: ${JSON.stringify(x)}`);
}
