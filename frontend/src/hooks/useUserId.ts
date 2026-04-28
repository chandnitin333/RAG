import { useState } from "react";

const KEY = "ragh.user_id.v1";

function rand() {
  return "u_" + Math.random().toString(36).slice(2, 10);
}

/** Stable per-browser anonymous user id, persisted to localStorage. */
export function useUserId(): string {
  const [id] = useState<string>(() => {
    try {
      const v = localStorage.getItem(KEY);
      if (v) return v;
    } catch {
      /* SSR or storage disabled */
    }
    const fresh = rand();
    try {
      localStorage.setItem(KEY, fresh);
    } catch {
      /* ignore */
    }
    return fresh;
  });
  return id;
}
