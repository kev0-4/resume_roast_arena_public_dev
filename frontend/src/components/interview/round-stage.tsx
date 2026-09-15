"use client";

// The exercise round: problem on the left, answering surface in the middle,
// the interviewer and the transcript stacked on the right.
//
// Widths are deliberately asymmetric rather than three equal columns. The
// socket is CLOSED for the whole round -- there are no hints in v1 -- so the
// interviewer is silent by design, and giving a dead panel a third of the
// screen while the editor is cramped would be the wrong trade. It stays
// visible because being watched is the point of the product; it just
// doesn't hog room it isn't using.
//
// The problem panel collapses to a rail once it has been read, which is
// when people actually want editor width.

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Clipboard, Loader2, Send } from "lucide-react";
import type { CodeHarness, DryRunResult, RoundQuestion, SqlHarness } from "@/lib/interview-api";
import { CollapsedProblemTab, McqPane, Panel, ProblemPanel, WrittenPane } from "./round-panes";
import { LANGUAGE_LABELS } from "./code-editor";
import { CodeRunPanel, SqlRunPanel } from "./run-panel";
import { runCode, runtimeForFormat } from "@/lib/runners/runtime";

// CodeMirror and its grammars are several hundred KB and most interviews --
// every HR, IB and conversation-only session -- never open an editor. Keep
// it out of the bundle until a coding round actually starts.
const CodeEditor = dynamic(() => import("./code-editor").then((m) => m.CodeEditor), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center gap-2 text-black/35">
      <Loader2 size={15} className="animate-spin" />
      <span className="font-mono text-[11px] font-semibold">Loading editor…</span>
    </div>
  ),
});

