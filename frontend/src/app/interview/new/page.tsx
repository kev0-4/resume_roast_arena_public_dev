"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight, FileText } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { stackedShadow } from "@/lib/text-shadow";
import { useAuth } from "@/lib/auth-context";
import { ApiError, startInterview } from "@/lib/interview-api";
import { getMySessions, type MySession } from "@/lib/api";

const HEADLINE_SHADOW = stackedShadow(10, "#001A99");
const MIN_JD_LENGTH = 20;
const MAX_JD_LENGTH = 6000;

// Wrapped in Suspense -- useSearchParams() requires it even in a fully
// client-rendered page, matching this Next.js version's own build
// requirement (confirmed via `npm run build`, not assumed).
export default function NewInterviewPage() {
  return (
    <Suspense fallback={null}>
      <NewInterviewForm />
    </Suspense>
  );
}

function NewInterviewForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { firebaseUser, loading: authLoading, getIdToken } = useAuth();

  // A resumeSessionId in the URL means they arrived from their own roast
  // result page's CTA. Arriving with nothing (navbar, homepage, the arena
  // page) is equally valid, so this page picks the roast itself rather
  // than dead-ending -- that dead end was the whole reason the feature
  // looked like it had no entry point.
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    searchParams.get("resumeSessionId"),
  );

  const [roasts, setRoasts] = useState<MySession[] | null>(null);
  const [roastsError, setRoastsError] = useState<string | null>(null);
  const [jobDescription, setJobDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsPicker = !selectedSessionId && !!firebaseUser;

  // Async IIFE inside the effect, with every setState after an await --
  // the shape app/interview-leaderboard/page.tsx already uses and that
  // passes react-hooks/set-state-in-effect. Calling a useCallback'd
  // loader directly from the effect body trips that rule instead, which
  // is the same lint error this codebase's result page hit before.
  useEffect(() => {
    if (!needsPicker || roasts !== null) return;
    (async () => {
      try {
        const idToken = await getIdToken();
        if (!idToken) return;
        // Only DONE roasts are interviewable -- the interviewer needs the
        // finished anonymized resume + roast artifacts as context, which
        // don't exist until the pipeline completes.
        const data = await getMySessions(idToken, 100, 0);
        setRoasts(data.sessions.filter((s) => s.status === "DONE"));
      } catch {
        setRoastsError("Could not load your roasts.");
        setRoasts([]);
      }
    })();
  }, [needsPicker, roasts, getIdToken]);

  const jdLength = jobDescription.trim().length;
  const jdValid = jdLength >= MIN_JD_LENGTH && jdLength <= MAX_JD_LENGTH;

  const handleSubmit = async () => {
    if (!selectedSessionId || !jdValid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const idToken = await getIdToken();
      if (!idToken) {
        setError("You need to be signed in to start an interview.");
        setSubmitting(false);
        return;
      }
      const result = await startInterview(selectedSessionId, jobDescription.trim(), idToken);
      router.push(`/interview/${result.interview_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        const wait = err.retryAfterSeconds ? ` Try again in ${Math.ceil(err.retryAfterSeconds / 60)} min.` : "";
        setError(`You've hit the interview limit.${wait}`);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Something went wrong -- try again.");
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      <main className="relative z-10 mx-auto flex w-full max-w-2xl flex-1 flex-col items-center px-4 pb-16 pt-4 md:px-10">
        <div className="mb-8 mt-4 flex w-full flex-col items-center text-center">
          <h1
            className="m-0 p-0 font-display text-[clamp(2rem,6vw,3.6rem)] uppercase leading-[0.9] tracking-tighter text-white"
            style={{ textShadow: HEADLINE_SHADOW }}
          >
            Think you can defend it?
          </h1>
          <h1
            className="m-0 mt-1 p-0 font-display text-[clamp(2rem,6vw,3.6rem)] uppercase leading-[0.9] tracking-tighter text-brand-lime"
            style={{ textShadow: HEADLINE_SHADOW }}
          >
            Prove it.
          </h1>
          <p className="mt-4 max-w-md font-mono text-xs text-white/60 md:text-sm">
            Paste the job description you&apos;re chasing. The interviewer already read your roast -- expect follow-ups on
            exactly what it called out.
          </p>
        </div>

        {authLoading ? (
          <div className="h-56 w-full animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
        ) : !firebaseUser ? (
          <p className="rounded-2xl border-[3px] border-black bg-white px-6 py-8 text-center font-mono text-sm font-semibold text-black/60 shadow-[5px_5px_0_#000]">
            Sign in first, then come back to start your interview.
          </p>
        ) : needsPicker ? (
          <div className="w-full rounded-[1.75rem] border-[3px] border-black bg-white p-6 shadow-[6px_6px_0_#000] md:p-8">
            <p className="mb-4 font-mono text-xs font-black uppercase tracking-wide text-black/50">
              Pick a roast to defend
            </p>

            {roasts === null ? (
              <div className="space-y-2">
                <div className="h-14 animate-pulse rounded-2xl bg-black/5" />
                <div className="h-14 animate-pulse rounded-2xl bg-black/5" />
              </div>
            ) : roasts.length === 0 ? (
              <div className="py-4 text-center">
                <p className="font-mono text-sm font-semibold text-black/60">
                  {roastsError ?? "You don't have a finished roast yet."}
                </p>
                <Link
                  href="/roast"
                  className="mt-5 inline-flex items-center gap-2 rounded-full bg-brand-lime px-7 py-3 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000]"
                >
                  Get roasted first
                  <ArrowRight size={18} strokeWidth={2.5} />
                </Link>
              </div>
            ) : (
              <ul className="space-y-2">
                {roasts.map((roast) => (
                  <li key={roast.session_id}>
                    <button
                      onClick={() => setSelectedSessionId(roast.session_id)}
                      className="flex w-full items-center gap-3 rounded-2xl border-2 border-black/10 px-4 py-3 text-left transition-colors hover:border-black/40 hover:bg-brand-blue/[0.03]"
                    >
                      <FileText size={18} strokeWidth={2.5} className="shrink-0 text-black/40" />
                      <span className="flex-1 font-mono text-sm font-semibold text-black">
                        {roast.composite_score !== null ? `${roast.composite_score}/100` : "Roast"}
                        {roast.stamp ? <span className="ml-2 text-black/40">{roast.stamp}</span> : null}
                      </span>
                      <span className="font-mono text-[10px] font-semibold text-black/35">
                        {new Date(roast.created_at).toLocaleDateString()}
                      </span>
                      <ArrowRight size={16} strokeWidth={2.5} className="shrink-0 text-black/30" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div className="w-full rounded-[1.75rem] border-[3px] border-black bg-white p-6 shadow-[6px_6px_0_#000] md:p-8">
            <label className="mb-2 block font-mono text-xs font-black uppercase tracking-wide text-black/50">
              Job description
            </label>
            <textarea
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              disabled={submitting}
              rows={10}
              maxLength={MAX_JD_LENGTH}
              placeholder="Paste the full job description here..."
              className="w-full resize-none rounded-2xl border-2 border-black/15 bg-brand-blue/[0.02] p-4 font-mono text-sm text-black placeholder:text-black/30 focus:border-black/40 focus:outline-none disabled:opacity-60"
            />
            <div className="mt-1.5 flex items-center justify-between font-mono text-[10px] font-semibold text-black/35">
              <span>{jdLength < MIN_JD_LENGTH ? `${MIN_JD_LENGTH - jdLength} more characters needed` : "Looks good"}</span>
              <span>
                {jdLength}/{MAX_JD_LENGTH}
              </span>
            </div>

            <button
              disabled={!jdValid || submitting}
              onClick={handleSubmit}
              className={[
                "mt-6 flex w-full items-center justify-center gap-2 rounded-full px-8 py-4 font-display text-sm uppercase tracking-wide transition-all md:text-base",
                jdValid && !submitting
                  ? "bg-brand-lime text-black shadow-[4px_4px_0_#000] hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000]"
                  : "cursor-not-allowed bg-black/10 text-black/30",
              ].join(" ")}
            >
              {submitting ? "Setting up..." : "Start the interview"}
              <ArrowRight size={18} strokeWidth={2.5} />
            </button>

            {error && <p className="mt-4 text-center font-mono text-xs font-semibold text-red-600">{error}</p>}
          </div>
        )}
      </main>
    </div>
  );
}
