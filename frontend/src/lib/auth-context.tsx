"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User as FirebaseUser,
} from "firebase/auth";
import { auth, googleProvider, githubProvider } from "./firebase";
import { syncFirebaseAuth, type BackendUser } from "./api";

interface AuthContextValue {
  firebaseUser: FirebaseUser | null;
  backendUser: BackendUser | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithGithub: () => Promise<void>;
  signOutUser: () => Promise<void>;
  getIdToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [backendUser, setBackendUser] = useState<BackendUser | null>(null);
  const [loading, setLoading] = useState(true);

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
    await signInWithPopup(auth, googleProvider);
  };

  const signInWithGithub = async () => {
    await signInWithPopup(auth, githubProvider);
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
      value={{ firebaseUser, backendUser, loading, signInWithGoogle, signInWithGithub, signOutUser, getIdToken }}
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
