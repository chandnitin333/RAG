import type {
  AgentName,
  ChatMessage,
  ChatResponse,
  FeedbackRequest,
  InsightsResponse,
  IngestResult,
  ManifestSummary,
  PageFiguresResponse,
  QueryFilters,
  QueryResponse,
  Stats,
  TrainingStats,
  UploadResult,
} from "./types";

// In dev, vite proxies /v1 to http://localhost:8000.
// In prod, set VITE_API_BASE to your API origin (e.g. https://ragh.example.com).
const BASE = import.meta.env.VITE_API_BASE ?? "";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => jsonFetch<{ status: string; backend: string; indexed: number }>("/v1/health"),
  stats: () => jsonFetch<Stats>("/v1/stats"),
  manifestSummary: () => jsonFetch<ManifestSummary>("/v1/manifest/summary"),

  rebuildManifest: () =>
    jsonFetch<{ status: string; summary: ManifestSummary }>("/v1/manifest/rebuild", {
      method: "POST",
    }),

  ingestCorpus: (opts: {
    rebuild_manifest?: boolean;
    rebuild_index?: boolean;
    limit?: number | null;
    subject?: string | null;
    book?: string | null;
  }) =>
    jsonFetch<IngestResult>("/v1/ingest-corpus", {
      method: "POST",
      body: JSON.stringify({
        rebuild_manifest: !!opts.rebuild_manifest,
        rebuild_index: !!opts.rebuild_index,
        limit: opts.limit ?? null,
        subject: opts.subject ?? null,
        book: opts.book ?? null,
      }),
    }),

  rebuildBM25: () =>
    jsonFetch<{ status: string; records: number }>("/v1/bm25/rebuild", { method: "POST" }),

  query: (q: { query: string; top_k?: number } & QueryFilters) =>
    jsonFetch<QueryResponse>("/v1/query", {
      method: "POST",
      body: JSON.stringify(q),
    }),

  chat: (req: { messages: ChatMessage[]; top_k?: number; user_id?: string; agent?: AgentName | null } & QueryFilters) =>
    jsonFetch<ChatResponse>("/v1/chat", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  /** Streaming chat. Calls onEvent() for each NDJSON event. Resolves when stream ends. */
  chatStream: async (
    req: { messages: ChatMessage[]; top_k?: number; user_id?: string; agent?: AgentName | null } & QueryFilters,
    onEvent: (ev: { type: string; data: any }) => void,
    signal?: AbortSignal
  ) => {
    const res = await fetch(`${BASE}/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    });
    if (!res.ok || !res.body) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status}: ${text}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        if (!line) continue;
        try {
          onEvent(JSON.parse(line));
        } catch {
          /* ignore malformed line */
        }
      }
    }
  },

  insights: (userId: string, days: number = 30) =>
    jsonFetch<InsightsResponse>(`/v1/personal/insights?user_id=${encodeURIComponent(userId)}&days=${days}`),

  agents: () => jsonFetch<{ agents: Record<string, string> }>("/v1/agents"),

  pageImageUrl: (sourceFile: string, opts: { startChar?: number; page?: number; dpi?: number } = {}) => {
    const p = new URLSearchParams({ source_file: sourceFile });
    if (opts.startChar !== undefined) p.set("start_char", String(opts.startChar));
    if (opts.page !== undefined) p.set("page", String(opts.page));
    if (opts.dpi !== undefined) p.set("dpi", String(opts.dpi));
    return `${BASE}/v1/page-image?${p.toString()}`;
  },

  pageFigures: (sourceFile: string, opts: { startChar?: number; page?: number } = {}) => {
    const p = new URLSearchParams({ source_file: sourceFile });
    if (opts.startChar !== undefined) p.set("start_char", String(opts.startChar));
    if (opts.page !== undefined) p.set("page", String(opts.page));
    return jsonFetch<PageFiguresResponse>(`/v1/page-figures?${p.toString()}`);
  },

  figureUrl: (relPath: string) => `${BASE}${relPath}`,

  feedback: (req: FeedbackRequest) =>
    jsonFetch<{ status: string; feedback_id: number; stats: TrainingStats }>(
      "/v1/feedback",
      { method: "POST", body: JSON.stringify(req) }
    ),

  trainingStats: () => jsonFetch<TrainingStats>("/v1/training/stats"),

  upload: async (files: File[]): Promise<UploadResult> => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    const res = await fetch(`${BASE}/v1/upload`, { method: "POST", body: fd });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    return (await res.json()) as UploadResult;
  },
};
