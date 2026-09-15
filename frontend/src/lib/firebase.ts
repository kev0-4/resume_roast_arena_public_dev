import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, GithubAuthProvider, signInWithCustomToken } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
};

// getApps().length check avoids Next's dev-mode module re-evaluation
// (fast refresh, or this module being imported from both a server and
// client bundle) trying to initializeApp() more than once, which Firebase
// throws on.
const app = getApps().length ? getApp() : initializeApp(firebaseConfig);

export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
export const githubProvider = new GithubAuthProvider();

// Dev-only hook for scripts/interview_smoke_test's Playwright runner: it
// drives this real page (real Live WebSocket, real mic pipeline) rather
// than a hand-rolled client, specifically to rule out "the Python SDK
// behaves differently from the browser" as an explanation for audio
// never transcribing. That script has no OAuth popup to click through,
// so it signs in with a Firebase custom token (minted server-side via
// the same Admin SDK backend/src/services/firebase_auth.py already
// uses) against this exact `auth` singleton -- not a fresh one from an
// injected script, which Next's bundler would resolve to a different
// module instance and Firebase would treat as a different session.
//
// Gated on NODE_ENV so it is a no-op in any production build.
if (process.env.NODE_ENV !== "production" && typeof window !== "undefined") {
  (window as unknown as { __TEST_AUTH__: unknown }).__TEST_AUTH__ = {
    signInWithCustomToken: (token: string) => signInWithCustomToken(auth, token),
  };
}
