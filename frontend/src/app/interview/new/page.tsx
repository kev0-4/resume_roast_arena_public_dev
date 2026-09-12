"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { stackedShadow } from "@/lib/text-shadow";
import { useAuth } from "@/lib/auth-context";
import { ApiError, startInterview } from "@/lib/interview-api";

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
  const resumeSessionId = searchParams.get("resumeSessionId");
  const { firebaseUser, loading: authLoading, getIdToken } = useAuth();

  const [jobDescription, setJobDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const jdLength = jobDescription.trim().length;
  const jdValid = jdLength >= MIN_JD_LENGTH && jdLength <= MAX_JD_LENGTH;

  const handleSubmit = async () => {
    if (!resumeSessionId || !jdValid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const idToken = await getIdToken();
      if (!idToken) {
        setError("You need to be signed in to start an interview.");
        setSubmitting(false);
        return;
      }
      const result = await startInterview(resumeSessionId, jobDescription.trim(), idToken);
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

        {!resumeSessionId ? (
          <p className="rounded-2xl border-[3px] border-black bg-white px-6 py-8 text-center font-mono text-sm font-semibold text-black/60 shadow-[5px_5px_0_#000]">
            No resume selected -- start from your roast result page.
          </p>
        ) : authLoading ? (
          <div className="h-56 w-full animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
        ) : !firebaseUser ? (
          <p className="rounded-2xl border-[3px] border-black bg-white px-6 py-8 text-center font-mono text-sm font-semibold text-black/60 shadow-[5px_5px_0_#000]">
            Sign in first, then come back to start your interview.
          </p>
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
