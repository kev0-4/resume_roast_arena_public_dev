"use client";

import { useState } from "react";
import { Check, Download, Link2 } from "lucide-react";
import { publicRoastCardUrl } from "@/lib/api";
import { InstagramLogo, LinkedInLogo, WhatsAppLogo, XLogo } from "./social-icons";

const SHARE_TEXT = "I just got my resume roasted. It did not go well.";

// No stored/effect-derived "shareUrl" state anywhere here on purpose --
// window.location is only ever read inside click handlers, computed fresh
// each time. Sidesteps the whole SSR/client hydration-mismatch class of
// bug (this component renders during SSR, where window doesn't exist)
// without a useEffect+state dance to fill in a client-only value after
// mount, and without tripping react-hooks/set-state-in-effect either.
export function ShareActions({ slug }: { slug: string }) {
  const [copied, setCopied] = useState(false);
  const [instagramStatus, setInstagramStatus] = useState<"idle" | "downloaded">("idle");

  const shareUrl = () => `${window.location.origin}/r/${slug}`;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard permission denied or unsupported -- button just won't
      // show the "copied" confirmation
    }
  };

  const openX = () => {
    const href = `https://twitter.com/intent/tweet?text=${encodeURIComponent(SHARE_TEXT)}&url=${encodeURIComponent(shareUrl())}`;
    window.open(href, "_blank", "noopener,noreferrer");
  };

  const openLinkedIn = () => {
    const href = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl())}`;
    window.open(href, "_blank", "noopener,noreferrer");
  };

  const openWhatsApp = () => {
    const href = `https://wa.me/?text=${encodeURIComponent(`${SHARE_TEXT} ${shareUrl()}`)}`;
    window.open(href, "_blank", "noopener,noreferrer");
  };

  // Instagram has no web share-intent URL (deliberately, on Instagram's
  // side) -- the two real options are the OS-level share sheet (Web Share
  // API, which lets a user pick Instagram directly with the image
  // attached, where the browser/device supports sharing files) or, as a
  // fallback everywhere else, downloading the card image with the caption
  // copied to the clipboard so the user can post it themselves.
  const shareToInstagram = async () => {
    let blob: Blob;
    try {
      const resp = await fetch(publicRoastCardUrl(slug));
      blob = await resp.blob();
    } catch {
      return; // network/CORS failure -- nothing sensible to fall back to
    }

    const file = new File([blob], "roast-card.png", { type: "image/png" });
    if (navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title: "My Resume Roast", text: SHARE_TEXT });
        return;
      } catch {
        // user cancelled the share sheet, or it failed -- fall through to
        // the download fallback below rather than leaving them stuck
      }
    }

    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "roast-card.png";
    link.click();
    URL.revokeObjectURL(objectUrl);

    try {
      await navigator.clipboard.writeText(SHARE_TEXT);
    } catch {
      // clipboard failure here just means the caption wasn't copied --
      // the image still downloaded, which is the part that matters most
    }
    setInstagramStatus("downloaded");
    setTimeout(() => setInstagramStatus("idle"), 4000);
  };

  const iconButtonClass =
    "flex h-9 w-9 items-center justify-center rounded-full border border-white/25 bg-white/10 text-white transition-colors hover:bg-white/20";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex items-center gap-2">
        <button onClick={copyLink} title="Copy link" aria-label="Copy link" className={iconButtonClass}>
          {copied ? <Check size={16} className="text-brand-lime" /> : <Link2 size={16} />}
        </button>
        <button onClick={openX} title="Share on X" aria-label="Share on X" className={iconButtonClass}>
          <XLogo size={15} />
        </button>
        <button onClick={openLinkedIn} title="Share on LinkedIn" aria-label="Share on LinkedIn" className={iconButtonClass}>
          <LinkedInLogo size={16} />
        </button>
        <button onClick={openWhatsApp} title="Share on WhatsApp" aria-label="Share on WhatsApp" className={iconButtonClass}>
          <WhatsAppLogo size={16} />
        </button>
        <button
          onClick={shareToInstagram}
          title="Share on Instagram"
          aria-label="Share on Instagram"
          className={iconButtonClass}
        >
          {instagramStatus === "downloaded" ? <Download size={16} className="text-brand-lime" /> : <InstagramLogo size={16} />}
        </button>
      </div>
      {instagramStatus === "downloaded" && (
        <p className="font-mono text-[10px] font-semibold text-brand-lime">
          Card saved + caption copied -- post it on Instagram!
        </p>
      )}
    </div>
  );
}
