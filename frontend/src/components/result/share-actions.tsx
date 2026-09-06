"use client";

import { useState } from "react";
import { Check, Link2, Share2 } from "lucide-react";

// No stored/effect-derived "shareUrl" state here on purpose -- window.location
// is only ever read inside these two click handlers, computed fresh each
// time. That sidesteps the whole SSR/client hydration-mismatch class of bug
// (this component renders during SSR, where window doesn't exist) without
// needing a useEffect + state dance to fill in a client-only value after
// mount.
export function ShareActions({ slug }: { slug: string }) {
  const [copied, setCopied] = useState(false);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/r/${slug}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard permission denied or unsupported -- fail silently,
      // the button just won't show the "copied" confirmation
    }
  };

  const openShareIntent = () => {
    const shareUrl = `${window.location.origin}/r/${slug}`;
    const tweetHref = `https://twitter.com/intent/tweet?text=${encodeURIComponent(
      "I just got my resume roasted. It did not go well.",
    )}&url=${encodeURIComponent(shareUrl)}`;
    window.open(tweetHref, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={copyLink}
        className="flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-4 py-2 font-mono text-xs font-bold text-white transition-colors hover:bg-white/20"
      >
        {copied ? <Check size={14} className="text-brand-lime" /> : <Link2 size={14} />}
        {copied ? "Copied" : "Copy link"}
      </button>
      <button
        onClick={openShareIntent}
        className="flex items-center gap-2 rounded-full border border-white/25 bg-white/10 px-4 py-2 font-mono text-xs font-bold text-white transition-colors hover:bg-white/20"
      >
        <Share2 size={14} />
        Share
      </button>
    </div>
  );
}
