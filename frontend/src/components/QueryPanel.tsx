import { useState } from "react";
import { api } from "../api";
import type { QueryFilters, QueryResponse } from "../types";
import { Citations } from "./Citations";

interface Props {
  filters: QueryFilters;
}

export function QueryPanel({ filters }: Props) {
  const [q, setQ] = useState("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState<QueryResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const ask = async () => {
    if (!q.trim()) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await api.query({ query: q.trim(), top_k: topK, ...filters });
      setResp(r);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="card p-4 space-y-3">
        <label className="label">Ask a question of your indexed books</label>
        <textarea
          className="textarea w-full min-h-[88px]"
          placeholder="e.g. State Newton's second law and explain its vector form"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
          }}
        />
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-400 flex items-center gap-2">
            top_k
            <input
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value) || 5)}
              className="input w-16"
            />
          </label>
          <div className="flex flex-wrap gap-1 text-xs text-slate-400">
            {filters.subject && <span className="badge">subject={filters.subject}</span>}
            {filters.book && <span className="badge">book={filters.book}</span>}
            {filters.chapter && <span className="badge">chapter={filters.chapter}</span>}
          </div>
          <button className="btn-primary ml-auto" disabled={loading} onClick={ask}>
            {loading ? "Thinking…" : "Ask"}
          </button>
        </div>
        <div className="text-xs text-slate-500">
          tip: ⌘/Ctrl + Enter to submit
        </div>
      </div>

      {err && (
        <div className="card p-3 text-sm text-rose-300">Error: {err}</div>
      )}

      {resp && (
        <div className="space-y-4">
          <div className="card p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-semibold">Answer</span>
              {resp.mode && <span className="badge">{resp.mode}</span>}
            </div>
            <p className="whitespace-pre-wrap leading-relaxed">{resp.answer}</p>
          </div>
          <Citations citations={resp.citations} />
        </div>
      )}
    </div>
  );
}
