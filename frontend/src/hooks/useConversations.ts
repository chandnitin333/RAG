import { useCallback, useEffect, useMemo, useState } from "react";
import type { Citation, Retrieved } from "../types";

export interface Turn {
  role: "user" | "assistant";
  content: string;
  corrected?: string;
  citations?: Citation[];
  retrieved?: Retrieved[];
  interactionId?: string;
  agent?: string;
  agentLabel?: string;
  streaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  turns: Turn[];
  createdAt: number;
  updatedAt: number;
}

const LIST_KEY = "ragh.conversations.v1";
const ACTIVE_KEY = "ragh.conversations.active.v1";

function rid() {
  return "c_" + Math.random().toString(36).slice(2, 10);
}

function load(): Conversation[] {
  try {
    const raw = localStorage.getItem(LIST_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Conversation[]) : [];
  } catch {
    return [];
  }
}

function save(list: Conversation[]) {
  try {
    localStorage.setItem(LIST_KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

function loadActive(): string | null {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

function saveActive(id: string | null) {
  try {
    if (id) localStorage.setItem(ACTIVE_KEY, id);
    else localStorage.removeItem(ACTIVE_KEY);
  } catch {
    /* ignore */
  }
}

function deriveTitle(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > 60 ? t.slice(0, 60) + "…" : t || "New chat";
}

export function useConversations() {
  const [list, setList] = useState<Conversation[]>(load);
  const [activeId, setActiveId] = useState<string | null>(loadActive);

  useEffect(() => save(list), [list]);
  useEffect(() => saveActive(activeId), [activeId]);

  const active = useMemo(
    () => list.find((c) => c.id === activeId) || null,
    [list, activeId]
  );

  const create = useCallback((): string => {
    const c: Conversation = {
      id: rid(),
      title: "New chat",
      turns: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    setList((prev) => [c, ...prev]);
    setActiveId(c.id);
    return c.id;
  }, []);

  const open = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const remove = useCallback((id: string) => {
    setList((prev) => prev.filter((c) => c.id !== id));
    setActiveId((cur) => (cur === id ? null : cur));
  }, []);

  const rename = useCallback((id: string, title: string) => {
    setList((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title, updatedAt: Date.now() } : c))
    );
  }, []);

  const updateTurns = useCallback(
    (id: string, updater: (turns: Turn[]) => Turn[]) => {
      setList((prev) =>
        prev.map((c) => {
          if (c.id !== id) return c;
          const turns = updater(c.turns);
          // auto-title from the first user message
          let title = c.title;
          if ((!title || title === "New chat") && turns.length > 0) {
            const firstUser = turns.find((t) => t.role === "user");
            if (firstUser) title = deriveTitle(firstUser.content);
          }
          return { ...c, turns, title, updatedAt: Date.now() };
        })
      );
    },
    []
  );

  /** Ensure there's a current conversation to write into; create one if not. */
  const ensureActive = useCallback((): string => {
    if (activeId) return activeId;
    return create();
  }, [activeId, create]);

  return {
    list,
    active,
    activeId,
    create,
    open,
    remove,
    rename,
    updateTurns,
    ensureActive,
  };
}
