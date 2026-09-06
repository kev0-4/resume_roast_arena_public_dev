import Link from "next/link";
import { Home } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { stackedShadow } from "@/lib/text-shadow";

const HEADLINE_SHADOW = stackedShadow(10, "#001A99");

// Next.js renders this for any unmatched route site-wide -- without it,
// a bad/typo'd link falls back to Next's plain default 404, breaking the
// site's visual identity at the exact moment someone's already lost.
export default function NotFound() {
  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
      <Navbar />
      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center justify-center px-4 pb-32 text-center">
        <span className="mb-4 font-display text-sm uppercase tracking-widest text-brand-lime">404</span>
        <h1
          className="m-0 p-0 font-display text-[clamp(2.4rem,7vw,4.8rem)] uppercase leading-[0.9] tracking-tighter text-white"
          style={{ textShadow: HEADLINE_SHADOW }}
        >
          This page got roasted too
        </h1>
        <p className="mt-4 max-w-md font-mono text-sm text-white/70">
          Whatever you were looking for isn&apos;t here. Maybe it never existed, maybe it moved on.
        </p>
        <Link
          href="/"
          className="mt-8 flex items-center gap-2 rounded-full bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
        >
          <Home size={18} strokeWidth={2.5} />
          Take me home
        </Link>
      </main>
    </div>
  );
}
