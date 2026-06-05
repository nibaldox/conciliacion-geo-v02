/**
 * StatusDot — minimal marker for a compliance status, used in the
 * bench table to color the row indicator. Less verbose than StatusPill.
 */

import type { CSSProperties } from 'react';
import type { BenchStatus } from '../../domain/types';
import { STATUS_BG_VAR, STATUS_BORDER_VAR } from '../../domain/status';

export interface StatusDotProps {
  readonly status: BenchStatus;
  readonly size?: number;
  readonly title?: string;
}

export function StatusDot({ status, size = 8, title }: StatusDotProps) {
  const style: CSSProperties = {
    width: size,
    height: size,
    backgroundColor: STATUS_BG_VAR[status],
    border: `1.5px solid ${STATUS_BORDER_VAR[status]}`,
  };
  return <span aria-hidden="true" data-status={status} title={title} className="inline-block rounded-full" style={style} />;
}
