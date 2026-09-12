// Hands the /start response from the setup page to the live page.
//
// Why not just refetch it on the live page? The ephemeral Gemini token is
// minted with uses=1 and cannot be re-issued for the same interview, so
// there is exactly one chance to carry it across the navigation. It also
// must not go in the URL, where it would land in history and server logs.
//
// sessionStorage (not localStorage) so it dies with the tab, and the entry
// is consumed on read -- a stale token left lying around is just a
// confusing error on the next visit.

import type { InterviewStartResponse } from "./interview-api";

const KEY_PREFIX = "interview-start:";

export function stashInterviewStart(start: InterviewStartResponse): void {
  try {
    sessionStorage.setItem(KEY_PREFIX + start.interview_id, JSON.stringify(start));
  } catch {
    // Private mode or a full quota. The live page will report the missing
    // handoff rather than silently failing to connect.
  }
}

export function takeInterviewStart(interviewId: string): InterviewStartResponse | null {
  try {
    const raw = sessionStorage.getItem(KEY_PREFIX + interviewId);
    if (!raw) return null;
    sessionStorage.removeItem(KEY_PREFIX + interviewId);
    return JSON.parse(raw) as InterviewStartResponse;
  } catch {
    return null;
  }
}
