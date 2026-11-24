import { type ReactNode } from 'react';

/**
 * Accessible tooltip built with pure CSS (no popper.js / floating-ui
 * dependency). Renders a <span> wrapper that shows a bubble on
 * hover and on keyboard focus. The bubble inherits the theme via
 * CSS custom properties so it works in both light and dark mode.
 *
 * Usage:
 *   <Tooltip content="Bench height tolerance in metres">
 *     <span>Bench height</span>
 *   </Tooltip>
 *
 * For interactive triggers, pass asChild to merge into the child:
 *   <Tooltip content="..." asChild>
 *     <button>Hover me</button>
 *   </Tooltip>
 */
interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  /** Show on which side. Default 'top'. */
  side?: 'top' | 'bottom' | 'left' | 'right';
  /** Alignment of the bubble. Default 'center'. */
  align?: 'center' | 'start' | 'end';
  /** When true, don't render the wrapper span (merge props onto child). */
  asChild?: boolean;
  /** Optional className applied to the wrapper. */
  className?: string;
}

export function Tooltip({ content, children, side = 'top', align = 'center', asChild, className }: TooltipProps) {
  const alignAttr = align !== 'center' ? align : undefined;
  if (asChild) {
    return (
      <span className={`conciliacion-tooltip ${className ?? ''}`} data-side={side} data-align={alignAttr}>
        {children}
        <span role="tooltip" className="conciliacion-tooltip__bubble">{content}</span>
      </span>
    );
  }
  return (
    <span className={`conciliacion-tooltip ${className ?? ''}`} data-side={side} data-align={alignAttr}>
      {children}
      <span role="tooltip" className="conciliacion-tooltip__bubble">{content}</span>
    </span>
  );
}
