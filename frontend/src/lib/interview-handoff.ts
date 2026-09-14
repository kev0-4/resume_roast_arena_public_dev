// Hands the /start response from the setup page to the live page.
//
// Why not just refetch it on the live page? The ephemeral Gemini token is
// minted with uses=1 and cannot be re-issued for the same interview, so
// there is exactly one chance to carry it across the navigation. It also
// must not go in the URL, where it would land in history and server logs.
//
// sessionStorage (not localStorage) so it dies with the tab.

import type { InterviewStartResponse } from "./interview-api";

const KEY_PREFIX = "interview-start:";

// Payloads already taken out of sessionStorage during this page's life.
//
// This exists because the read is destructive AND is made from an effect,
// and React double-invokes effects in development. The first call consumed
// the entry and the second got nothing back, so every interview opened
// straight into "this interview room has closed" -- a bug that only
// appeared in dev, which is exactly where the feature gets used most.
//
// Caching makes the read idempotent for as long as the module is alive.
// A real reload re-evaluates the module AND finds sessionStorage already
// emptied, so a genuinely stale room still reports itself closed.
const taken = new Map<string, InterviewStartResponse>();

export function stashInterviewStart(start: InterviewStartResponse): void {
  try {
    sessionStorage.setItem(KEY_PREFIX + start.interview_id, JSON.stringify(start));
  } catch {
    // Private mode or a full quota. The live page will report the missing
    // handoff rather than silently failing to connect.
  }
}

export function takeInterviewStart(interviewId: string): InterviewStartResponse | null {
  const cached = taken.get(interviewId);
  if (cached) return cached;

  try {
    const raw = sessionStorage.getItem(KEY_PREFIX + interviewId);
    if (!raw) return null;
    sessionStorage.removeItem(KEY_PREFIX + interviewId);
    const parsed = JSON.parse(raw) as InterviewStartResponse;
    taken.set(interviewId, parsed);
    return parsed;
  } catch {
    return null;
  }
}
