"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Download, Link2 } from "lucide-react";
import { publicRoastCardUrl } from "@/lib/api";
import { InstagramLogo, LinkedInLogo, RedditLogo, WhatsAppLogo, XLogo } from "./social-icons";

const SHARE_TEXT = "I just got my resume roasted. It did not go well.";
const INSTAGRAM_APP_ID = process.env.NEXT_PUBLIC_INSTAGRAM_APP_ID;

function isIOS(): boolean {
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}

// Waits to see whether the browser actually switched away to a native app
// (the tab going `hidden` is the closest signal a website gets for "a
// custom URL scheme deep link just worked") -- resolves true if that
// happens within `timeoutMs`, false otherwise.
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
  // Prefetched on mount, not on click -- iOS Safari revokes "user
  // activation" after an awaited network request, which silently breaks
  // navigator.clipboard.write if the image is fetched inside the click
  // handler. Prefetching means the click handler can call it with no
  // network wait in between.
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

  const openReddit = () => {
    const href = `https://www.reddit.com/submit?url=${encodeURIComponent(shareUrl())}&title=${encodeURIComponent(SHARE_TEXT)}`;
    window.open(href, "_blank", "noopener,noreferrer");
  };

  // Instagram has no web share-intent URL (deliberately, on Instagram's
  // side), and the two platforms need genuinely different handling here --
  // this isn't a detail, it's the actual reason the first version of this
  // never worked on Android:
  //
  // - iOS: Meta's documented "share to Instagram Stories from your app"
  //   trick writes to the OS pasteboard using a private Instagram-specific
  //   data type, which is a *native* Swift capability. The closest a
  //   website can get is writing a plain image to the general clipboard
  //   via the standard Clipboard API, then triggering the
  //   instagram-stories://share deep link -- on some iOS/Instagram
  //   versions the Stories composer picks up a plain image already
  //   sitting on the general pasteboard. Not guaranteed, but a real,
  //   documented-if-unofficial pattern worth attempting.
  // - Android: that same trick does not exist. Android's real equivalent
  //   is a native Android Intent (action com.instagram.share.ADD_TO_STORY
  //   with a content:// URI extra) -- something only native app code can
  //   construct, not a URL scheme a browser can navigate to. Attempting
  //   the iOS-style deep link on Android does nothing but burn the
  //   timeout window. Android's actual working mechanism for handing a
  //   file to another app is the Web Share API's native share sheet,
  //   which Android supports well (better than iOS does, in practice) --
  //   so Android goes straight there instead of via a dead-end scheme.
  const tryInstagramStoriesDeepLink = async (blob: Blob): Promise<boolean> => {
    if (!INSTAGRAM_APP_ID || !isIOS()) return false;

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
    // iOS only -- see the big comment above for why Android skips this
    // entirely and goes straight to the Web Share API below.
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

    // Android's real mechanism: the native share sheet, with Instagram as
    // one of the real options the user picks, image already attached.
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
      <div className="flex flex-wrap items-center justify-center gap-2">
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
        <button onClick={openReddit} title="Share on Reddit" aria-label="Share on Reddit" className={iconButtonClass}>
          <RedditLogo size={16} />
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
