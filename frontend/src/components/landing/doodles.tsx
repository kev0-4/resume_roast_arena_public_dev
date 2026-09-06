// Extra hand-drawn background doodles for the hero -- same stroke-only
// construction as the arrows in accents.tsx (viewBox 0 0 100 100, round
// caps/joins, single accent color), themed resume/roast/funny-edgy so
// they read as part of the joke, not generic decoration.

export const FlameDoodle = () => (
  <svg
    viewBox="0 0 100 100"
    className="h-full w-full overflow-visible stroke-brand-lime"
    fill="none"
    strokeWidth="5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M50,14 C64,32 70,46 62,58 C60,50 54,47 52,52 C56,40 46,30 50,14 Z" />
    <path d="M38,40 C30,52 30,66 40,76 C55,88 72,80 74,64 C75,55 70,48 66,46 C70,58 64,68 56,70 C46,72 40,64 42,54 C43,48 40,44 38,40 Z" />
  </svg>
);

export const SkullDoodle = () => (
  <svg
    viewBox="0 0 100 100"
    className="h-full w-full overflow-visible stroke-brand-lime"
    fill="none"
    strokeWidth="5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M28,45 C28,25 38,12 50,12 C62,12 72,25 72,45 C72,55 68,60 65,64 L65,74 L60,74 L60,68 L54,68 L54,74 L46,74 L46,68 L40,68 L40,74 L35,74 L35,64 C32,60 28,55 28,45 Z" />
    <circle cx="40" cy="43" r="6" />
    <circle cx="60" cy="43" r="6" />
    <path d="M47,52 L50,58 L53,52" />
  </svg>
);

export const TrashDoodle = () => (
  <svg
    viewBox="0 0 100 100"
    className="h-full w-full overflow-visible stroke-brand-lime"
    fill="none"
    strokeWidth="5"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M46,10 C40,6 34,10 34,17 C26,17 22,26 30,32 C38,38 50,34 50,24 C50,16 50,14 46,10 Z" />
    <path d="M22,38 L78,38" />
    <path d="M35,38 L38,26 L62,26 L65,38" />
    <path d="M28,38 L34,88 L66,88 L72,38" />
    <path d="M42,50 L44,78 M50,50 L50,78 M58,50 L56,78" />
  </svg>
);
