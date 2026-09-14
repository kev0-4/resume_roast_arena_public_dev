"use client";

// The live interview room.
//
// This page holds a WebSocket straight to Gemini's Live API -- our backend
// is not in the audio path at all. It only minted the single-use token that
// got us here. That is the whole reason the interviewer answers in under a
// second instead of the ~92 seconds the old record-upload-wait-playback
// build took to produce its first question.

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Mic, MicOff, PhoneOff } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useLiveInterview } from "@/hooks/use-live-interview";
import { takeInterviewStart } from "@/lib/interview-handoff";
import type { InterviewStartResponse } from "@/lib/interview-api";
import { motion } from "framer-motion";
import { InterviewerPresence } from "@/components/interview/interviewer-presence";
import { TranscriptPane } from "@/components/interview/transcript-pane";
import { ResumePane } from "@/components/interview/resume-pane";
import { RoundStage, RoundVerdict } from "@/components/interview/round-stage";
import { ResultsSummary } from "@/components/interview/results-summary";

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function InterviewRoomPage({ params }: { params: Promise<{ interviewId: string }> }) {
  const { interviewId } = use(params);
  const { getIdToken } = useAuth();

  // `undefined` = not looked yet, `null` = looked and it wasn't there.
  const [start, setStart] = useState<InterviewStartResponse | null | undefined>(undefined);

  // sessionStorage only exists client-side, so this cannot be a lazy
  // useState initializer: the server prerender would read null, the client
  // would read the token, and the two renders would disagree.
  //
  // eslint's set-state-in-effect is suppressed rather than worked around,
  // because this is the case its own message carves out -- reading once
  // from an external system that React cannot see. There is nothing to
  // await here, so wrapping it in an async IIFE (this codebase's usual
  // shape for that rule) would only hide the call from the linter without
  // changing what it does.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStart(takeInterviewStart(interviewId));
  }, [interviewId]);

  const live = useLiveInterview(start ?? null, getIdToken);

  if (start === undefined) {
    return <RoomShell>{null}</RoomShell>;
  }

  // No token in the handoff: a refresh, a shared link, or a direct visit.
  // None of these are recoverable -- the token was single-use and is gone.
  if (start === null) {
    return (
      <RoomShell>
        <CenteredCard
          title="This interview room has closed"
          body="Live interviews can't be resumed or reopened -- the session credential is used once and expires. Start a fresh one and you'll be talking in a few seconds."
          action={{ href: "/interview/new", label: "Start a new interview" }}
        />
      </RoomShell>
    );
  }

  if (live.phase === "done" && live.result) {
    return (
      <RoomShell>
        <div className="mx-auto w-full max-w-2xl py-10">
          <ResultsSummary
            score={live.result.score}
            strengths={live.result.strengths}
            weaknesses={live.result.weaknesses}
            nextSteps={live.result.next_steps}
          />
        </div>
      </RoomShell>
    );
  }

  if (live.phase === "error") {
    return (
      <RoomShell>
        <CenteredCard
          title="The interview dropped"
          body={live.error ?? "Something went wrong."}
          action={{ href: "/interview/new", label: "Try again" }}
        />
      </RoomShell>
    );
  }

  if (live.phase === "ending" || live.phase === "scoring") {
    return (
      <RoomShell>
        <div className="flex flex-col items-center gap-4 py-24 text-center">
          <Loader2 size={32} className="animate-spin text-brand-lime" />
          <p className="font-display text-2xl uppercase tracking-tight text-white">
            {live.endedByInterviewer ? "The interviewer ended it" : live.phase === "ending" ? "Wrapping up" : "Scoring your answers"}
          </p>
          {/* Attribute the ending honestly. Being cut off without being told
              why reads as a crash rather than a decision the interviewer made. */}
          {live.endedByInterviewer?.reason ? (
            <p className="max-w-sm font-mono text-xs italic text-brand-lime/80">
              &ldquo;{live.endedByInterviewer.reason}&rdquo;
            </p>
          ) : null}
          <p className="max-w-sm font-mono text-xs text-white/50">
            Reading back everything you said and grading it against the job description.
          </p>
        </div>
      </RoomShell>
    );
  }

  // Green room, exactly like Meet's pre-join: nothing connects and no audio
  // context opens until this click. Browsers require a user gesture before
  // audio can play at all, so an auto-connect would leave the interviewer
  // talking into a muted tab.
  if (live.phase === "greenroom") {
    return (
      <RoomShell>
        <CenteredCard
          title="Ready when you are"
          body="Put headphones on -- without them the interviewer hears itself through your mic and talks over its own questions. It speaks first, so just answer out loud, and you can cut it off mid-sentence. If you're stuck you can ask to move on, though it'll push back once and skipping counts against your score. It can also end the interview early if you waste its time."
          onAction={() => void live.connect()}
          actionLabel="Join the interview"
        />
      </RoomShell>
    );
  }

  // The handoff: the interviewer has said what's coming and the screen is
  // about to change. A beat of explanation beats a hard cut.
  if (live.phase === "handoff") {
    return (
      <RoomShell>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-1 flex-col items-center justify-center gap-5 text-center"
        >
          <motion.div
            layoutId="interviewer-presence"
            className="flex h-24 w-24 items-center justify-center rounded-full border-[3px] border-black bg-brand-lime shadow-[5px_5px_0_#000]"
          >
            <span className="font-display text-3xl uppercase tracking-tighter text-black">RR</span>
          </motion.div>
          {live.handoffLine ? (
            <p className="max-w-md font-mono text-sm italic text-brand-lime/90">&ldquo;{live.handoffLine}&rdquo;</p>
          ) : null}
          <div className="flex items-center gap-2 font-mono text-[11px] font-semibold text-white/50">
            <Loader2 size={13} className="animate-spin" />
            Setting up your workspace
          </div>
        </motion.div>
      </RoomShell>
    );
  }

  if (live.phase === "exercise" && live.round) {
    return (
      <RoomShell wide>
        <RoundStage
          question={live.round.question}
          secondsLeft={live.roundSecondsLeft}
          submitting={live.submittingRound}
          onSubmit={live.submitRound}
          presence={
            <InterviewerPresence amplitude={live.amplitude} speaking={false} thinking={false} idle />
          }
          transcript={<TranscriptPane lines={live.lines} interim="" />}
        />
      </RoomShell>
    );
  }

  if (live.phase === "round-verdict" && live.roundResult) {
    return (
      <RoomShell>
        <RoundVerdict
          score={live.roundResult.score}
          strengths={live.roundResult.strengths}
          problems={live.roundResult.problems}
          continuing={false}
          onContinue={() => void live.continueToDebrief()}
        />
      </RoomShell>
    );
  }

  const connecting = live.phase === "connecting";

  return (
    <RoomShell>
      <div className="flex min-h-0 flex-1 flex-col gap-4 py-4 lg:flex-row">
        {/* Stage */}
        <div className="relative flex min-h-[18rem] flex-1 items-center justify-center rounded-[1.5rem] border-[3px] border-black bg-brand-blue/40 shadow-[6px_6px_0_#000] lg:min-h-0">
          {connecting ? (
            <div className="flex flex-col items-center gap-3">
              <Loader2 size={28} className="animate-spin text-brand-lime" />
              <p className="font-mono text-xs font-semibold text-white/60">Connecting...</p>
            </div>
          ) : (
            <InterviewerPresence
              amplitude={live.amplitude}
              speaking={live.speaking}
              thinking={!live.speaking && !live.muted}
            />
          )}

          {/* The number this whole rebuild exists to move. Shown, not
              buried in a console log, because it is the feature. */}
          {live.firstAudioMs !== null ? (
            <div className="absolute right-4 top-4 rounded-full border-2 border-black bg-white px-3 py-1 shadow-[3px_3px_0_#000]">
              <span className="font-mono text-[10px] font-black uppercase tracking-wide text-black">
                {(live.firstAudioMs / 1000).toFixed(1)}s to first word
              </span>
            </div>
          ) : null}

          {/* Visible running cost of asking to move on, so the penalty is
              never a surprise that only shows up in the final score. */}
          {live.skippedCount > 0 ? (
            <div className="absolute left-4 top-4 rounded-full border-2 border-black bg-red-500 px-3 py-1 shadow-[3px_3px_0_#000]">
              <span className="font-mono text-[10px] font-black uppercase tracking-wide text-white">
                {live.skippedCount} skipped
              </span>
            </div>
          ) : null}

          {!connecting ? <ResumePane resumeText={start.resume_text} /> : null}
        </div>

        {/* Transcript rail */}
        <div className="h-[20rem] shrink-0 lg:h-auto lg:w-[22rem]">
          <TranscriptPane lines={live.lines} interim={live.interim} />
        </div>
      </div>

      {/* Control bar */}
      <div className="flex shrink-0 items-center justify-center gap-3 pb-6 pt-2">
        <div className="rounded-full border-2 border-black bg-white px-4 py-2.5 shadow-[3px_3px_0_#000]">
          <span
            className={[
              "font-mono text-xs font-black tabular-nums",
              live.secondsLeft !== null && live.secondsLeft <= 60 ? "text-red-600" : "text-black",
            ].join(" ")}
          >
            {live.secondsLeft === null ? "--:--" : formatClock(live.secondsLeft)}
          </span>
        </div>

        <button
          onClick={live.toggleMute}
          disabled={connecting}
          aria-label={live.muted ? "Unmute microphone" : "Mute microphone"}
          className={[
            "flex h-12 w-12 items-center justify-center rounded-full border-2 border-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[2px_2px_0_#000] disabled:opacity-40",
            live.muted ? "bg-red-500 text-white" : "bg-white text-black",
          ].join(" ")}
        >
          {live.muted ? <MicOff size={18} strokeWidth={2.5} /> : <Mic size={18} strokeWidth={2.5} />}
        </button>

        <button
          onClick={() => void live.end()}
          className="flex items-center gap-2 rounded-full border-2 border-black bg-red-500 px-6 py-3 font-display text-sm uppercase tracking-wide text-white shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[2px_2px_0_#000]"
        >
          <PhoneOff size={16} strokeWidth={2.5} />
          End
        </button>
      </div>
    </RoomShell>
  );
}

