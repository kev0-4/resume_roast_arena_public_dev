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

export async function ingestResume(file: File): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const resp = await fetch(`${API_BASE_URL}/api/v1/ingest`, {
    method: "POST",
    body: formData,
    headers: { "X-Idempotency-Key": getIdempotencyKey() },
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
