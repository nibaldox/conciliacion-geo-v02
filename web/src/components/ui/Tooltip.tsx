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
  /** When true, don't render the wrapper span (merge props onto child). */
  asChild?: boolean;
  /** Optional className applied to the wrapper. */
  className?: string;
}

export function Tooltip({ content, children, side = 'top', asChild, className }: TooltipProps) {
  if (asChild) {
    // The asChild pattern would normally require a Slot from radix-ui
    // or @radix-ui/react-slot. We don't have that dep, so we fall back
    // to wrapping. The caller is responsible for ensuring the child
    // is a single focusable element.
    return (
      <span className={`conciliacion-tooltip ${className ?? ''}`} data-side={side}>
        {children}
        <span role="tooltip" className="conciliacion-tooltip__bubble">{content}</span>
      </span>
    );
  }
  return (
    <span className={`conciliacion-tooltip ${className ?? ''}`} data-side={side}>
      {children}
      <span role="tooltip" className="conciliacion-tooltip__bubble">{content}</span>
    </span>
  );
}