// Deliberately no Navbar: this is a call, and a nav rail full of exits is
// the wrong shape for one. Matches Meet, which hides its own chrome too.
function RoomShell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="relative flex h-[100dvh] w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
      {/* A conversation reads better in a column; an IDE does not. The
          exercise round gets close to the full viewport, because a 28%
          problem panel inside a 1152px box is a column of six words. */}
      <div
        className={[
          "relative z-10 mx-auto flex h-full w-full flex-col px-4",
          wide ? "max-w-[2000px] md:px-6" : "max-w-6xl md:px-8",
        ].join(" ")}
      >
        {children}
      </div>
    </div>
  );
}

function CenteredCard({
  title,
  body,
  action,
  onAction,
  actionLabel,
}: {
  title: string;
  body: string;
  action?: { href: string; label: string };
  onAction?: () => void;
  actionLabel?: string;
}) {
  const buttonClass =
    "mt-6 inline-flex items-center justify-center gap-2 rounded-full bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000]";

  return (
    <div className="flex flex-1 items-center justify-center py-10">
      <div className="w-full max-w-md rounded-[1.75rem] border-[3px] border-black bg-white p-8 text-center shadow-[6px_6px_0_#000]">
        <h1 className="font-display text-3xl uppercase leading-none tracking-tighter text-black">{title}</h1>
        <p className="mt-4 font-mono text-xs leading-relaxed text-black/60">{body}</p>
        {action ? (
          <Link href={action.href} className={buttonClass}>
            {action.label}
          </Link>
        ) : null}
        {onAction ? (
          <button onClick={onAction} className={buttonClass}>
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
