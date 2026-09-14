"use client";

// The answering surfaces for the four exercise formats, plus the problem
// panel that sits beside them.
//
// They share one visual language deliberately: same panel chrome, same
// header treatment, same inner padding. An MCQ round and a SQL round should
// feel like two views of one product, not two products.

import { motion } from "framer-motion";
import { ChevronLeft, Database, FileText } from "lucide-react";
import type { McqQuestion, RoundQuestion, SqlTable } from "@/lib/interview-api";

/** Shared panel shell. One definition so the panes cannot drift apart. */
export function Panel({
  title,
  icon,
  action,
  children,
  className = "",
}: {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    // h-full, not content height: these sit in stretch-aligned flex tracks
    // and without it every panel shrank to its text and left the rest of
    // the screen empty.
    <div
      className={`flex h-full min-h-0 flex-col overflow-hidden rounded-[1.25rem] border-[3px] border-black bg-white shadow-[5px_5px_0_#000] ${className}`}
    >
      <div className="flex shrink-0 items-center justify-between gap-3 border-b-[3px] border-black px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          {icon}
          <p className="truncate font-mono text-[10px] font-black uppercase tracking-wider text-black/55">{title}</p>
        </div>
        {action}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}

export function ProblemPanel({
  question,
  onCollapse,
}: {
  question: RoundQuestion;
  onCollapse: () => void;
}) {
  return (
    <Panel
      title={`${question.format === "SQL" ? "The query" : "The problem"} · ${question.difficulty}`}
      icon={<FileText size={13} strokeWidth={2.5} className="shrink-0 text-black/40" />}
      action={
        <button
          onClick={onCollapse}
          aria-label="Collapse the problem"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-black bg-white transition-colors hover:bg-black/5"
        >
          <ChevronLeft size={12} strokeWidth={3} />
        </button>
      }
    >
      <div className="px-4 py-4">
        <p className="whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-black/80">{question.prompt}</p>

        {question.schema ? <SchemaBlock tables={question.schema} /> : null}

        {question.examples?.length ? (
          <div className="mt-5 flex flex-col gap-3">
            {question.examples.map((example, index) => (
              <div key={index} className="rounded-xl border-2 border-black/12 bg-black/[0.025] p-3">
                <p className="mb-2 font-mono text-[9px] font-black uppercase tracking-wider text-black/45">
                  Example {index + 1}
                </p>
                <ExampleRow label="Input" value={example.input} />
                <ExampleRow label="Output" value={example.output} accent />
                {example.explanation ? (
                  <p className="mt-2 font-mono text-[11.5px] leading-relaxed text-black/55">
                    {example.explanation}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        {question.constraints?.length ? (
          <div className="mt-5">
            <p className="mb-1.5 font-mono text-[9px] font-black uppercase tracking-wider text-black/45">
              Constraints
            </p>
            <ul className="flex flex-col gap-1">
              {question.constraints.map((constraint, index) => (
                <li key={index} className="flex gap-2 font-mono text-[11.5px] leading-snug text-black/60">
                  <span className="text-black/25">&bull;</span>
                  {constraint}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap gap-1.5">
          {question.topics.map((topic) => (
            <span
              key={topic}
              className="rounded-full border border-black/15 bg-black/[0.03] px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide text-black/45"
            >
              {topic}
            </span>
          ))}
        </div>
      </div>
    </Panel>
  );
}

/** Input/output on a worked example. Pre-wrapped because multi-line
 *  examples (a sequence of calls, a table) are the norm, not the exception. */
function ExampleRow({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="mb-1.5 last:mb-0">
      <span className="font-mono text-[10px] font-bold uppercase tracking-wide text-black/35">{label}</span>
      <pre
        className={[
          "mt-0.5 overflow-x-auto whitespace-pre-wrap break-words rounded-lg px-2 py-1.5 font-mono text-[11.5px] leading-snug",
          accent ? "bg-brand-lime/20 text-black" : "bg-white text-black/75",
        ].join(" ")}
      >
        {value}
      </pre>
    </div>
  );
}

/** The schema a SQL question is unanswerable without. */
function SchemaBlock({ tables }: { tables: SqlTable[] }) {
  return (
    <div className="mt-5 rounded-xl border-2 border-black/12 bg-brand-blue/[0.03] p-3">
      <p className="mb-2.5 flex items-center gap-1.5 font-mono text-[9px] font-black uppercase tracking-wider text-black/45">
        <Database size={11} strokeWidth={2.5} />
        Schema
      </p>
      <div className="flex flex-col gap-3">
        {tables.map((table) => (
          <div key={table.table}>
            <p className="font-mono text-[11px] font-bold text-brand-blue">{table.table}</p>
            <ul className="mt-1 flex flex-col gap-0.5 pl-3">
              {table.columns.map((column) => (
                <li key={column} className="font-mono text-[11px] text-black/60">
                  {column}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

export function WrittenPane({
  value,
  onChange,
  onPaste,
  disabled,
}: {
  value: string;
  onChange: (next: string) => void;
  onPaste: () => void;
  disabled?: boolean;
}) {
  const words = value.trim() ? value.trim().split(/\s+/).length : 0;
  return (
    <div className="flex h-full flex-col">
      <textarea
        id="written-answer"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onPaste={onPaste}
        disabled={disabled}
        placeholder="Structure your answer. The reasoning matters more than the conclusion."
        className="min-h-0 flex-1 resize-none bg-transparent px-4 py-4 font-mono text-[13px] leading-relaxed text-black outline-none placeholder:text-black/25 disabled:opacity-60"
      />
      <div className="shrink-0 border-t border-black/10 px-4 py-2 text-right">
        <span className="font-mono text-[10px] font-semibold tabular-nums text-black/35">{words} words</span>
      </div>
    </div>
  );
}

export function McqPane({
  questions,
  answers,
  onAnswer,
  disabled,
}: {
  questions: McqQuestion[];
  answers: (number | null)[];
  onAnswer: (questionIndex: number, optionIndex: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-5 px-4 py-4">
      {questions.map((question, qi) => (
        <fieldset key={qi} className="border-0 p-0" disabled={disabled}>
          <legend className="mb-2.5 flex gap-2 font-mono text-[13px] font-semibold leading-snug text-black">
            <span className="shrink-0 tabular-nums text-black/30">{String(qi + 1).padStart(2, "0")}</span>
            <span>{question.prompt}</span>
          </legend>
          <div className="flex flex-col gap-1.5 pl-7">
            {question.options.map((option, oi) => {
              const checked = answers[qi] === oi;
              return (
                <label
                  key={oi}
                  className={[
                    "flex cursor-pointer items-start gap-2.5 rounded-xl border-2 px-3 py-2 transition-colors",
                    checked
                      ? "border-black bg-brand-lime/25"
                      : "border-black/10 bg-white hover:border-black/30 hover:bg-black/[0.02]",
                  ].join(" ")}
                >
                  <input
                    id={`mcq-${qi}-${oi}`}
                    type="radio"
                    name={`mcq-${qi}`}
                    checked={checked}
                    onChange={() => onAnswer(qi, oi)}
                    className="mt-[3px] h-3.5 w-3.5 shrink-0 accent-black"
                  />
                  <span className="font-mono text-[12.5px] leading-snug text-black/80">{option}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

/** Slim tab shown where the problem panel was, once it's collapsed. */
export function CollapsedProblemTab({ onExpand }: { onExpand: () => void }) {
  return (
    <motion.button
      layout
      onClick={onExpand}
      aria-label="Show the problem"
      className="flex w-11 shrink-0 flex-col items-center gap-3 rounded-[1.25rem] border-[3px] border-black bg-white py-4 shadow-[5px_5px_0_#000] transition-colors hover:bg-black/[0.03]"
    >
      <FileText size={14} strokeWidth={2.5} className="text-black/45" />
      <span
        className="font-mono text-[10px] font-black uppercase tracking-wider text-black/45"
        style={{ writingMode: "vertical-rl" }}
      >
        Problem
      </span>
    </motion.button>
  );
}
