"use client";

// "My Interviews" -- the profile menu had "My Roasts" (/dashboard) but
// no equivalent for the interview feature, so every past mock interview
// was invisible once its own live session ended. Deliberately lighter
// than /dashboard, not a 1:1 port of it: no score-trend chart (a handful
// of interviews, capped at one a week, doesn't make a trend worth
// charting yet the way dozens of roasts do), and rows expand in place
// instead of linking to a result page that doesn't exist for interviews.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Mic, Target, Trophy } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { ProfileHeader } from "@/components/dashboard/profile-header";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { InterviewHistoryList } from "@/components/interview/history-list";
import { useAuth } from "@/lib/auth-context";
import { ApiError, getMyInterviews, getMyInterviewLeaderboardPosition, type MyInterviewEntry, type MyInterviewLeaderboardPosition } from "@/lib/interview-api";

const PAGE_SIZE = 50;

export default function InterviewHistoryPage() {
  const { firebaseUser, backendUser, loading: authLoading, getIdToken, signOutUser } = useAuth();
  const [interviews, setInterviews] = useState<MyInterviewEntry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [rank, setRank] = useState<MyInterviewLeaderboardPosition | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(
    async (offset: number) => {
      const token = await getIdToken();
      if (!token) throw new ApiError("Not signed in", 401);
      const data = await getMyInterviews(token, PAGE_SIZE, offset);
      setInterviews((prev) => (offset === 0 ? data.interviews : [...prev, ...data.interviews]));
      setTotal(data.total);
      return token;
    },
    [getIdToken],
  );

  useEffect(() => {
    if (authLoading || !firebaseUser) return;
    (async () => {
      try {
        const token = await loadPage(0);
        const rankResult = await getMyInterviewLeaderboardPosition(token).catch(() => null);
        setRank(rankResult);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load your interviews.");
      } finally {
        setLoading(false);
      }
    })();
    // loadPage excluded for the same reason dashboard/page.tsx excludes
    // its own loadPage -- it closes over `interviews`, which would refire
    // this on every page load rather than only on auth state changing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, firebaseUser]);

  const handleLoadMore = async () => {
    setLoadingMore(true);
    try {
      await loadPage(interviews.length);
    } catch {
      // a failed "load more" leaves the existing rows intact
    } finally {
      setLoadingMore(false);
    }
  };

  const hasMore = total !== null && interviews.length < total;
  const scored = interviews.filter((i) => i.status === "COMPLETED" && i.score !== null);
  const bestScore = scored.length > 0 ? Math.max(...scored.map((i) => i.score as number)) : null;

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <div className="relative z-10">
        <Navbar />

        <main className="mx-auto flex w-full max-w-4xl flex-col gap-5 px-4 pb-16">
          {authLoading ? (
            <HistorySkeleton />
          ) : !firebaseUser ? (
            <div className="flex flex-col items-center gap-3 rounded-2xl border-[3px] border-black bg-white/90 px-6 py-10 text-center shadow-[5px_5px_0_#000]">
              <p className="font-mono text-sm font-semibold text-black/70">Sign in to see your interviews.</p>
              <Link
                href="/interview/new"
                className="rounded-full border-2 border-black bg-brand-lime px-5 py-2 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000]"
              >
                Take an interview
              </Link>
            </div>
          ) : loading ? (
            <HistorySkeleton />
          ) : error ? (
            <p className="py-16 text-center font-mono text-sm text-brand-lime">{error}</p>
          ) : (
            <>
              <ProfileHeader
                displayName={backendUser?.display_name || firebaseUser.displayName || "You"}
                createdAt={backendUser?.created_at ?? null}
                onSignOut={signOutUser}
              />

              {interviews.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-2xl border-[3px] border-black bg-brand-blue-deep px-6 py-10 text-center shadow-[5px_5px_0_#000]">
                  <p className="font-mono text-sm font-semibold text-white/70">
                    You haven&apos;t taken a mock interview yet.
                  </p>
                  <Link
                    href="/interview/new"
                    className="rounded-full border-2 border-black bg-brand-lime px-5 py-2 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000]"
                  >
                    Defend your resume
                  </Link>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-3">
                    <KpiCard icon={Trophy} label="Rank" value={rank ? `#${rank.rank}` : "--"} sub={rank ? `of ${rank.total}` : undefined} />
                    <KpiCard icon={Target} label="Best score" value={bestScore ?? "--"} sub={bestScore !== null ? "out of 10" : undefined} />
                    <KpiCard icon={Mic} label="Interviews" value={total ?? interviews.length} />
                  </div>

                  <div>
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="font-display text-sm uppercase tracking-tight text-white/70">Interview history</h3>
                      <Link
                        href="/interview/new"
                        className="font-mono text-[11px] font-bold uppercase tracking-wide text-brand-lime transition-colors hover:text-brand-lime/70"
                      >
                        + New interview
                      </Link>
                    </div>
                    <InterviewHistoryList interviews={interviews} />
                    {hasMore && (
                      <button
                        onClick={handleLoadMore}
                        disabled={loadingMore}
                        className="mx-auto mt-4 block rounded-full border-2 border-black bg-brand-lime px-6 py-2.5 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000] disabled:opacity-40"
                      >
                        {loadingMore ? "Loading..." : "Load more"}
                      </button>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function HistorySkeleton() {
  return (
    <div className="flex flex-col gap-5 pt-4">
      <div className="h-20 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
      <div className="h-24 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
      <div className="h-48 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
    </div>
  );
}
