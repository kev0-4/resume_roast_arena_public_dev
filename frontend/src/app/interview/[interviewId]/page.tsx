"use client";

import { use, useEffect, useRef, useState } from "react";
import { Navbar } from "@/components/site/navbar";
import { RecorderButton } from "@/components/interview/recorder-button";
import { ResultsSummary } from "@/components/interview/results-summary";
import { useAuth } from "@/lib/auth-context";
import {
  ApiError,
  fetchAuthedAudioUrl,
  getInterview,
  submitInterviewTurn,
  type InterviewDetail,
} from "@/lib/interview-api";

type PageParams = { params: Promise<{ interviewId: string }> };

// Client-rendered and stateful (unlike the server-rendered public /r/[slug]
// result page) -- this is a live, multi-step interaction the viewer is
// actively waiting on, not a static shareable result.
export default function InterviewPage({ params }: PageParams) {
  const { interviewId } = use(params);
  const { firebaseUser, loading: authLoading, getIdToken } = useAuth();

  const [loading, setLoading] = useState(true);
  const [interview, setInterview] = useState<InterviewDetail | null>(null);
  const [currentTurnNumber, setCurrentTurnNumber] = useState(0);
  const [questionText, setQuestionText] = useState("");
  const [reactionText, setReactionText] = useState<string | null>(null);
  const [questionAudioUrl, setQuestionAudioUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [finalScore, setFinalScore] = useState<{
    score: number;
    strengths: string[];
    weaknesses: string[];
    nextSteps: string[];
  } | null>(null);

  const currentAudioObjectUrlRef = useRef<string | null>(null);

  const loadAudio = async (relativePath: string, idToken: string) => {
    setAudioLoading(true);
    try {
      const objectUrl = await fetchAuthedAudioUrl(relativePath, idToken);
      // Revoke the previous object URL before swapping in the new one --
      // a multi-turn interview would otherwise leak one per turn.
      if (currentAudioObjectUrlRef.current) URL.revokeObjectURL(currentAudioObjectUrlRef.current);
      currentAudioObjectUrlRef.current = objectUrl;
      setQuestionAudioUrl(objectUrl);
    } catch {
      // Non-fatal -- the question text is still readable without audio.
      setQuestionAudioUrl(null);
    } finally {
      setAudioLoading(false);
    }
  };

  useEffect(() => {
    // Revoke on unmount regardless of which effect/handler created it.
    return () => {
      if (currentAudioObjectUrlRef.current) URL.revokeObjectURL(currentAudioObjectUrlRef.current);
    };
  }, []);

  useEffect(() => {
    if (authLoading || !firebaseUser) return;
    let cancelled = false;
    (async () => {
      try {
        const idToken = await getIdToken();
        if (!idToken) {
          setError("You need to be signed in to view this interview.");
          return;
        }
        const data = await getInterview(interviewId, idToken);
        if (cancelled) return;
        setInterview(data);

        if (data.status !== "IN_PROGRESS") {
          setDone(true);
          if (data.score !== undefined) {
            setFinalScore({
              score: data.score,
              strengths: data.strengths ?? [],
              weaknesses: data.weaknesses ?? [],
              nextSteps: data.next_steps ?? [],
            });
          }
          return;
        }

        setCurrentTurnNumber(data.turn_count);
        const currentEntry = data.transcript.find((t) => t.turn === data.turn_count);
        if (currentEntry) {
          setQuestionText(currentEntry.question_text);
          await loadAudio(currentEntry.question_audio_url, idToken);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load this interview.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- interviewId/getIdToken/firebaseUser stable enough for this one-time hydration
  }, [interviewId, authLoading, firebaseUser]);

  const handleAnswer = async (blob: Blob, mimeType: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const idToken = await getIdToken();
      if (!idToken) {
        setError("You need to be signed in to continue.");
        setSubmitting(false);
        return;
      }
      const extension = mimeType.includes("mp4") ? "mp4" : "webm";
      const response = await submitInterviewTurn(interviewId, currentTurnNumber, blob, `answer.${extension}`, idToken);

      setReactionText(response.reaction_text);

      if (response.is_final) {
        setDone(true);
        if (response.score !== undefined) {
          setFinalScore({
            score: response.score,
            strengths: response.strengths ?? [],
            weaknesses: response.weaknesses ?? [],
            nextSteps: response.next_steps ?? [],
          });
        }
        await loadAudio(response.response_audio_url, idToken);
      } else {
        setQuestionText(response.next_question);
        setCurrentTurnNumber(response.turn_number + 1);
        await loadAudio(response.response_audio_url, idToken);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Server's turn_count moved from under us -- re-fetch and
        // reconcile rather than blindly retrying.
        setError("Lost sync with the interview -- reloading current state.");
        try {
          const idToken = await getIdToken();
          if (idToken) {
            const data = await getInterview(interviewId, idToken);
            setInterview(data);
            setCurrentTurnNumber(data.turn_count);
            const currentEntry = data.transcript.find((t) => t.turn === data.turn_count);
            if (currentEntry) {
              setQuestionText(currentEntry.question_text);
              await loadAudio(currentEntry.question_audio_url, idToken);
            }
          }
        } catch {
          // best-effort reconciliation -- leave the error message up
        }
      } else if (err instanceof ApiError && err.status === 429) {
        const wait = err.retryAfterSeconds ? ` Try again in ${Math.ceil(err.retryAfterSeconds / 60)} min.` : "";
        setError(`You've hit the turn limit for now.${wait}`);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Something went wrong submitting your answer -- try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      <main className="relative z-10 mx-auto flex w-full max-w-2xl flex-1 flex-col items-center px-4 pb-16 pt-6 md:px-10">
        {authLoading ? (
          <div className="h-72 w-full animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
        ) : !firebaseUser ? (
          <p className="mt-16 rounded-2xl border-[3px] border-black bg-white px-6 py-8 text-center font-mono text-sm font-semibold text-black/60 shadow-[5px_5px_0_#000]">
            Sign in to view this interview.
          </p>
        ) : loading ? (
          <div className="h-72 w-full animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
        ) : done && finalScore ? (
          <div className="mt-4 w-full">
            <ResultsSummary
              score={finalScore.score}
              strengths={finalScore.strengths}
              weaknesses={finalScore.weaknesses}
              nextSteps={finalScore.nextSteps}
            />
          </div>
        ) : interview ? (
          <div className="mt-4 flex w-full flex-col items-center gap-6">
            <p className="font-mono text-xs font-black uppercase tracking-wide text-white/50">
              Turn {currentTurnNumber + 1} of {interview.max_turns}
            </p>

            <div className="w-full rounded-[1.75rem] border-[3px] border-black bg-white p-6 shadow-[6px_6px_0_#000] md:p-8">
              {reactionText && (
                <p className="mb-4 border-b border-black/10 pb-4 font-mono text-sm italic text-black/60">
                  &quot;{reactionText}&quot;
                </p>
              )}
              <p className="font-display text-xl leading-snug text-black md:text-2xl">{questionText}</p>
              {audioLoading ? (
                <p className="mt-4 font-mono text-xs text-black/40">Loading audio...</p>
              ) : questionAudioUrl ? (
                <audio controls src={questionAudioUrl} className="mt-4 w-full" />
              ) : null}
            </div>

            <RecorderButton disabled={submitting || audioLoading} onRecordingComplete={handleAnswer} />

            {submitting && <p className="font-mono text-xs text-white/60">Thinking of something brutal to say...</p>}
            {error && <p className="max-w-sm text-center font-mono text-xs font-semibold text-brand-lime">{error}</p>}
          </div>
        ) : (
          error && <p className="mt-16 text-center font-mono text-sm text-brand-lime">{error}</p>
        )}
      </main>
    </div>
  );
}
