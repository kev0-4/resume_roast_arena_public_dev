"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/site/navbar";
import { HistoryList } from "@/components/dashboard/history-list";
import { useAuth } from "@/lib/auth-context";
import { ApiError, getMySessions, type MySession } from "@/lib/api";

const PAGE_SIZE = 20;

export default function DashboardPage() {
  const { firebaseUser, loading: authLoading, getIdToken } = useAuth();
  const [sessions, setSessions] = useState<MySession[]>([]);
  const [total, setTotal] = useState<number | null>(null);
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
    },
    [getIdToken],
  );

  useEffect(() => {
    // No setState for the "not signed in" case -- the render below checks
    // !firebaseUser before it ever looks at `loading`, so that branch
    // never needs `loading` to flip; only the real fetch below does.
    if (authLoading || !firebaseUser) return;
    (async () => {
      try {
        await loadPage(0);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load your roast history.");
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, firebaseUser, loadPage]);

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

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <div className="relative z-10">
        <Navbar />

        <main className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-4 pb-16">
          <div className="flex flex-col items-center pt-4 text-center">
            <h1 className="font-display text-[clamp(2rem,5vw,2.8rem)] uppercase leading-[0.95] tracking-tighter text-white">
              Your <span className="text-brand-lime">roasts</span>
            </h1>
            <p className="mt-1.5 max-w-sm font-mono text-xs text-white/60 md:text-sm">
              Every resume you&apos;ve thrown to the wolves.
            </p>
          </div>

          {authLoading ? (
            <DashboardSkeleton />
          ) : !firebaseUser ? (
            <div className="flex flex-col items-center gap-3 rounded-2xl border-[3px] border-black bg-white/90 px-6 py-10 text-center shadow-[5px_5px_0_#000]">
              <p className="font-mono text-sm font-semibold text-black/70">Sign in to see your roast history.</p>
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
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-2xl border-[3px] border-black bg-white/90 px-6 py-10 text-center shadow-[5px_5px_0_#000]">
              <p className="font-mono text-sm font-semibold text-black/70">You haven&apos;t roasted a resume yet.</p>
              <Link
                href="/roast"
                className="rounded-full border-2 border-black bg-brand-lime px-5 py-2 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000]"
              >
                Roast your resume
              </Link>
            </div>
          ) : (
            <>
              <HistoryList sessions={sessions} />
              {hasMore && (
                <button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="mx-auto rounded-full border-2 border-black bg-brand-lime px-6 py-2.5 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000] disabled:opacity-40"
                >
                  {loadingMore ? "Loading..." : "Load more"}
                </button>
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
    <div className="flex flex-col gap-5 pt-2">
      <div className="h-64 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
    </div>
  );
}
