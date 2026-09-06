"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User as FirebaseUser,
  type AuthError,
} from "firebase/auth";
import { auth, googleProvider, githubProvider } from "./firebase";
import { syncFirebaseAuth, type BackendUser } from "./api";

interface AuthContextValue {
  firebaseUser: FirebaseUser | null;
  backendUser: BackendUser | null;
  loading: boolean;
  authError: string | null;
  clearAuthError: () => void;
  signInWithGoogle: () => Promise<void>;
  signInWithGithub: () => Promise<void>;
  signOutUser: () => Promise<void>;
  getIdToken: () => Promise<string | null>;
}

// Codes a user triggers themselves just by closing the popup or clicking
// too fast -- not real failures, showing an error for these would be
// noise for completely normal behavior.
const BENIGN_AUTH_ERROR_CODES = new Set([
  "auth/popup-closed-by-user",
  "auth/cancelled-popup-request",
]);

function describeAuthError(err: unknown): string | null {
  const code = (err as AuthError)?.code;
  if (!code || BENIGN_AUTH_ERROR_CODES.has(code)) return null;
  if (code === "auth/popup-blocked") return "Your browser blocked the sign-in popup -- allow popups for this site and try again.";
  if (code === "auth/account-exists-with-different-credential") {
    return "That email is already linked to a different sign-in method -- try the other provider.";
  }
  if (code === "auth/network-request-failed") return "Network error -- check your connection and try again.";
  return "Sign-in didn't go through -- try again.";
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [backendUser, setBackendUser] = useState<BackendUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    // Firebase's own listener -- fires on sign-in, sign-out, and on page
    // load with whatever session Firebase already persisted (its default
    // is localStorage-backed, so a signed-in user stays signed in across
    // reloads without this app doing anything extra for that).
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      setFirebaseUser(user);
      if (user) {
        try {
          const token = await user.getIdToken();
          const synced = await syncFirebaseAuth(token);
          setBackendUser(synced);
        } catch {
          // backend sync failed (network blip, project mismatch, etc.) --
          // the user is still signed in on the Firebase side; leave
          // backendUser null rather than treating this as a full sign-out
          setBackendUser(null);
        }
      } else {
        setBackendUser(null);
      }
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const signInWithGoogle = async () => {
    setAuthError(null);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      setAuthError(describeAuthError(err));
    }
  };

  const signInWithGithub = async () => {
    setAuthError(null);
    try {
      await signInWithPopup(auth, githubProvider);
    } catch (err) {
      setAuthError(describeAuthError(err));
    }
  };

  const signOutUser = async () => {
    await firebaseSignOut(auth);
  };

  const getIdToken = async () => {
    if (!auth.currentUser) return null;
    return auth.currentUser.getIdToken();
  };

  return (
    <AuthContext.Provider
      value={{
        firebaseUser,
        backendUser,
        loading,
        authError,
        clearAuthError: () => setAuthError(null),
        signInWithGoogle,
        signInWithGithub,
        signOutUser,
        getIdToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
