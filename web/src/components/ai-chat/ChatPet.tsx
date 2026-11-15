import { useEffect, useId, useRef } from 'react';
import type { PetState } from './petState';

interface ChatPetProps {
  state?: PetState;
  size?: 'launcher' | 'inline';
  trackPointer?: boolean;
}

const EYE_TRACK_MAX_X_PX = 1.8;
const EYE_TRACK_MAX_Y_PX = 1.2;
const EYE_TRACK_SATURATION_PX = 120;

/**
 * Minimal non-human mascot: a white squircle with vertical-oval eyes and
 * state-specific expressions, without mouth, nose, or pupils. A yellow miner
 * hard hat carries a front lamp, and a speech bubble reflects each state.
 * Inline size hides the bubble and effects. Pointer tracking uses rAF to write
 * CSS variables and is disabled under prefers-reduced-motion, including changes.
 */
export function ChatPet({ state = 'idle', size = 'launcher', trackPointer = true }: ChatPetProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const fur = `ai-pet-fur-${id}`;
  const glow = `ai-pet-glow-${id}`;
  useEffect(() => {
    if (!trackPointer) return;
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let frame = 0;
    let x = 0;
    let y = 0;
    const reset = () => {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      svgRef.current?.style.removeProperty('--ai-pet-ex');
      svgRef.current?.style.removeProperty('--ai-pet-ey');
    };
    const move = (event: PointerEvent) => {
      x = event.clientX;
      y = event.clientY;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const svg = svgRef.current;
        if (!svg) return;
        const rect = svg.getBoundingClientRect();
        const dx = x - rect.left - rect.width / 2;
        const dy = y - rect.top - rect.height / 2;
        const distance = Math.hypot(dx, dy) || 1;
        const reach = Math.min(1, distance / EYE_TRACK_SATURATION_PX);
        svg.style.setProperty('--ai-pet-ex', `${(dx / distance) * EYE_TRACK_MAX_X_PX * reach}px`);
        svg.style.setProperty('--ai-pet-ey', `${(dy / distance) * EYE_TRACK_MAX_Y_PX * reach}px`);
      });
    };
    const update = () => {
      window.removeEventListener('pointermove', move);
      reset();
      if (!query?.matches) window.addEventListener('pointermove', move, { passive: true });
    };
    update();
    query?.addEventListener('change', update);
    return () => {
      window.removeEventListener('pointermove', move);
      query?.removeEventListener('change', update);
      reset();
    };
  }, [trackPointer]);
  return (
    <span
      className={`ai-pet ai-pet--${state} ai-pet--${size}`}
      data-state={state}
      aria-hidden="true"
    >
      <svg
        ref={svgRef}
        data-testid="ai-chat-pet"
        aria-hidden="true"
        viewBox="0 0 56 56"
        className="ai-pet__svg"
      >
        <defs>
          <linearGradient id={fur} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#fff" />
            <stop offset="1" stopColor="#e4e5ea" />
          </linearGradient>
          <radialGradient id={glow}>
            <stop offset="0" stopColor="#ffe9ae" />
            <stop offset="1" stopColor="#ffc94d" stopOpacity="0" />
          </radialGradient>
        </defs>
        <ellipse className="ai-pet__shade" cx="28" cy="50.6" rx="14" ry="2.2" />
        <g className="ai-pet__tilt">
          <g className="ai-pet__rig">
            <g>
              <rect
                data-testid="ai-pet-body"
                className="ai-pet__fur"
                x="10"
                y="22"
                width="36"
                height="28"
                rx="14"
                fill={`url(#${fur})`}
              />
              <ellipse cx="17.5" cy="29.2" rx="5" ry="2.3" fill="#fff" opacity=".85" />
              <g data-testid="ai-pet-eyes" className="ai-pet__eyes">
                <g className="ai-pet__eye-open">
                  <ellipse cx="21.5" cy="37" rx="1.8" ry="3.1" />
                  <ellipse cx="34.5" cy="37" rx="1.8" ry="3.1" />
                </g>
                <g className="ai-pet__eye-happy">
                  <path d="M19.2 38 Q21.5 34.6 23.8 38 M32.2 38 Q34.5 34.6 36.8 38" />
                </g>
                <g className="ai-pet__eye-squint">
                  <path d="M19.8 35.2 L23.2 37.2 L19.8 39.2 M36.2 35.2 L32.8 37.2 L36.2 39.2" />
                </g>
                <g className="ai-pet__eye-closed">
                  <path d="M19.4 37.6 Q21.5 39.2 23.6 37.6 M32.4 37.6 Q34.5 39.2 36.6 37.6" />
                </g>
              </g>
            </g>
            <g data-testid="ai-pet-helmet" className="ai-pet__helmet">
              <path
                className="ai-pet__helmet-dome"
                d="M13.6 25.4C13.9 15.6 20 9.2 28 9.2C36 9.2 42.1 15.6 42.4 25.4Z"
              />
              <path
                className="ai-pet__helmet-band"
                d="M14.3 19.6C21 18.9 35 18.9 41.7 19.6L42.3 23.4C35 22.8 21 22.8 13.7 23.4Z"
              />
              <path className="ai-pet__helmet-hi" d="M18.2 17.2C19.6 13.6 22.2 11.4 24.8 10.8" />
              <path
                className="ai-pet__helmet-brim"
                d="M9.4 25.6C9.4 23.7 18 23.1 28 23.1C38 23.1 46.6 23.7 46.6 25.6C46.6 27.3 38 27.9 28 27.9C18 27.9 9.4 27.3 9.4 25.6Z"
              />
              <circle
                className="ai-pet__lamp-glow"
                cx="28"
                cy="20.6"
                r="5"
                fill={`url(#${glow})`}
              />
              <rect
                className="ai-pet__lamp-house"
                x="24.7"
                y="17.6"
                width="6.6"
                height="5.8"
                rx="2"
              />
              <circle className="ai-pet__lamp" cx="28" cy="20.5" r="2.1" />
              <circle className="ai-pet__lamp-core" cx="27.6" cy="20" r=".75" />
            </g>
            <g className="ai-pet__sweat">
              <path d="M44.2 28.5 C44.2 28.5 42.6 31 42.6 32 A1.6 1.6 0 0 0 45.8 32 C45.8 31 44.2 28.5 44.2 28.5Z" />
            </g>
          </g>
        </g>
        <g data-testid="ai-pet-shovel" className="ai-pet__shovel">
          <rect
            className="ai-pet__shovel-shaft"
            x="47"
            y="19.6"
            width="1.9"
            height="21.6"
            rx="0.95"
          />
          <rect
            className="ai-pet__shovel-grip"
            x="44.9"
            y="18.4"
            width="6.1"
            height="2.1"
            rx="1.05"
          />
          <path
            className="ai-pet__shovel-blade"
            d="M44.2 40H51.7V45.4Q51.7 49.2 47.95 50.9Q44.2 49.2 44.2 45.4Z"
          />
          <path className="ai-pet__shovel-shine" d="M45.8 41.4V45.6" />
        </g>
        <g className="ai-pet__clods">
          <circle cx="53" cy="41" r="1.7" />
          <circle cx="54.8" cy="39.6" r="1.25" />
          <circle cx="51.3" cy="39.4" r="1.4" />
        </g>
        <g className="ai-pet__dig-dust">
          <circle cx="44.8" cy="50.4" r="1.3" />
          <circle cx="51" cy="50.4" r="1.3" />
          <circle cx="47.9" cy="51" r="1" />
        </g>
        <g className="ai-pet__spark">
          <path d="M8 12 l1 2.4 2.4 1 -2.4 1 -1 2.4 -1 -2.4 -2.4 -1 2.4 -1Z" />
          <path d="M47 8 l.8 1.9 1.9 .8 -1.9 .8 -.8 1.9 -.8 -1.9 -1.9 -.8 1.9 -.8Z" />
          <path d="M50 22 l.6 1.4 1.4 .6 -1.4 .6 -.6 1.4 -.6 -1.4 -1.4 -.6 1.4 -.6Z" />
        </g>
        <g className="ai-pet__sleep">
          <text x="42" y="12">
            z
          </text>
          <text x="45" y="8">
            z
          </text>
        </g>
        <g data-testid="ai-pet-bubble" className="ai-pet__bubble">
          <rect className="ai-pet__bubble-bg" x="38" y="3" width="15" height="10" rx="5" />
          <circle className="ai-pet__bubble-bg" cx="38.6" cy="15.2" r="1.3" />
          <g className="ai-pet__bubble-dots">
            <circle cx="41.6" cy="8" r="1.1" />
            <circle cx="45.5" cy="8" r="1.1" />
            <circle cx="49.4" cy="8" r="1.1" />
          </g>
          <text className="ai-pet__bubble-q" x="45.5" y="10.6">
            ?
          </text>
          <text className="ai-pet__bubble-bang" x="45.5" y="10.6">
            !
          </text>
          <path className="ai-pet__bubble-check" d="M42.3 8.2 L44.6 10.3 L48.8 5.8" />
        </g>
      </svg>
    </span>
  );
}
