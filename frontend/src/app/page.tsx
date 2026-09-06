"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowAccentLeft, ArrowAccentRight, ArrowDark, SpinningRoastBadge } from "@/components/landing/accents";
import { ExampleRoastCard } from "@/components/landing/example-card";
import { Navbar } from "@/components/site/navbar";
import { stackedShadow } from "@/lib/text-shadow";

const HEADLINE_SHADOW = stackedShadow(14, "#001A99");

export default function Home() {
  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      {/* faint grid backdrop */}
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      {/* Hero */}
      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center justify-center px-4 pb-32 pt-8 md:pb-48 md:pt-12">
        <div className="relative mx-auto mb-16 mt-4 flex w-full max-w-5xl flex-col items-center justify-center text-center">
          <div className="relative z-10 flex w-full flex-col items-center space-y-2 md:space-y-4">
            <div className="relative z-30 flex w-full justify-start pl-[8%] md:pl-[20%]">
              <h1
                className="m-0 p-0 font-display text-[clamp(4rem,11vw,140px)] uppercase leading-[0.85] tracking-tighter text-brand-lime"
                style={{ textShadow: HEADLINE_SHADOW }}
              >
                GET
              </h1>
            </div>

            <div className="relative z-20 flex w-full justify-center">
              <h1
                className="m-0 p-0 font-display text-[clamp(5rem,15vw,220px)] uppercase leading-[0.85] tracking-tighter text-white"
                style={{ textShadow: HEADLINE_SHADOW }}
              >
                ROASTED
              </h1>
            </div>

            <div className="relative z-10 flex w-full justify-start pl-[12%] md:pl-[26%]">
              <h1
                className="m-0 p-0 font-display text-[clamp(3.5rem,9vw,120px)] uppercase leading-[0.85] tracking-tighter text-white"
                style={{ textShadow: HEADLINE_SHADOW }}
              >
                FOR FREE
              </h1>
            </div>
          </div>

          <div className="pointer-events-none absolute inset-0 h-full w-full">
            <motion.div
              animate={{ y: [0, -15, 0] }}
              transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
              className="pointer-events-auto absolute bottom-[8%] left-[2%] z-30 rotate-[-10deg] transition-transform duration-500 hover:rotate-0 md:left-[16%]"
            >
              <ExampleRoastCard name="OverqualifiedGoblin6248" score={91} stamp="SOLID" />
            </motion.div>

            <motion.div
              animate={{ y: [0, -20, 0] }}
              transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", delay: 1 }}
              className="pointer-events-auto absolute right-[2%] top-[10%] z-30 rotate-[10deg] transition-transform duration-500 hover:rotate-0 md:right-[18%]"
            >
              <ExampleRoastCard name="UnhingedRecruiter2116" score={64} stamp="MID" />
            </motion.div>

            <div className="absolute bottom-[0%] left-[0%] z-20 h-24 w-24 md:left-[8%] md:h-32 md:w-32">
              <ArrowAccentLeft />
            </div>
            <div className="absolute right-[0%] top-[2%] z-20 h-24 w-24 md:right-[8%] md:h-32 md:w-32">
              <ArrowAccentRight />
            </div>

            <Link
              href="/roast"
              className="pointer-events-auto absolute bottom-[-8%] right-[2%] z-40 block md:right-[14%]"
            >
              <SpinningRoastBadge />
            </Link>
          </div>
        </div>

        <p className="relative z-10 max-w-xl px-4 text-center font-mono text-sm text-white/80 md:text-base">
          Upload your resume. An AI roasts it, ruthlessly and anonymously, then hands
          you a real score and the fixes that actually matter.
        </p>
      </main>

      {/* Bottom feature section */}
      <section className="relative z-20 mt-auto w-full rounded-t-[2.5rem] bg-white px-6 py-12 text-black shadow-[0_-20px_50px_rgba(0,0,0,0.2)] md:rounded-t-[3.5rem] md:px-10 md:py-16">
        <div className="mx-auto grid max-w-6xl grid-cols-1 gap-6 md:grid-cols-3 md:gap-8">
          <div className="relative flex h-64 flex-col items-center border border-black/5 bg-paper p-8 text-center rounded-[2rem]">
            <h3 className="mb-2 font-display text-xl uppercase leading-tight md:text-2xl">
              100% Anonymous
            </h3>
            <p className="mb-auto font-mono text-[11px] font-semibold text-smoke md:text-xs">
              names, contacts and identifiers are redacted before anything gets scored
            </p>
            <div className="mt-6 flex items-center gap-2 rounded-2xl bg-brand-blue px-4 py-2.5 text-white shadow-lg">
              <span className="font-mono text-[10px] font-bold">redacted@[EMAIL]</span>
            </div>
            <div className="absolute -right-12 bottom-8 hidden h-16 w-16 md:block">
              <ArrowDark />
            </div>
          </div>

          <div className="relative flex h-64 flex-col items-center border border-black/5 bg-paper p-8 text-center rounded-[2rem]">
            <h3 className="mb-2 font-display text-xl uppercase leading-tight md:text-2xl">
              Real, Ruthless Feedback
            </h3>
            <p className="mb-auto font-mono text-[11px] font-semibold text-smoke md:text-xs">
              a real 0-100 score plus the exact issues dragging it down
            </p>
            <div className="relative mt-6 flex items-center gap-2 rounded-full bg-brand-blue p-1.5 text-white shadow-lg">
              <div className="rounded-full bg-white/10 px-4 py-2 font-display text-sm">62</div>
              <div className="px-4 font-mono text-xs font-bold">/100</div>
              <div className="absolute -bottom-6 right-1/3 z-20 rotate-12 rounded-full bg-brand-lime p-2.5 shadow-lg">
                <svg viewBox="0 0 24 24" className="h-4 w-4 stroke-black" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M7 17L17 7M17 7H7M17 7V17" />
                </svg>
              </div>
            </div>
            <div className="absolute -right-12 bottom-8 hidden h-16 w-16 md:block">
              <ArrowDark />
            </div>
          </div>

          <div className="flex h-64 flex-col items-center border border-black/5 bg-paper p-8 text-center rounded-[2rem]">
            <h3 className="mb-2 font-display text-xl uppercase leading-tight md:text-2xl">
              Share Your Roast
            </h3>
            <p className="mb-auto font-mono text-[11px] font-semibold text-smoke md:text-xs">
              every roast gets a real, shareable card and a leaderboard spot
            </p>
            <div className="relative mt-6 w-full max-w-[200px] rounded-[2rem] bg-brand-lime px-6 py-4 text-black shadow-lg">
              <p className="mb-1 font-mono text-[9px] font-bold uppercase tracking-wider">rank</p>
              <p className="font-display text-xl">#1 of 56</p>
              <div className="absolute -bottom-2 left-8 h-5 w-5 rotate-45 bg-brand-lime" />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
