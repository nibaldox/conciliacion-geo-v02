import { useEffect, useRef, useState } from 'react';

interface ChatPetProps {
  streaming?: boolean;
}

const EYE_TRACK_MAX_X_PX = 1.8;
const EYE_TRACK_MAX_Y_PX = 1.2;
const EYE_TRACK_SATURATION_PX = 120;

/**
 * Minimal non-human mascot for the floating chat launcher: white blob
 * body with two vertical-oval eyes that follow the pointer (no mouth,
 * no nose), a yellow miner's hard hat — dome, central ridge, front
 * band, wide brim, and a front lamp that pulses while streaming — and
 * a blue three-dot badge on the left brim. Pure SVG/CSS — geometry
 * lives here, animation in globals.css.
 *
 * The hex fills are the character's own brand colors (fur white,
 * helmet yellow, lamp amber, badge blue), deliberately independent
 * from the app theme tokens. Eye tracking is skipped under
 * prefers-reduced-motion.
 */
export function ChatPet({ streaming = false }: ChatPetProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [eyeOffset, setEyeOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (motionQuery.matches) return undefined;
    const onPointerMove = (event: PointerEvent) => {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const dx = event.clientX - (rect.left + rect.width / 2);
      const dy = event.clientY - (rect.top + rect.height / 2);
      const distance = Math.hypot(dx, dy);
      if (distance === 0) {
        setEyeOffset({ x: 0, y: 0 });
        return;
      }
      const reach = Math.min(1, distance / EYE_TRACK_SATURATION_PX);
      setEyeOffset({
        x: (dx / distance) * EYE_TRACK_MAX_X_PX * reach,
        y: (dy / distance) * EYE_TRACK_MAX_Y_PX * reach,
      });
    };
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
    };
  }, []);

  return (
    <span className={streaming ? 'ai-pet ai-pet--working' : 'ai-pet'} aria-hidden="true">
      <span className="ai-pet__tilt">
        <span className="ai-pet__body">
          <svg
            ref={svgRef}
            data-testid="ai-chat-pet"
            aria-hidden="true"
            viewBox="0 0 56 56"
            className="ai-pet__svg"
          >
            <defs>
              <linearGradient id="ai-pet-fur" x1="0" y1="0" x2="0" y2="1">
                <stop className="ai-pet__fur-hi" offset="0" />
                <stop className="ai-pet__fur-lo" offset="1" />
              </linearGradient>
              <radialGradient id="ai-pet-sheen">
                <stop className="ai-pet__sheen-hi" offset="0" />
                <stop className="ai-pet__sheen-lo" offset="1" />
              </radialGradient>
            </defs>
            <ellipse className="ai-pet__shade" cx="28" cy="49.6" rx="15.5" ry="2.4" />
            <rect
              data-testid="ai-pet-body"
              className="ai-pet__fur"
              x="9.5"
              y="23"
              width="37"
              height="26"
              rx="13"
            />
            <ellipse className="ai-pet__sheen" cx="18" cy="30.8" rx="5.5" ry="2.8" />
            <g
              data-testid="ai-pet-eyes"
              className="ai-pet__eyes"
              style={{
                transform: `translate(${eyeOffset.x.toFixed(2)}px, ${eyeOffset.y.toFixed(2)}px)`,
              }}
            >
              <ellipse className="ai-pet__eye" cx="21.5" cy="37.5" rx="1.7" ry="3" />
              <ellipse className="ai-pet__eye" cx="34.5" cy="37.5" rx="1.7" ry="3" />
            </g>
            <g data-testid="ai-pet-helmet">
              <path
                className="ai-pet__helmet-dome"
                d="M13.8 27C14 17 20 8.6 28 8.6C36 8.6 42 17 42.2 27Z"
              />
              <path
                className="ai-pet__helmet-band"
                d="M15.1 19.9C21 19.3 35 19.3 40.9 19.9L42.15 23.5C35 22.9 21 22.9 13.85 23.5Z"
              />
              <path
                className="ai-pet__helmet-ridge"
                d="M26.3 26C26.3 18 26.6 11.5 27.4 8.6C27.7 7.9 28.3 7.9 28.6 8.6C29.4 11.5 29.7 18 29.7 26Z"
              />
              <ellipse className="ai-pet__helmet-brim" cx="28" cy="26" rx="18.5" ry="3.4" />
              <rect
                className="ai-pet__lamp-bracket"
                x="26.3"
                y="22.9"
                width="3.4"
                height="4.2"
                rx="1"
              />
              <circle className="ai-pet__lamp-glow" cx="28" cy="25" r="3.6" />
              <circle className="ai-pet__lamp" cx="28" cy="25" r="1.9" />
              <circle className="ai-pet__lamp-core" cx="28" cy="24.6" r="0.8" />
            </g>
            <g data-testid="ai-pet-dots" className="ai-pet__badge">
              <rect className="ai-pet__badge-pill" x="12.6" y="24.3" width="10" height="3.4" rx="1.7" />
              <circle className="ai-pet__dot" cx="15.2" cy="26" r="0.8" />
              <circle className="ai-pet__dot" cx="17.6" cy="26" r="0.8" />
              <circle className="ai-pet__dot" cx="20" cy="26" r="0.8" />
            </g>
          </svg>
        </span>
      </span>
    </span>
  );
}
