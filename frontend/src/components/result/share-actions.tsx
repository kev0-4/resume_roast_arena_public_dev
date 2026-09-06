"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Download, Link2 } from "lucide-react";
import { publicRoastCardUrl } from "@/lib/api";
import { InstagramLogo, LinkedInLogo, WhatsAppLogo, XLogo } from "./social-icons";

const SHARE_TEXT = "I just got my resume roasted. It did not go well.";
const INSTAGRAM_APP_ID = process.env.NEXT_PUBLIC_INSTAGRAM_APP_ID;

function isMobileDevice(): boolean {
  return /iphone|ipad|ipod|android/i.test(navigator.userAgent);
}

// Waits to see whether the browser actually switched away to a native app
// (the tab going `hidden` is the closest signal a website gets for "the
// instagram-stories:// deep link just worked") -- resolves true if that
// happens within `timeoutMs`, false otherwise (no Instagram app installed,
// desktop browser that ignores the scheme, etc.), so the caller knows
// whether to fall back.
function waitForAppSwitch(timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        cleanup();
        resolve(true);
      }
    };
    const timer = setTimeout(() => {
      cleanup();
      resolve(false);
    }, timeoutMs);
    const cleanup = () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
  });
}

// No stored/effect-derived "shareUrl" state anywhere here on purpose --
// window.location is only ever read inside click handlers, computed fresh
// each time. Sidesteps the whole SSR/client hydration-mismatch class of
// bug (this component renders during SSR, where window doesn't exist)
// without a useEffect+state dance to fill in a client-only value after
// mount, and without tripping react-hooks/set-state-in-effect either.
export function ShareActions({ slug }: { slug: string }) {
  const [copied, setCopied] = useState(false);
  const [instagramStatus, setInstagramStatus] = useState<"idle" | "downloaded">("idle");
  // Prefetched on mount, not on click -- see tryInstagramStoriesDeepLink's
  // comment below for why this matters (it's the actual fix for the deep
  // link never firing on a real device).
  const cardBlobRef = useRef<Blob | null>(null);

  useEffect(() => {
    fetch(publicRoastCardUrl(slug))
      .then((r) => r.blob())
      .then((b) => {
        cardBlobRef.current = b;
      })
      .catch(() => {
        // best-effort prefetch -- every caller below still fetches on
        // demand if this hasn't landed (or failed) by click time
      });
  }, [slug]);

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
  // side). What Spotify Wrapped-style apps do (open Stories with the
  // image already loaded) is a *native app* capability -- they write to
  // the OS pasteboard using a private Instagram-specific data type
  // (com.instagram.sharedSticker.backgroundImage) via native Swift/Kotlin
  // code, which a website's JavaScript cannot do. This is the closest
  // real equivalent from a website: write the image to the *general*
  // clipboard via the standard Clipboard API, then trigger Instagram's
  // documented Stories deep link (instagram-stories://share) with our
  // Meta App ID as source_application. On some iOS/Instagram versions
  // the Stories composer picks up a plain image already on the general
  // pasteboard -- this isn't guaranteed the way the native-only trick is,
  // it's the best a web app can do, so it's only attempted on mobile
  // (the scheme means nothing on desktop) and always has a real fallback
  // if the app never opens.
  //
  // Critical ordering constraint (found from real-device testing, not
  // simulated): navigator.clipboard.write must be *called* with no
  // `await` between the click and that call, or Safari on iOS silently
  // rejects it as "not associated with a user gesture" -- browsers only
  // keep a click's "user activation" alive for a very short window, and
  // an awaited network request is enough to lose it. This is exactly why
  // this needs the prefetched blob (cardBlobRef, fetched on mount) rather
  // than fetching the image on click -- an `await fetch()` right before
  // this call was silently breaking it on every real device even though
  // automated (Chromium-based) testing never caught it, since Chrome is
  // much more lenient here than Safari.
  const tryInstagramStoriesDeepLink = async (blob: Blob): Promise<boolean> => {
    if (!INSTAGRAM_APP_ID || !isMobileDevice()) return false;

    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
    } catch {
      return false; // can't write images to the clipboard here -- skip straight to fallback
    }

    const switched = waitForAppSwitch(1500);
    window.location.href = `instagram-stories://share?source_application=${INSTAGRAM_APP_ID}`;
    return switched;
  };

  const shareToInstagram = async () => {
    // Try the prefetched blob FIRST, synchronously relative to the click
    // (see the big comment above) -- only fetch on demand as a fallback
    // if the mount-time prefetch hasn't landed yet, in which case the
    // deep link is already off the table for this click and we go
    // straight to the download/share-sheet path below anyway.
    if (cardBlobRef.current) {
      if (await tryInstagramStoriesDeepLink(cardBlobRef.current)) return;
    }

    let blob: Blob | null = cardBlobRef.current;
    if (!blob) {
      try {
        const resp = await fetch(publicRoastCardUrl(slug));
        blob = await resp.blob();
      } catch {
        return; // network/CORS failure -- nothing sensible to fall back to
      }
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
