// Hand-drawn accent SVGs + the spinning CTA badge for the landing hero.
// Colored to match the reference component's own palette (brand blue +
// lime), the user's explicit preference over the roast card's ember/ash
// scheme -- see globals.css for the note on that divergence.

export const ArrowAccentLeft = () => (
  <svg
    viewBox="0 0 100 100"
    className="h-full w-full overflow-visible stroke-brand-lime"
    fill="none"
    strokeWidth="6"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M10,90 C 10,40 40,20 60,50 C 70,65 80,75 95,70" />
    <path d="M80,55 L95,70 L85,85" />
  </svg>
);

export const ArrowAccentRight = () => (
  <svg
    viewBox="0 0 100 100"
    className="h-full w-full overflow-visible stroke-brand-lime"
    fill="none"
    strokeWidth="6"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M90,10 C 80,60 60,80 40,60 C 20,40 40,20 60,30 C 80,40 70,70 50,80" />
    <path d="M65,75 L50,80 L55,65" />
  </svg>
);

export const ArrowDark = () => (
  <svg
    viewBox="0 0 100 100"
    className="h-full w-full overflow-visible stroke-black"
    fill="none"
    strokeWidth="5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M20,80 Q 40,20 80,40" />
    <path d="M60,20 L80,40 L50,60" />
  </svg>
);

export const ArrowDarkDown = () => (
  <svg
    viewBox="0 0 100 100"
    className="h-full w-full overflow-visible stroke-black"
    fill="none"
    strokeWidth="5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M50,10 Q 60,50 45,80" />
    <path d="M25,65 L45,80 L60,60" />
  </svg>
);

export const SpinningRoastBadge = () => (
  <div className="relative h-28 w-28 rotate-12 cursor-pointer rounded-full border-[3px] border-black/5 bg-brand-lime shadow-xl transition-transform hover:scale-105 md:h-36 md:w-36">
    <div className="absolute inset-1 animate-[spin_10s_linear_infinite]">
      <svg viewBox="0 0 100 100" className="h-full w-full">
        <path
          id="badgeCirclePath"
          d="M 50, 50 m -36, 0 a 36,36 0 1,1 72,0 a 36,36 0 1,1 -72,0"
          fill="none"
        />
        <text
          className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]"
          fill="black"
        >
          <textPath href="#badgeCirclePath" startOffset="0%">
            UPLOAD YOUR RESUME • GET ROASTED •{" "}
          </textPath>
        </text>
      </svg>
    </div>
    <div className="absolute inset-0 flex items-center justify-center">
      <svg
        viewBox="0 0 100 100"
        className="h-10 w-10 overflow-visible stroke-black"
        fill="none"
        strokeWidth="8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M20,80 Q 40,50 30,30 T 80,20" />
        <path d="M60,10 L80,20 L70,40" />
      </svg>
    </div>
  </div>
);
