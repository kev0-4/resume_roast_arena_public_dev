"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { GitHubLogo, GoogleLogo } from "@/components/icons/social-icons";

// No outside-click library -- a single native `mousedown` listener,
// attached only while the dropdown is open and removed on close/unmount.
function useCloseOnOutsideClick(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, onClose]);

  return ref;
}

export function AuthMenu() {
  const { firebaseUser, backendUser, loading, signInWithGoogle, signInWithGithub, signOutUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [photoFailed, setPhotoFailed] = useState(false);
  const menuRef = useCloseOnOutsideClick(open, () => setOpen(false));

  if (loading) {
    return <div className="h-9 w-24 animate-pulse rounded-full border border-white/25 bg-white/10" />;
  }

  if (!firebaseUser) {
    return (
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setOpen((v) => !v)}
          className="rounded-full border border-white px-6 py-2 text-xs font-semibold text-white transition-colors hover:bg-white hover:text-brand-blue md:text-sm"
        >
          Sign in
        </button>
        {open && (
          <div className="absolute right-0 top-full z-30 mt-2 w-56 rounded-2xl border border-black/10 bg-white p-2 shadow-xl">
            <button
              onClick={async () => {
                setOpen(false);
                await signInWithGoogle();
              }}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left font-mono text-sm font-semibold text-black transition-colors hover:bg-black/5"
            >
              <GoogleLogo size={16} />
              Continue with Google
            </button>
            <button
              onClick={async () => {
                setOpen(false);
                await signInWithGithub();
              }}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left font-mono text-sm font-semibold text-black transition-colors hover:bg-black/5"
            >
              <GitHubLogo size={16} />
              Continue with GitHub
            </button>
          </div>
        )}
      </div>
    );
  }

  const displayName = backendUser?.display_name || firebaseUser.displayName || "Signed in";
  const photoUrl = backendUser?.photo_url || firebaseUser.photoURL;

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full border border-white/30 py-1 pl-1 pr-3 text-xs font-semibold text-white transition-colors hover:bg-white/10 md:text-sm"
      >
        {photoUrl && !photoFailed ? (
          <Image
            src={photoUrl}
            alt={displayName}
            width={28}
            height={28}
            className="rounded-full"
            unoptimized
            // Google/GitHub avatar CDNs are blocked outright by some
            // ad-blockers and privacy extensions (e.g. lh3.googleusercontent.com
            // shows up on a few tracker blocklists) -- rather than a
            // permanently broken-image icon, fall back to the initials
            // avatar the same way we do when there's no photoUrl at all.
            onError={() => setPhotoFailed(true)}
          />
        ) : (
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-lime font-display text-xs text-black">
            {displayName.charAt(0).toUpperCase()}
          </span>
        )}
        <span className="max-w-[8rem] truncate">{displayName}</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-48 rounded-2xl border border-black/10 bg-white p-2 shadow-xl">
          <Link
            href="/dashboard"
            onClick={() => setOpen(false)}
            className="block w-full rounded-xl px-3 py-2.5 text-left font-mono text-sm font-semibold text-black transition-colors hover:bg-black/5"
          >
            My Roasts
          </Link>
          <button
            onClick={async () => {
              setOpen(false);
              await signOutUser();
            }}
            className="w-full rounded-xl px-3 py-2.5 text-left font-mono text-sm font-semibold text-black transition-colors hover:bg-black/5"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
