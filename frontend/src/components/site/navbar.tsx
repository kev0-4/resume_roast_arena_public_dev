import Link from "next/link";
import { AuthMenu } from "./auth-menu";

const NAV_LINKS = [
  { label: "Leaderboard", href: "/leaderboard" },
  { label: "How it works", href: "/how-it-works" },
];

// Shared across every page -- same nav links everywhere rather than each
// page inventing its own subset, so the site reads as one product.
export function Navbar() {
  return (
    <nav className="relative z-20 mx-auto flex w-full max-w-[1440px] items-center justify-between px-6 py-6 md:px-10 md:py-8">
      <div className="flex items-center gap-1">
        {/* Brand half -- home. */}
        <Link
          href="/"
          className="rounded-2xl rounded-bl-sm bg-white px-3 py-1.5 font-display text-xs tracking-tight text-black shadow-sm transition-transform hover:-translate-y-0.5 md:text-sm"
        >
          RESUME
        </Link>
        {/* Was visually a second half of the same logo but read as its own
            dead button -- now a real CTA straight to the upload page. */}
        <Link
          href="/roast"
          className="rounded-full border-[1.5px] border-white bg-brand-lime px-3 py-1.5 font-display text-xs tracking-tight text-black shadow-sm transition-transform hover:-translate-y-0.5 md:text-sm"
        >
          ROAST
        </Link>
      </div>

      <div className="hidden items-center space-x-2 md:flex">
        {NAV_LINKS.map((item) => (
          <Link
            key={item.label}
            href={item.href}
            className="rounded-full border border-white/30 px-4 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-white/10"
          >
            {item.label}
          </Link>
        ))}
      </div>

      <AuthMenu />
    </nav>
  );
}
