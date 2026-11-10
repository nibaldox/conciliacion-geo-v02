interface ChatPetProps {
  streaming?: boolean;
}

/**
 * Circular mascot face for the floating chat launcher: miner helmet
 * with a pulsing headlamp, blinking eyes and a small smile. Pure
 * SVG/CSS — geometry lives here, animation in globals.css.
 */
export function ChatPet({ streaming = false }: ChatPetProps) {
  return (
    <span className={streaming ? 'ai-pet ai-pet--working' : 'ai-pet'} aria-hidden="true">
      <span className="ai-pet__tilt">
        <span className="ai-pet__body">
          <svg data-testid="ai-chat-pet" aria-hidden="true" viewBox="0 0 56 56" className="ai-pet__svg">
            <g data-testid="ai-pet-helmet">
              <path className="ai-pet__helmet-dome" d="M12 24a16 16 0 0 1 32 0Z" />
              <rect className="ai-pet__helmet-brim" x="9" y="22.5" width="38" height="4" rx="2" />
            </g>
            <circle className="ai-pet__lamp-halo" cx="28" cy="14" r="5.5" />
            <circle className="ai-pet__lamp" cx="28" cy="14" r="2.4" />
            <g className="ai-pet__eyes" data-testid="ai-pet-eyes">
              <ellipse className="ai-pet__eye" cx="20" cy="33.5" rx="5" ry="6" />
              <ellipse className="ai-pet__eye" cx="36" cy="33.5" rx="5" ry="6" />
              <ellipse className="ai-pet__pupil" cx="21.5" cy="34.5" rx="2.3" ry="2.9" />
              <ellipse className="ai-pet__pupil" cx="34.5" cy="34.5" rx="2.3" ry="2.9" />
            </g>
            <path
              className="ai-pet__mouth"
              data-testid="ai-pet-mouth"
              d="M23.5 42.5q4.5 4 9 0"
              fill="none"
            />
          </svg>
        </span>
      </span>
    </span>
  );
}
