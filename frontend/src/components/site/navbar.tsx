"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { AuthMenu } from "./auth-menu";

const NAV_LINKS = [
  { label: "Leaderboard", href: "/leaderboard" },
  { label: "Interview Arena", href: "/interview-leaderboard" },
  { label: "How it works", href: "/how-it-works" },
];

// Shared across every page -- same nav links everywhere rather than each
// page inventing its own subset, so the site reads as one product.
export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mobileOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMobileOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [mobileOpen]);

  return (
    <nav className="relative z-20 mx-auto flex w-full max-w-[1440px] items-center justify-between px-6 py-6 md:px-10 md:py-8">
      <div className="flex items-center gap-2">
        {/* Wordmark, not a button -- was styled as a same-weight pill next
            to the real ROAST CTA and read as a second dead button. Plain
            text (still a real link home) makes the one actual button in
            this pair unambiguous. */}
        <Link
          href="/"
          className="font-display text-xs tracking-tight text-white/90 transition-colors hover:text-white md:text-sm"
        >
          RESUME
        </Link>
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

      <div className="flex items-center gap-2">
        {/* Below md, NAV_LINKS above is just `hidden` with no other way to
            reach Leaderboard/How it works -- this toggle is the mobile
            equivalent, same bordered-pill language as the rest of the nav. */}
        <div className="relative md:hidden" ref={menuRef}>
          <button
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Toggle navigation menu"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-white/30 text-white transition-colors hover:bg-white/10"
          >
            {mobileOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
          {mobileOpen && (
            <div className="absolute right-0 top-full z-30 mt-2 flex w-48 flex-col gap-1 rounded-2xl border border-black/10 bg-white p-2 shadow-xl">
              {NAV_LINKS.map((item) => (
                <Link
                  key={item.label}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className="rounded-xl px-3 py-2 text-sm font-semibold text-brand-blue transition-colors hover:bg-brand-blue/10"
                >
                  {item.label}
                </Link>
              ))}
            </div>
          )}
        </div>

        <AuthMenu />
      </div>
    </nav>
  );
}
