"use client";

import { Search } from "lucide-react";

// Filters over the entries already loaded client-side (whatever "Load
// more" has fetched so far, capped at MAX_ENTRIES in the page) -- not a
// new backend search endpoint. Good enough for "find someone I know is
// on the board" without adding server-side search for a leaderboard this
// small.
export function SearchBox({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="relative">
      <Search size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-black/30" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search by name..."
        className="w-full rounded-full border-2 border-black bg-white py-2.5 pl-10 pr-4 font-mono text-sm font-semibold text-black placeholder:text-black/35 shadow-[3px_3px_0_#000] focus:outline-none"
      />
    </div>
  );
}
