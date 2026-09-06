import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { ArrowDarkDown } from "@/components/landing/accents";

const STEPS = [
  {
    n: 1,
    title: "Drop your resume",
    body: "PDF, DOCX, PNG, or JPEG, up to 10MB. No account needed to start -- sign in later if you want it on the leaderboard under your name.",
    image: "/how-it-works/step-1-upload.png",
  },
  {
    n: 2,
    title: "It actually gets read",
    body: "A real pipeline runs your resume through extraction, anonymization, a deterministic rule engine, and an LLM roast -- seven real stages, tracked live, not a fake progress bar.",
    image: "/how-it-works/step-2-processing.png",
  },
  {
    n: 3,
    title: "Get scored, not just insulted",
    body: "A real 0-100 score, a tier stamp, your live rank against every other roast, and a roast that's actually grounded in your resume's real text -- not generic filler.",
    image: "/how-it-works/step-3-score.png",
  },
  {
    n: 4,
    title: "Climb the board",
    body: "Every scored roast is rankable on the public leaderboard. Beat someone's score, take their spot.",
    image: "/how-it-works/step-4-leaderboard.png",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <div className="relative z-10">
        <Navbar />

        <main className="mx-auto flex w-full max-w-3xl flex-col items-center gap-4 px-4 pb-20">
          <div className="flex flex-col items-center pt-4 text-center">
            <h1 className="font-display text-[clamp(2.2rem,6vw,3.4rem)] uppercase leading-[0.95] tracking-tighter text-white">
              How it <span className="text-brand-lime">works</span>
            </h1>
            <p className="mt-2 max-w-md font-mono text-xs text-white/60 md:text-sm">
              Four real steps, real screenshots, no smoke.
            </p>
          </div>

          {STEPS.map((step, i) => (
            <div key={step.n} className="flex w-full flex-col items-center">
              <div className="w-full overflow-hidden rounded-2xl border-[3px] border-black bg-white shadow-[5px_5px_0_#000]">
                <div className="relative w-full bg-brand-blue-deep">
                  <Image
                    src={step.image}
                    alt={step.title}
                    width={900}
                    height={520}
                    className="h-auto w-full"
                    unoptimized
                  />
                </div>
                <div className="flex items-start gap-4 p-5 md:p-6">
                  <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border-2 border-black bg-brand-lime font-display text-sm text-black">
                    {step.n}
                  </span>
                  <div>
                    <h2 className="font-display text-lg uppercase tracking-tight text-black md:text-xl">{step.title}</h2>
                    <p className="mt-1 font-mono text-sm text-black/60">{step.body}</p>
                  </div>
                </div>
              </div>

              {i < STEPS.length - 1 && (
                <div className="my-2 h-12 w-12 text-white/40">
                  <ArrowDarkDown />
                </div>
              )}
            </div>
          ))}

          <div className="mt-8 flex flex-col items-center gap-4 text-center">
            <Link
              href="/roast"
              className="flex items-center gap-2 rounded-full border-2 border-black bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
            >
              Roast your resume
              <ArrowRight size={18} strokeWidth={2.5} />
            </Link>
            <p className="font-mono text-xs text-white/50">
              Not convinced?{" "}
              <Link href="/leaderboard" className="text-brand-lime underline underline-offset-2">
                Browse real roasts on the leaderboard
              </Link>
              .
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
