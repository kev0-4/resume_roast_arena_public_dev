// Thin client for the FastAPI backend. Base URL is env-configurable
// (NEXT_PUBLIC_API_BASE_URL, see .env.example) since the frontend and
// backend are deployed separately -- defaults to the local dev backend
// (backend/app.py runs uvicorn on :8000).

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type SessionStatus =
  | "UPLOADED"
  | "QUEUED"
  | "PROCESSING"
  | "EXTRACTED"
  | "NORMALIZING"
  | "NORMALIZED"
  | "ANONYMIZING"
  | "ANONYMIZED"
  | "SCORING"
  | "SCORED"
  | "ROASTING"
  | "ROASTED"
  | "RENDERING"
  | "DONE"
  | "FAILED";

export interface IngestResponse {
  session_id: string;
  status: SessionStatus;
  links: { session: string };
}

export interface SessionStatusResponse {
  session_id: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  slug: string | null;
  error_code: string | null;
  error_message: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Kept in one place (a real browser tab id, not a random UUID per
// request) so a retried/duplicate submit within the session dedupes on
// the backend's idempotency-key handling (backend/src/routes/injest.py)
// instead of creating a second session every time.
function getIdempotencyKey(): string {
  const STORAGE_KEY = "rra_idempotency_key";
  if (typeof window === "undefined") return crypto.randomUUID();
  let key = window.sessionStorage.getItem(STORAGE_KEY);
  if (!key) {
    key = crypto.randomUUID();
    window.sessionStorage.setItem(STORAGE_KEY, key);
  }
  return key;
}

export async function ingestResume(file: File, idToken?: string | null): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = { "X-Idempotency-Key": getIdempotencyKey() };
  if (idToken) headers["Authorization"] = `Bearer ${idToken}`;

  const resp = await fetch(`${API_BASE_URL}/api/v1/ingest`, {
    method: "POST",
    body: formData,
    headers,
  });

  if (resp.status === 429) {
    const retryAfter = resp.headers.get("Retry-After");
    throw new ApiError(
      "You've hit the upload limit -- try again soon.",
      429,
      retryAfter ? Number(retryAfter) : undefined,
    );
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(body.detail ?? "Upload failed", resp.status);
  }

  return resp.json();
}

export async function getSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/sessions/${sessionId}`);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(body.detail ?? "Could not fetch session status", resp.status);
  }
  return resp.json();
}

export interface BackendUser {
  id: string;
  firebase_uid: string;
  display_name: string | null;
  email: string | null;
  photo_url: string | null;
  role: string;
  is_anonymous: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

// Called once right after Firebase sign-in with the real ID token. Not
// strictly required before other authenticated-optional routes work --
// /ingest resolves the backend user itself from any valid Bearer token
// (backend/src/dependencies/auth.py get_current_user_optional) -- but
// calling this immediately serves two real purposes: it's an early check
// that the token actually verifies against the backend's Firebase project
// (surfaces a credential/project mismatch right away, not silently on
// the next upload), and it hands back real profile info (display name,
// photo) for the UI without waiting for that next request.
export async function syncFirebaseAuth(idToken: string): Promise<BackendUser> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/auth/firebase`, {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(body.detail ?? "Could not sync auth with backend", resp.status);
  }
  const data = await resp.json();
  return data.user;
}

// The public roast-card PNG lives on the backend itself (GET /r/{slug}).
export function publicRoastCardUrl(slug: string): string {
  return `${API_BASE_URL}/r/${slug}`;
}

export interface ScoreSummary {
  total_issues: number;
  critical_issues: number;
  high_issues: number;
  medium_issues: number;
  low_issues: number;
  total_strengths: number;
}

export interface Highlight {
  quote: string;
  comment: string;
}

export interface RoastAnalysis {
  slug: string;
  composite_score: number;
  stamp: string;
  created_at: string;
  rank: number;
  total_ranked: number;
  summary: ScoreSummary;
  metrics: Record<string, number | string | null>;
  // Per-category 0-100 scores (Structure, Contact & Links, Experience,
  // Clarity, Conciseness, Skills) for the radar chart -- real deductions
  // from this session's own rule-engine issues, not invented numbers.
  // See backend/src/routes/public.py:_compute_subscores.
  subscores: Record<string, number>;
  verdict: string;
  roast: string;
  fixes: string[];
  highlights: Highlight[];
}

// Backend companion to the PNG above (GET /r/{slug}/data) -- the full
// analysis behind the card. `cache: "no-store"` here is about Next's own
// fetch cache, a separate layer from the backend response's own
// Cache-Control (backend/src/routes/public.py) -- explicit no-store keeps
// the two from being confusing to reason about together.
export async function getRoastAnalysis(slug: string): Promise<RoastAnalysis> {
  const resp = await fetch(`${API_BASE_URL}/r/${slug}/data`, { cache: "no-store" });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(body.detail ?? "Could not fetch roast analysis", resp.status);
  }
  return resp.json();
}

export interface LeaderboardEntry {
  rank: number;
  slug: string;
  display_name: string;
  composite_score: number;
  // Older rows predate the `stamp` column (backend/src/db/sessions.py) --
  // never backfilled, so this is genuinely nullable, not just optional.
  stamp: string | null;
  created_at: string;
}

export interface LeaderboardResponse {
  total: number;
  limit: number;
  offset: number;
  entries: LeaderboardEntry[];
}

export async function getLeaderboard(limit: number, offset: number): Promise<LeaderboardResponse> {
  const resp = await fetch(`${API_BASE_URL}/leaderboard?limit=${limit}&offset=${offset}`, {
    cache: "no-store",
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(body.detail ?? "Could not fetch leaderboard", resp.status);
  }
  return resp.json();
}

export interface MyLeaderboardPosition {
  rank: number;
  total: number;
  slug: string;
  composite_score: number;
  stamp: string | null;
  created_at: string;
}

// Null (not an error) means the signed-in user just has no eligible roast
// yet -- GET /leaderboard/me returns 200+null for that, see
// backend/src/routes/leaderboard.py.
export async function getMyLeaderboardPosition(idToken: string): Promise<MyLeaderboardPosition | null> {
  const resp = await fetch(`${API_BASE_URL}/leaderboard/me`, {
    headers: { Authorization: `Bearer ${idToken}` },
    cache: "no-store",
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(body.detail ?? "Could not fetch your leaderboard position", resp.status);
  }
  return resp.json();
}
