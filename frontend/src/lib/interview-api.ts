// Client for the AI mock-interview backend (backend/src/routes/interview.py).
// Same ApiError/fetch conventions as lib/api.ts -- see that file for the
// established pattern this mirrors.

import { ApiError } from "./api";
export { ApiError };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface InterviewStartResponse {
  interview_id: string;
  /** Single-use ephemeral Gemini token. Never an API key -- see the backend's
   *  minting route. Cannot be re-minted for the same interview, which is why
   *  a refresh of the live page can't resume a session. */
  token: string;
  model: string;
  /** Persona + resume + roast + JD context, built server-side and passed
   *  straight through as the Live session's systemInstruction. */
  system_instruction: string;
  /** Tool declarations (end_interview, skip_question), passed through to
   *  the connect config. The authoritative copy is pinned in the token. */
  tools: unknown[];
  /** The anonymized resume, for the in-room reference pane. Never the
   *  roast -- that would hand over the list of weak spots in advance. */
  resume_text: string;
  /** The planned shape of the interview, so the rounds are never a
   *  mid-session surprise. Empty for interviews that predate planning. */
  agenda: AgendaItem[];
  /** ISO8601 -- when the session must end. Drives the countdown. */
  expires_at: string;
}

export type RoundFormat = "CODE" | "SQL" | "MCQ" | "WRITTEN";

/** One line of the agenda shown before the candidate joins. */
export interface AgendaItem {
  label: string;
  detail: string;
  minutes: number;
}

export interface SqlTable {
  table: string;
  columns: string[];
}

export interface McqQuestion {
  prompt: string;
  options: string[];
}

export interface CodeCase {
  name?: string;
  /** Hidden cases arrive WITHOUT `expected` -- the server keeps it. */
  hidden?: boolean;
  args?: unknown[];
  construct?: unknown[];
  ops?: [string, unknown[]][];
  expected: unknown;
}

/** Test cases for a CODE question. `entry` is per-language because the
 *  starters are idiomatic per language (merge_intervals vs mergeIntervals). */
export interface CodeHarness {
  kind: "call" | "ops";
  entry: Record<string, string>;
  cases: CodeCase[];
}

/** Everything needed to run a SQL answer in the candidate's own browser. */
export interface SqlHarness {
  setup: string[];
  verify: string;
  expected: unknown[][];
  /** The candidate's statement is a SELECT, so wrap it as a view first. */
  wrap_candidate_as_view?: boolean;
}

export interface WorkedExample {
  input: string;
  output: string;
  explanation?: string;
}

/** A question as the candidate may see it -- the answer key and rubric are
 *  stripped server-side and never reach the browser. */
export interface RoundQuestion {
  id: string;
  format: RoundFormat;
  difficulty: string;
  topics: string[];
  minutes: number;
  prompt?: string;
  examples?: WorkedExample[];
  constraints?: string[];
  starter?: Record<string, string>;
  schema?: SqlTable[];
  harness?: SqlHarness | CodeHarness;
  questions?: McqQuestion[];
}

export interface DryRunResult {
  looks_correct: boolean;
  summary: string;
  problems: string[];
}

/** "Run" for Java and C/C++: a server-side READ of the code, never an
 *  execution. Presented as an assessment, never as a test result. */
export async function dryRunRound(
  interviewId: string,
  index: number,
  idToken: string,
  body: { answer: string; language: string },
): Promise<DryRunResult> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/round/${index}/dry-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not check that code");
  return resp.json();
}

export interface InterviewRound {
  index: number;
  minutes: number;
  question: RoundQuestion;
}

export interface McqAnswerDetail {
  prompt: string;
  given: number | null;
  answer: number;
  correct: boolean;
  why: string;
}

export interface RoundResult {
  index: number;
  score: number;
  strengths: string[];
  problems: string[];
  mcq_detail?: McqAnswerDetail[] | null;
  next_round_kind?: string | null;
  next_round_index?: number | null;
}

export async function getInterviewRound(
  interviewId: string,
  index: number,
  idToken: string,
): Promise<InterviewRound> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/round/${index}`, {
    headers: { Authorization: `Bearer ${idToken}` },
    cache: "no-store",
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not load this round");
  return resp.json();
}

/** Leaves a conversation round. Driven by the interviewer's begin_round tool. */
export async function advanceInterviewRound(interviewId: string, idToken: string): Promise<RoundResult> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/advance`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
    body: JSON.stringify({}),
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not move to the next round");
  return resp.json();
}

export async function submitInterviewRound(
  interviewId: string,
  index: number,
  idToken: string,
  body: {
    answer?: string;
    mcq_answers?: number[];
    language?: string | null;
    seconds_taken: number;
    pasted: boolean;
    runs?: number;
    failed_runs?: number;
    /** What their code produced per case, including hidden ones whose
     *  expected values the browser was never given. */
    case_outputs?: { name: string; got: string }[];
  },
): Promise<RoundResult> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/round/${index}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not submit this round");
  return resp.json();
}

/** Re-opens voice after an exercise, re-seeded with everything that happened. */
export async function mintVoiceToken(interviewId: string, idToken: string): Promise<InterviewStartResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/voice-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
    body: JSON.stringify({}),
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not bring the interviewer back");
  return resp.json();
}

/** Reported at /complete, from the interviewer's own tool calls. */
export interface InterviewConduct {
  skipped_questions: number;
  ended_early?: { reason: string; category: string };
}

