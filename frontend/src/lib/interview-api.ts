// Client for the AI mock-interview backend (backend/src/routes/interview.py).
// Same ApiError/fetch conventions as lib/api.ts -- see that file for the
// established pattern this mirrors.

import { ApiError } from "./api";
export { ApiError };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface InterviewStartResponse {
  interview_id: string;
  status: string;
  turn_number: number;
  max_turns: number;
  question_text: string;
  question_audio_url: string;
}

export interface InterviewTurnResponse {
  interview_id: string;
  turn_number: number;
  reaction_text: string;
  next_question: string;
  response_audio_url: string;
  is_final: boolean;
  status: string;
  score?: number;
  strengths?: string[];
  weaknesses?: string[];
  next_steps?: string[];
}

export interface InterviewEligibility {
  eligible: boolean;
  resume_session_id?: string;
}

export interface TranscriptTurnEntry {
  turn: number;
  question_text: string;
  question_audio_url: string;
  answer_transcript: string | null;
  answer_audio_url: string | null;
  reaction_text: string | null;
}

export interface InterviewDetail {
  interview_id: string;
  status: string;
  resume_session_id: string;
  roast_slug: string | null;
  job_description: string;
  turn_count: number;
  max_turns: number;
  transcript: TranscriptTurnEntry[];
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

// turnNumber must be exactly the interview's current turn_count -- the
// backend 409s on any mismatch (optimistic-concurrency guard against a
// duplicate submit double-spending a Gemini call). Callers should re-fetch
// getInterview() and reconcile on a 409, not blindly retry.
export async function submitInterviewTurn(
  interviewId: string,
  turnNumber: number,
  audioBlob: Blob,
  audioFilename: string,
  idToken: string,
): Promise<InterviewTurnResponse> {
  const formData = new FormData();
  formData.append("turn_number", String(turnNumber));
  formData.append("file", audioBlob, audioFilename);

  const resp = await fetch(`${API_BASE_URL}/api/v1/interview/${interviewId}/turn`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}` },
    body: formData,
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not submit your answer");
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

// Every interview audio route requires the same Authorization header as
// everything else in this API -- a plain <audio src> can't send that, so
// every audio URL has to be fetched, read as a Blob, and turned into an
// object URL before anything can play it. Centralized here so the page
// doesn't repeat the fetch+blob+createObjectURL dance at every call site.
// Callers must URL.revokeObjectURL() the result when done with it (a
// multi-turn interview creates several of these) -- see interview
// page's cleanup effect.
export async function fetchAuthedAudioUrl(relativePath: string, idToken: string): Promise<string> {
  const resp = await fetch(`${API_BASE_URL}/${relativePath}`, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!resp.ok) throw await errorFromResponse(resp, "Could not load audio");
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}
