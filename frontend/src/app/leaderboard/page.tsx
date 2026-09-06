"use client";

import { useCallback, useEffect, useState } from "react";
import { Navbar } from "@/components/site/navbar";
import { Podium } from "@/components/leaderboard/podium";
import { LeaderboardRow } from "@/components/leaderboard/leaderboard-row";
import { YourRankBanner } from "@/components/leaderboard/your-rank-banner";
import { ApiError, getLeaderboard, type LeaderboardEntry } from "@/lib/api";

const PAGE_SIZE = 15;

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(async (offset: number) => {
    const data = await getLeaderboard(PAGE_SIZE, offset);
    setEntries((prev) => (offset === 0 ? data.entries : [...prev, ...data.entries]));
    setTotal(data.total);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await loadPage(0);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load the leaderboard.");
      } finally {
        setLoading(false);
      }
    })();
  }, [loadPage]);

  const handleLoadMore = async () => {
    setLoadingMore(true);
    try {
      await loadPage(entries.length);
    } catch {
      // a failed "load more" leaves the existing rows intact -- just no
      // visible error for a non-critical secondary action
    } finally {
      setLoadingMore(false);
    }
  };

  const rest = entries.slice(3);
  const hasMore = total !== null && entries.length < total;

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center gap-8 px-4 pb-16 pt-4 md:px-10">
        <div className="flex flex-col items-center text-center">
          <h1 className="font-display text-[clamp(2.2rem,6vw,3.6rem)] uppercase leading-[0.95] tracking-tighter text-white">
            The <span className="text-brand-lime">leaderboard</span>
          </h1>
          <p className="mt-2 max-w-md font-mono text-xs text-white/60 md:text-sm">
            Every roast that made the cut, ranked by score.
            {total !== null && <> {total} resumes roasted and counting.</>}
          </p>
        </div>

        {loading ? (
          <LeaderboardSkeleton />
        ) : error ? (
          <p className="font-mono text-sm text-brand-lime">{error}</p>
        ) : entries.length === 0 ? (
          <p className="font-mono text-sm text-white/60">No roasts on the board yet -- be the first.</p>
        ) : (
          <>
            <YourRankBanner />
            <Podium entries={entries} />
          </>
        )}
      </main>

      {!loading && !error && rest.length > 0 && (
        <section className="relative z-20 mt-auto w-full rounded-t-[2.5rem] bg-white px-6 py-12 text-black shadow-[0_-20px_50px_rgba(0,0,0,0.2)] md:rounded-t-[3.5rem] md:px-10 md:py-16">
          <div className="mx-auto flex max-w-3xl flex-col gap-8">
            <div className="flex flex-col gap-2">
              {rest.map((entry) => (
                <LeaderboardRow key={entry.slug} entry={entry} />
              ))}
            </div>

            {hasMore && (
              <button
                onClick={handleLoadMore}
                disabled={loadingMore}
                className="mx-auto rounded-full border-2 border-black px-6 py-2 font-display text-xs uppercase tracking-wide text-black transition-colors hover:bg-black hover:text-white disabled:opacity-40"
              >
                {loadingMore ? "Loading..." : "Load more"}
              </button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function LeaderboardSkeleton() {
  return (
    <div className="grid w-full max-w-3xl grid-cols-1 gap-4 md:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-56 animate-pulse rounded-[2rem] border border-white/10 bg-white/5" />
      ))}
    </div>
  );
}
