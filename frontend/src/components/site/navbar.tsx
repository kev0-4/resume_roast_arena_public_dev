import Link from "next/link";
import { AuthMenu } from "./auth-menu";

const NAV_LINKS = [
  { label: "Leaderboard", href: "/leaderboard" },
  { label: "How it works", href: "#" },
  { label: "Examples", href: "#" },
];

// Shared across every page -- same nav links everywhere rather than each
// page inventing its own subset, so the site reads as one product.
export function Navbar() {
  return (
    <nav className="relative z-20 mx-auto flex w-full max-w-[1440px] items-center justify-between px-6 py-6 md:px-10 md:py-8">
      <Link href="/" className="flex items-center gap-1">
        <div className="rounded-2xl rounded-bl-sm bg-white px-3 py-1.5 font-display text-xs tracking-tight text-black shadow-sm md:text-sm">
          RESUME
        </div>
        <div className="rounded-full border-[1.5px] border-white bg-brand-lime px-3 py-1.5 font-display text-xs tracking-tight text-black shadow-sm md:text-sm">
          ROAST
        </div>
      </Link>

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
