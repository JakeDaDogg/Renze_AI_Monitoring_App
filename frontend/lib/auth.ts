"use client";

import { useSyncExternalStore } from "react";

/**
 * Mock auth for the boilerplate. The session lives in sessionStorage so it is
 * cleared when the tab closes. Replace `login` with the real backend call.
 */

export type Session = {
  username: string;
  token: string;
};

const STORAGE_KEY = "renze.session";
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((l) => l());
}

export async function login(username: string, password: string): Promise<Session> {
  // TODO(backend): replace the mock with the FastAPI login endpoint, e.g.
  //   const res = await fetch(`${API_BASE_URL}/api/login`, {
  //     method: "POST",
  //     headers: { "Content-Type": "application/json" },
  //     body: JSON.stringify({ username, password }),
  //   });
  //   if (!res.ok) throw new Error("Invalid username or password");
  //   const session: Session = await res.json();
  void password; // unused by the mock: any non-empty credentials are accepted
  await new Promise((r) => setTimeout(r, 300)); // simulate network latency
  const session: Session = { username, token: "mock-token" };

  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  notify();
  return session;
}

export function logout() {
  // TODO(backend): call POST /api/logout if the backend keeps server sessions.
  sessionStorage.removeItem(STORAGE_KEY);
  notify();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

// Returns the raw string so the snapshot is referentially stable.
const getSnapshot = () => sessionStorage.getItem(STORAGE_KEY);
// `undefined` on the server / first render means "not known yet".
const getServerSnapshot = () => undefined;

/** `undefined` = still loading, `null` = signed out, otherwise the session. */
export function useSession(): Session | null | undefined {
  const raw = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  if (raw === undefined) return undefined;
  if (raw === null) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}
