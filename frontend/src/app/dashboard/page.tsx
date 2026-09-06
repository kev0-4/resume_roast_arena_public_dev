"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Flame, Target, Trophy } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { ProfileHeader } from "@/components/dashboard/profile-header";
import { LatestRoastAndRadar } from "@/components/dashboard/latest-roast-radar";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { ScoreTrend } from "@/components/dashboard/score-trend";
import { HistoryList } from "@/components/dashboard/history-list";
import { useAuth } from "@/lib/auth-context";
import {
  ApiError,
  getMySessions,
  getMyLeaderboardPosition,
  getRoastAnalysis,
  type MySession,
  type MyStats,
  type MyLeaderboardPosition,
  type RoastAnalysis,
} from "@/lib/api";

const PAGE_SIZE = 50;

export default function DashboardPage() {
  const { firebaseUser, backendUser, loading: authLoading, getIdToken, signOutUser } = useAuth();
  const [sessions, setSessions] = useState<MySession[]>([]);
  const [stats, setStats] = useState<MyStats | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [rank, setRank] = useState<MyLeaderboardPosition | null>(null);
  const [latestRoast, setLatestRoast] = useState<RoastAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(
    async (offset: number) => {
      const token = await getIdToken();
      if (!token) throw new ApiError("Not signed in", 401);
      const data = await getMySessions(token, PAGE_SIZE, offset);
      setSessions((prev) => (offset === 0 ? data.sessions : [...prev, ...data.sessions]));
      setTotal(data.total);
      setStats(data.stats);
      return { token, sessions: offset === 0 ? data.sessions : [...sessions, ...data.sessions] };
    },
    [getIdToken, sessions],
  );

  useEffect(() => {
    // No setState for "auth still resolving" or "signed out" -- the
    // render below checks authLoading/!firebaseUser before it ever looks
    // at `loading`, so neither branch needs `loading` to flip; only the
    // real fetch below does.
    if (authLoading || !firebaseUser) return;
    (async () => {
      try {
        const { token, sessions: loaded } = await loadPage(0);

        const latestDone = loaded.find((s) => s.status === "DONE" && s.slug);
        const [rankResult, roastResult] = await Promise.allSettled([
          getMyLeaderboardPosition(token),
          latestDone?.slug ? getRoastAnalysis(latestDone.slug) : Promise.resolve(null),
        ]);
        if (rankResult.status === "fulfilled") setRank(rankResult.value);
        if (roastResult.status === "fulfilled") setLatestRoast(roastResult.value);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load your dashboard.");
      } finally {
        setLoading(false);
      }
    })();
    // loadPage intentionally excluded -- it closes over `sessions` (for
    // handleLoadMore's benefit), which would make this effect refire on
    // every page load; only auth state should ever re-trigger the
    // initial dashboard load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, firebaseUser]);

  const handleLoadMore = async () => {
    setLoadingMore(true);
    try {
      await loadPage(sessions.length);
    } catch {
      // a failed "load more" leaves the existing rows intact
    } finally {
      setLoadingMore(false);
    }
  };

  const hasMore = total !== null && sessions.length < total;
  // chronological (oldest first) for the trend chart -- `sessions` itself
  // is most-recent-first, matching the history list's own order
  const trendScores = [...sessions]
    .filter((s) => s.status === "DONE" && s.composite_score !== null)
    .reverse()
    .map((s) => s.composite_score as number);

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <div className="relative z-10">
        <Navbar />

        <main className="mx-auto flex w-full max-w-4xl flex-col gap-5 px-4 pb-16">
          {authLoading ? (
            <DashboardSkeleton />
          ) : !firebaseUser ? (
            <div className="flex flex-col items-center gap-3 rounded-2xl border-[3px] border-black bg-white/90 px-6 py-10 text-center shadow-[5px_5px_0_#000]">
              <p className="font-mono text-sm font-semibold text-black/70">Sign in to see your dashboard.</p>
              <Link
                href="/roast"
                className="rounded-full border-2 border-black bg-brand-lime px-5 py-2 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000]"
              >
                Go roast a resume
              </Link>
            </div>
          ) : loading ? (
            <DashboardSkeleton />
          ) : error ? (
            <p className="py-16 text-center font-mono text-sm text-brand-lime">{error}</p>
          ) : (
            <>
              <ProfileHeader
                displayName={backendUser?.display_name || firebaseUser.displayName || "You"}
                createdAt={backendUser?.created_at ?? null}
                onSignOut={signOutUser}
              />

              {latestRoast ? (
                <LatestRoastAndRadar roast={latestRoast} />
              ) : (
                <div className="flex flex-col items-center gap-3 rounded-2xl border-[3px] border-black bg-brand-blue-deep px-6 py-10 text-center shadow-[5px_5px_0_#000]">
                  <p className="font-mono text-sm font-semibold text-white/70">You haven&apos;t roasted a resume yet.</p>
                  <Link
                    href="/roast"
                    className="rounded-full border-2 border-black bg-brand-lime px-5 py-2 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000]"
                  >
                    Roast your resume
                  </Link>
                </div>
              )}

              <div className="grid grid-cols-3 gap-3">
                <KpiCard icon={Flame} label="Rank" value={rank ? `#${rank.rank}` : "--"} sub={rank ? `of ${rank.total}` : undefined} />
                <KpiCard icon={Trophy} label="Best score" value={stats?.best_score ?? "--"} />
                <KpiCard icon={Target} label="Average score" value={stats?.average_score ?? "--"} />
              </div>

              <ScoreTrend scores={trendScores} />

              {sessions.length > 0 && (
                <div>
                  <h3 className="mb-3 font-display text-sm uppercase tracking-tight text-white/70">Roast history</h3>
                  <HistoryList sessions={sessions} />
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
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-5 pt-4">
      <div className="h-20 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
      <div className="h-64 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
      <div className="h-24 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
    </div>
  );
}