function formatClock(seconds: number): string {
  const m = Math.floor(Math.max(0, seconds) / 60);
  const s = Math.max(0, seconds) % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export interface RoundStageProps {
  question: RoundQuestion;
  secondsLeft: number;
  submitting: boolean;
  onSubmit: (payload: {
    answer: string;
    mcqAnswers: number[];
    language: string | null;
    pasted: boolean;
    runs?: number;
    failedRuns?: number;
    caseOutputs?: { name: string; got: string }[];
  }) => void;
  /** The interviewer tile and transcript, passed in so the SAME elements
   *  animate across from the conversation layout rather than being rebuilt. */
  presence: React.ReactNode;
  transcript: React.ReactNode;
  /** Server-side read for languages with no browser runtime. */
  onDryRun?: (args: { answer: string; language: string }) => Promise<DryRunResult>;
}

export function RoundStage({
  question,
  secondsLeft,
  submitting,
  onSubmit,
  presence,
  transcript,
  onDryRun,
}: RoundStageProps) {
  const languages = useMemo(() => {
    if (question.format === "SQL") return ["sql"];
    return Object.keys(question.starter ?? {});
  }, [question]);

  const [language, setLanguage] = useState(() => languages[0] ?? "python");
  const [code, setCode] = useState(() => question.starter?.[languages[0] ?? "python"] ?? "");
  const [written, setWritten] = useState("");
  const [answers, setAnswers] = useState<(number | null)[]>(() =>
    (question.questions ?? []).map(() => null),
  );
  const [problemOpen, setProblemOpen] = useState(true);
  const pastedRef = useRef(false);
  // Run history. Recorded and handed to the interviewer as context, never
  // deducted from the score -- penalising failed runs would push people to
  // stop testing, which is exactly the habit this button exists to build.
  const runsRef = useRef(0);
  const failedRunsRef = useRef(0);
  const [submitPhase, setSubmitPhase] = useState<"idle" | "grading">("idle");

  // Switching language swaps in that language's starter, but never discards
  // work: only replace the buffer if it is still untouched starter code.
  const starterValues = useMemo(() => Object.values(question.starter ?? {}), [question.starter]);
  const onLanguageChange = (next: string) => {
    setLanguage(next);
    setCode((current) =>
      current.trim() === "" || starterValues.some((s) => s.trim() === current.trim())
        ? question.starter?.[next] ?? ""
        : current,
    );
  };

  const urgent = secondsLeft <= 60;

  const answered = answers.filter((a) => a !== null).length;
  const canSubmit =
    !submitting &&
    (question.format === "MCQ" ? answered > 0 : (question.format === "WRITTEN" ? written : code).trim().length > 0);

  const submit = async () => {
    const harness = question.harness as CodeHarness | undefined;
    const kind = runtimeForFormat(question.format, language);
    let caseOutputs: { name: string; got: string }[] = [];

    // On submit -- and only on submit -- every case runs, including the
    // hidden ones the candidate was never shown expected values for. The
    // server holds those values and decides what passed, so tweaking until
    // the visible tests go green buys nothing.
    if (question.format === "CODE" && harness?.cases && kind && harness.entry[language]) {
      setSubmitPhase("grading");
      try {
        const result = await runCode(kind, {
          kind: harness.kind,
          entry: harness.entry[language],
          code,
          cases: harness.cases,
        });
        caseOutputs = (result.results ?? []).map((r) => ({ name: r.name, got: r.got ?? "" }));
      } catch {
        // A failed grading run must not block submission -- the reviewer
        // reads the code either way.
      } finally {
        setSubmitPhase("idle");
      }
    }

    onSubmit({
      answer: question.format === "WRITTEN" ? written : code,
      mcqAnswers: answers.map((a) => a ?? -1),
      language: question.format === "MCQ" || question.format === "WRITTEN" ? null : language,
      pasted: pastedRef.current,
      runs: runsRef.current,
      failedRuns: failedRunsRef.current,
      caseOutputs,
    });
  };

  const markPasted = () => {
    pastedRef.current = true;
  };

  // Auto-submit at zero. This lives here rather than in the hook because
  // the answer buffer is here -- submitting from outside would post an
  // empty answer and bin everything they had written.
  //
  // It only arms once the clock has actually been seen running. Firing on
  // a zero that was never counted down to would submit an empty answer the
  // instant the round opened, which is the worst possible failure for this
  // screen.
  const autoSubmittedRef = useRef(false);
  const clockStartedRef = useRef(false);
  useEffect(() => {
    if (secondsLeft > 0) clockStartedRef.current = true;
  }, [secondsLeft]);
  useEffect(() => {
    if (!clockStartedRef.current || secondsLeft > 0 || submitting || autoSubmittedRef.current) return;
    autoSubmittedRef.current = true;
    void submit();
    // submit is recreated every render from live state; depending on it
    // would re-arm this effect constantly. secondsLeft is the real trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secondsLeft, submitting]);

  const isEditor = question.format === "CODE" || question.format === "SQL";

  return (
    <motion.div
      // Below lg the stack (problem + editor + submit + presence +
      // transcript) genuinely runs taller than a phone screen -- the old
      // fixed-and-clipped RoomShell above this had nothing scrollable in
      // between, so the excess was invisible and unreachable rather than
      // scrolled to. overflow-y-auto here is what that was missing; lg
      // reverts to the original fit-exactly-to-viewport desktop behavior,
      // where individual panels scroll internally instead.
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto py-3 lg:flex-row lg:overflow-visible"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Problem, collapsible */}
      <AnimatePresence initial={false} mode="popLayout">
        {problemOpen ? (
          <motion.div
            key="problem"
            layout
            initial={{ opacity: 0, x: -24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -24 }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            // h-[38vh], not the old min-h-[12rem]: that showed two
            // sentences of a multi-paragraph problem with no visible way
            // to see the rest was scrollable -- framer-motion's layout
            // animation on this wrapper doesn't play well with a height
            // that changes with content (see round-panes.tsx's Panel:
            // that was tried first and produced real content overlapping
            // real content), so this keeps Panel's own internal scroll
            // and just gives it enough room to be worth scrolling in.
            className="h-[38vh] shrink-0 lg:h-auto lg:min-h-0 lg:w-[28%]"
          >
            <ProblemPanel question={question} onCollapse={() => setProblemOpen(false)} />
          </motion.div>
        ) : (
          <motion.div
            key="problem-tab"
            initial={{ opacity: 0, x: -18 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -18 }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="hidden lg:flex"
          >
            <CollapsedProblemTab onExpand={() => setProblemOpen(true)} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Answering surface */}
      {/* A fixed mobile height (not flex-1) rather than competing for
          whatever's left over: CodeMirror's height="100%" needs a real,
          determinate parent height to render at all, and an editor whose
          size randomly depends on how long the problem statement happens
          to be is a worse experience than a consistent one. Desktop is
          unchanged -- lg:h-auto releases this so the row's stretch
          alignment plus lg:flex-1 (width, in a row) sizes it exactly as
          before. */}
      <motion.div layout className="flex h-[55vh] min-h-[20rem] min-w-0 shrink-0 flex-col lg:h-auto lg:min-h-0 lg:flex-1 lg:shrink">
        <Panel
          title={
            question.format === "MCQ"
              ? `Quick-fire · ${answered}/${question.questions?.length ?? 0} answered`
              : question.format === "WRITTEN"
                ? "Your answer"
                : "Your solution"
          }
          action={
            <div className="flex items-center gap-2">
              {isEditor && languages.length > 1 ? (
                <select
                  id="round-language"
                  value={language}
                  onChange={(e) => onLanguageChange(e.target.value)}
                  className="cursor-pointer rounded-full border-2 border-black bg-white px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-wide text-black outline-none"
                >
                  {languages.map((lang) => (
                    <option key={lang} value={lang}>
                      {LANGUAGE_LABELS[lang] ?? lang}
                    </option>
                  ))}
                </select>
              ) : null}
              <Clock seconds={secondsLeft} urgent={urgent} />
            </div>
          }
          // flex-1 rather than h-full here: the submit button is a sibling
          // below, so the panel takes the remaining height instead of the
          // full column.
          className={`min-h-0 flex-1 ${isEditor ? "bg-[#282c34]" : ""}`}
        >
          {question.format === "MCQ" ? (
            <McqPane
              questions={question.questions ?? []}
              answers={answers}
              disabled={submitting}
              onAnswer={(qi, oi) =>
                setAnswers((prev) => prev.map((value, index) => (index === qi ? oi : value)))
              }
            />
          ) : question.format === "WRITTEN" ? (
            <WrittenPane value={written} onChange={setWritten} onPaste={markPasted} disabled={submitting} />
          ) : (
            <div className="h-full min-h-0">
              <CodeEditor
                value={code}
                language={language}
                onChange={setCode}
                onPaste={markPasted}
                disabled={submitting}
              />
            </div>
          )}
        </Panel>

        {/* Self-check before submitting. The score still comes from the
            server's review either way -- this only spares the candidate
            submitting an answer they were never able to try. */}
        {question.harness ? (
          <div className="mt-3">
            {question.format === "SQL" ? (
              <SqlRunPanel sql={code} harness={question.harness as SqlHarness} />
            ) : question.format === "CODE" && onDryRun ? (
              <CodeRunPanel
                code={code}
                language={language}
                harness={question.harness as CodeHarness}
                onDryRun={onDryRun}
                onRunRecorded={(failed) => {
                  runsRef.current += 1;
                  if (failed) failedRunsRef.current += 1;
                }}
              />
            ) : null}
          </div>
        ) : null}

        <motion.button
          layout
          onClick={() => void submit()}
          disabled={!canSubmit}
          className={[
            "mt-3 flex shrink-0 items-center justify-center gap-2 rounded-full border-2 border-black px-7 py-3 font-display text-sm uppercase tracking-wide transition-all",
            canSubmit
              ? "bg-brand-lime text-black shadow-[4px_4px_0_#000] hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000]"
              : "cursor-not-allowed border-black/20 bg-black/10 text-black/30",
          ].join(" ")}
        >
          {submitting || submitPhase === "grading" ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              {submitPhase === "grading" ? "Running every test" : "Marking your answer"}
            </>
          ) : (
            <>
              <Send size={15} strokeWidth={2.5} />
              Submit and face the questions
            </>
          )}
        </motion.button>
      </motion.div>

      {/* Interviewer + transcript, stacked */}
      <div className="flex min-h-[16rem] shrink-0 flex-col gap-3 lg:min-h-0 lg:w-[26%]">
        <div className="relative h-[34%] min-h-[7rem] shrink-0 overflow-hidden rounded-[1.25rem] border-[3px] border-black bg-brand-blue/40 shadow-[5px_5px_0_#000]">
          {presence}
          <div className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-2 bg-black/35 py-1.5 backdrop-blur-sm">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-300" />
            <span className="font-mono text-[9px] font-black uppercase tracking-wider text-white/85">
              Waiting · watching you work
            </span>
          </div>
        </div>
        <div className="min-h-0 flex-1">{transcript}</div>
      </div>
    </motion.div>
  );
}

function Clock({ seconds, urgent }: { seconds: number; urgent: boolean }) {
  return (
    <div
      className={[
        "rounded-full border-2 px-2.5 py-1 font-mono text-[11px] font-black tabular-nums transition-colors",
        urgent ? "border-red-600 bg-red-500 text-white" : "border-black bg-white text-black",
      ].join(" ")}
      // Only the last minute pulses. A timer that throbs for twelve minutes
      // is noise; one that starts throbbing means something.
      style={urgent ? { animation: "roundPulse 1s ease-in-out infinite" } : undefined}
    >
      {formatClock(seconds)}
      <style>{`@keyframes roundPulse{0%,100%{opacity:1}50%{opacity:.55}}
        @media (prefers-reduced-motion: reduce){[style*="roundPulse"]{animation:none!important}}`}</style>
    </div>
  );
}

/** Between rounds: what they scored, and what's coming. */
export function RoundVerdict({
  score,
  strengths,
  problems,
  onContinue,
  continuing,
}: {
  score: number;
  strengths: string[];
  problems: string[];
  onContinue: () => void;
  continuing: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 28 }}
      className="mx-auto flex w-full max-w-md flex-col items-center gap-5 py-10 text-center"
    >
      <div className="flex flex-col items-center">
        <p className="font-mono text-[10px] font-black uppercase tracking-wider text-white/45">Round scored</p>
        <p className="font-display text-6xl leading-none text-brand-lime">
          {score}
          <span className="text-2xl text-white/30">/10</span>
        </p>
      </div>

      <div className="w-full rounded-[1.25rem] border-[3px] border-black bg-white p-5 text-left shadow-[5px_5px_0_#000]">
        {strengths.length > 0 ? (
          <>
            <p className="mb-1.5 font-mono text-[10px] font-black uppercase tracking-wider text-black/45">Worked</p>
            <ul className="mb-4 flex flex-col gap-1">
              {strengths.map((s, i) => (
                <li key={i} className="flex gap-2 font-mono text-[12.5px] text-black/75">
                  <Check size={13} strokeWidth={3} className="mt-0.5 shrink-0 text-brand-lime" />
                  {s}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {problems.length > 0 ? (
          <>
            <p className="mb-1.5 font-mono text-[10px] font-black uppercase tracking-wider text-black/45">Didn&apos;t</p>
            <ul className="flex flex-col gap-1">
              {problems.map((p, i) => (
                <li key={i} className="flex gap-2 font-mono text-[12.5px] text-black/75">
                  <Clipboard size={13} strokeWidth={2.5} className="mt-0.5 shrink-0 text-red-500" />
                  {p}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>

      <p className="font-mono text-[11px] text-white/45">
        The interviewer has read your answer. It&apos;s going to ask about it.
      </p>

      <button
        onClick={onContinue}
        disabled={continuing}
        className="flex items-center gap-2 rounded-full bg-brand-lime px-8 py-4 font-display text-sm uppercase tracking-wide text-black shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] disabled:opacity-60"
      >
        {continuing ? <Loader2 size={16} className="animate-spin" /> : null}
        {continuing ? "Bringing them back" : "Face the debrief"}
      </button>
    </motion.div>
  );
}
