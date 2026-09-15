"use client";

// Dev-only mock render of the exercise round UI, for reproducing and
// fixing layout bugs (mobile, narrow viewports) without needing a real
// interview -- no auth, no Live API, no backend call at all. Renders the
// REAL RoundStage component with a realistic mock question, so the CSS
// under test is exactly what production ships.
//
// Gated on NODE_ENV, same pattern as the other dev-only pages/hooks in
// this codebase (firebase.ts's __TEST_AUTH__, use-live-interview.ts's
// __TEST_LIVE__, dev-runtime-check's __TEST_RUNTIME__).

import { useState } from "react";
import { RoundStage } from "@/components/interview/round-stage";
import { InterviewerPresence } from "@/components/interview/interviewer-presence";
import { TranscriptPane } from "@/components/interview/transcript-pane";
import type { RoundQuestion } from "@/lib/interview-api";

const MOCK_QUESTION: RoundQuestion = {
  id: "merge-intervals",
  format: "CODE",
  difficulty: "easy",
  topics: ["sorting", "arrays", "greedy"],
  minutes: 10,
  prompt:
    "You are given an array of intervals where intervals[i] = [start_i, end_i].\n\n" +
    "Merge all overlapping intervals and return an array of the non-overlapping intervals " +
    "that cover all the intervals in the input, sorted by start.\n\n" +
    "Two intervals overlap if they share any point, INCLUDING touching at the boundary: " +
    "[1, 4] and [4, 5] overlap and must merge into [1, 5]. The input is not guaranteed to be sorted.",
  examples: [
    {
      input: "intervals = [[1,3],[2,6],[8,10],[15,18]]",
      output: "[[1,6],[8,10],[15,18]]",
      explanation: "[1,3] and [2,6] overlap, so they merge into [1,6]. The rest are disjoint.",
    },
    {
      input: "intervals = [[1,4],[4,5]]",
      output: "[[1,5]]",
      explanation: "They only touch at 4, but touching counts as overlapping here.",
    },
  ],
  constraints: [
    "0 <= intervals.length <= 10^4",
    "intervals[i].length == 2",
    "-10^5 <= start_i <= end_i <= 10^5",
    "Return an empty list for empty input.",
  ],
  starter: {
    python: "def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:\n    pass\n",
    javascript: "function mergeIntervals(intervals) {\n}\n",
    java: "class Solution {\n    public int[][] mergeIntervals(int[][] intervals) {\n        return new int[0][];\n    }\n}\n",
    cpp: "vector<vector<int>> mergeIntervals(vector<vector<int>>& intervals) {\n}\n",
  },
  harness: {
    kind: "call",
    entry: { python: "merge_intervals", javascript: "mergeIntervals" },
    cases: [
      { name: "overlapping and disjoint", args: [[[1, 3], [2, 6], [8, 10], [15, 18]]], expected: [[1, 6], [8, 10], [15, 18]] },
      { name: "touching intervals merge", args: [[[1, 4], [4, 5]]], expected: [[1, 5]] },
    ],
  },
};

const MOCK_LINES = [
  { id: 1, speaker: "interviewer" as const, text: "Alright, let's get into the coding round. Take your time." },
  { id: 2, speaker: "candidate" as const, text: "Sounds good, I'll sort by start first." },
];

const MOCK_MCQ_QUESTION: RoundQuestion = {
  id: "mcq-frontend-fundamentals",
  format: "MCQ",
  difficulty: "medium",
  topics: ["event loop", "rendering", "browser"],
  minutes: 4,
  questions: [
    {
      prompt: "A click handler calls setTimeout(f, 0) and then Promise.resolve().then(g). Which runs first?",
      options: [
        "f, because its delay is 0",
        "g, because microtasks drain before the next macrotask",
        "Whichever was registered first",
        "They run concurrently",
      ],
    },
    {
      prompt: "Which change forces a layout (reflow) rather than only a repaint?",
      options: [
        "Changing an element's background-color",
        "Changing an element's visibility to hidden",
        "Changing an element's width",
        "Changing an element's color",
      ],
    },
  ],
};

// Flip this when checking a non-CODE format -- not wired to a query
// param on purpose: reading window.location during render would mismatch
// server vs. client output on the very first hydration pass, for a
// switch that only ever gets flipped by hand anyway.
const PREVIEW_MCQ = false;

export default function DevRoundPreviewPage() {
  const [submitting, setSubmitting] = useState(false);

  if (process.env.NODE_ENV === "production") return null;

  return (
    <div className="relative flex h-[100dvh] w-full flex-col overflow-hidden bg-brand-blue font-mono">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />
      <div className="relative z-10 mx-auto flex h-full w-full max-w-[2000px] flex-col px-4 md:px-6">
        <RoundStage
          question={PREVIEW_MCQ ? MOCK_MCQ_QUESTION : MOCK_QUESTION}
          secondsLeft={573}
          submitting={submitting}
          onSubmit={() => {
            setSubmitting(true);
            setTimeout(() => setSubmitting(false), 500);
          }}
          presence={<InterviewerPresence amplitude={() => 0} speaking={false} thinking={false} idle />}
          transcript={<TranscriptPane lines={MOCK_LINES} interim="" />}
        />
      </div>
    </div>
  );
}
