"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Mic } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { getInterviewEligibility } from "@/lib/interview-api";

// /r/[slug] is intentionally public with zero ownership awareness (see
// backend/src/routes/interview.py's own eligibility-route docstring for
// why this is a separate authenticated check rather than adding user_id
// to the public roast-analysis response). Renders nothing at all while
// signed out or ineligible -- most viewers of a shared roast link won't
// be signed in, and this must stay invisible/silent for them, not flash
// a loading or error state on a page whose whole point is being shared.
export function InterviewCta({ slug }: { slug: string }) {
  const { firebaseUser, getIdToken } = useAuth();
  const [resumeSessionId, setResumeSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (!firebaseUser) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getIdToken();
        if (!token) return;
        const result = await getInterviewEligibility(slug, token);
        if (!cancelled && result.eligible && result.resume_session_id) {
          setResumeSessionId(result.resume_session_id);
        }
      } catch {
        // silent -- ineligibility/errors just mean no CTA, not a broken page
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [firebaseUser, getIdToken, slug]);

  if (!resumeSessionId) return null;

  return (
    <Link
      href={`/interview/new?resumeSessionId=${resumeSessionId}`}
      className="flex items-center gap-2 rounded-full bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
    >
      <Mic size={18} strokeWidth={2.5} />
      Think you can defend this resume?
      <ArrowRight size={18} strokeWidth={2.5} />
    </Link>
  );
}
