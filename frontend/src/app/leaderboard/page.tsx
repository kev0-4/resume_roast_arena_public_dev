"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Navbar } from "@/components/site/navbar";
import { HeroPanel } from "@/components/leaderboard/hero-panel";
import { LeaderboardList } from "@/components/leaderboard/leaderboard-list";
import { YourRankBanner } from "@/components/leaderboard/your-rank-banner";
import { SearchBox } from "@/components/leaderboard/search-box";
import { ApiError, getLeaderboard, type LeaderboardEntry } from "@/lib/api";

const PAGE_SIZE = 15;
// Hard ceiling on how many rows "Load more" will ever fetch, regardless
// of how large `total` actually is -- without this, a large enough
// leaderboard turns "Load more" into an unintentional unlimited scroll.
// 100 keeps it a genuine top-of-the-pile view, not a full directory.
const MAX_ENTRIES = 100;

export default function LeaderboardPage() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const loadPage = useCallback(async (offset: number) => {
    const limit = Math.min(PAGE_SIZE, MAX_ENTRIES - offset);
    const data = await getLeaderboard(limit, offset);
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
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? rest.filter((e) => e.display_name.toLowerCase().includes(q)) : rest;
  }, [query, rest]);
  const atCap = entries.length >= MAX_ENTRIES;
  const hasMore = !atCap && total !== null && entries.length < total;

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <div className="relative z-10">
        <Navbar />

        <main className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-4 pb-16">
        {loading ? (
          <LeaderboardSkeleton />
        ) : error ? (
          <p className="py-16 text-center font-mono text-sm text-brand-lime">{error}</p>
        ) : entries.length === 0 ? (
          <p className="py-16 text-center font-mono text-sm text-white/60">No roasts on the board yet -- be the first.</p>
        ) : (
          <>
            <HeroPanel entries={entries} total={total} />
            <YourRankBanner />

            {rest.length > 0 && (
              <>
                <SearchBox value={query} onChange={setQuery} />

                {filtered.length > 0 ? (
                  <LeaderboardList entries={filtered} />
                ) : (
                  <p className="rounded-2xl border-[3px] border-black bg-white px-4 py-8 text-center font-mono text-sm font-semibold text-black/40 shadow-[5px_5px_0_#000]">
                    No one by that name got roasted (yet).
                  </p>
                )}

                {hasMore && !query && (
                  <button
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    className="mx-auto rounded-full border-2 border-black bg-brand-lime px-6 py-2.5 font-display text-xs uppercase tracking-wide text-black shadow-[3px_3px_0_#000] transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-[1px_1px_0_#000] disabled:opacity-40"
                  >
                    {loadingMore ? "Loading..." : "Load more"}
                  </button>
                )}
                {atCap && !query && (
                  <p className="text-center font-mono text-[11px] text-white/40">Showing the top {MAX_ENTRIES} roasts.</p>
                )}
              </>
            )}
          </>
        )}
        </main>
      </div>
    </div>
  );
}

function LeaderboardSkeleton() {
  return (
    <div className="flex flex-col gap-5 pt-6">
      <div className="h-[26rem] animate-pulse rounded-[1.75rem] border-[3px] border-black/10 bg-white/5" />
      <div className="h-14 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
      <div className="h-64 animate-pulse rounded-2xl border-[3px] border-black/10 bg-white/5" />
    </div>
  );
}