export type TranscriptSpeaker = "interviewer" | "candidate";

export interface TranscriptChunk {
  seq: number;
  speaker: TranscriptSpeaker;
  text: string;
  is_final: boolean;
  at: string;
}

export interface InterviewScoreResult {
  interview_id: string;
  status: string;
  score: number;
  strengths: string[];
  weaknesses: string[];
  next_steps: string[];
}

export interface InterviewEligibility {
  eligible: boolean;
  resume_session_id?: string;
}

export interface TranscriptEntry {
  seq: number;
  speaker: TranscriptSpeaker;
  text: string;
  at: string;
}

export interface InterviewDetail {
  interview_id: string;
  status: string;
  resume_session_id: string;
  roast_slug: string | null;
  job_description: string;
  transcript: TranscriptEntry[];
  score?: number;
  strengths?: string[];
  weaknesses?: string[];
  next_steps?: string[];
  started_at: string;
  completed_at: string | null;
}

export interface InterviewLeaderboardEntry {
  rank: number;
  display_name: string;
  score: number;
  completed_at: string;
}

export interface InterviewLeaderboardResponse {
  total: number;
  limit: number;
  offset: number;
  entries: InterviewLeaderboardEntry[];
}

export interface MyInterviewLeaderboardPosition {
  rank: number;
  total: number;
  score: number;
  completed_at: string;
}

/** "3 days", "5 hours", "20 minutes" -- the interview cap is weekly, so a
 *  countdown in minutes would read as five figures and tell nobody
 *  anything. Rounds up: promising sooner than reality is worse. */
export function formatRetryAfter(seconds: number): string {
  const days = Math.ceil(seconds / 86400);
  if (seconds >= 86400) return `${days} day${days === 1 ? "" : "s"}`;
  const hours = Math.ceil(seconds / 3600);
  if (seconds >= 3600) return `${hours} hour${hours === 1 ? "" : "s"}`;
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}

async function errorFromResponse(resp: Response, fallback: string): Promise<ApiError> {
  if (resp.status === 429) {
    const retryAfter = resp.headers.get("Retry-After");
    return new ApiError("You've hit the interview limit -- try again soon.", 429, retryAfter ? Number(retryAfter) : undefined);
  }
  const body = await resp.json().catch(() => ({ detail: resp.statusText }));
  return new ApiError(body.detail ?? fallback, resp.status);
}

export async function startInterview(
  resumeSessionId: string,
  jobDescription: string,
  idToken: string,
): Promise<InterviewStartResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
    },
    body: JSON.stringify({ resume_session_id: resumeSessionId, job_description: jobDescription }),
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not start the interview");
  return resp.json();
}

// The browser talks straight to Gemini, so the transcript originates
// client-side. It is streamed up here as it arrives rather than posted in
// one lump at the end: a closed tab then can't lose the whole interview,
// and scoring always runs server-side off the server's own copy.
//
// Trust boundary, stated plainly: this is NOT tamper-proof. A determined
// client could stream invented text. The server can prove a session was
// *authorised* (it minted the token) but not what was actually said. That
// matches the roast leaderboard's existing trust model, where the score
// comes from a resume the user fully controls. A backend WebSocket relay
// is the genuinely server-authoritative fix, at the cost of the latency
// this whole design exists to win.
export async function postTranscriptChunks(
  interviewId: string,
  chunks: TranscriptChunk[],
  idToken: string,
  clientDiag?: Record<string, unknown>,
): Promise<{ accepted: number; total_chunks: number }> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/transcript`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
    body: JSON.stringify({ chunks, client_diag: clientDiag ?? null }),
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not save the transcript");
  return resp.json();
}

// Idempotent server-side: calling it on an already-completed interview
// returns the existing score rather than paying for a second scoring call.
export async function completeInterview(
  interviewId: string,
  idToken: string,
  conduct: InterviewConduct = { skipped_questions: 0 },
): Promise<InterviewScoreResult> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${idToken}` },
    body: JSON.stringify(conduct),
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not score the interview");
  return resp.json();
}

export async function getInterviewEligibility(slug: string, idToken: string): Promise<InterviewEligibility> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/eligibility?slug=${encodeURIComponent(slug)}`, {
    headers: { Authorization: `Bearer ${idToken}` },
    cache: "no-store",
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not check interview eligibility");
  return resp.json();
}

export async function getInterview(interviewId: string, idToken: string): Promise<InterviewDetail> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}`, {
    headers: { Authorization: `Bearer ${idToken}` },
    cache: "no-store",
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not load the interview");
  return resp.json();
}

export async function getInterviewLeaderboard(limit: number, offset: number): Promise<InterviewLeaderboardResponse> {
  const resp = await fetch(`${API_BASE_URL}/interview-leaderboard?limit=${limit}&offset=${offset}`, {
    cache: "no-store",
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not fetch the interview leaderboard");
  return resp.json();
}

// Null (not an error) means the signed-in user has no completed interview
// yet -- GET /interview-leaderboard/me returns 200+null for that, same
// convention as GET /leaderboard/me (lib/api.ts's getMyLeaderboardPosition).
export async function getMyInterviewLeaderboardPosition(idToken: string): Promise<MyInterviewLeaderboardPosition | null> {
  const resp = await fetch(`${API_BASE_URL}/interview-leaderboard/me`, {
    headers: { Authorization: `Bearer ${idToken}` },
    cache: "no-store",
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not fetch your interview rank");
  return resp.json();
}
