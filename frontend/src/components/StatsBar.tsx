import { useEffect, useState } from "react";
import { api } from "../api";
import type { Stats } from "../types";

export function StatsBar() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    try {
      setStats(await api.stats());
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  if (err) {
    return (
      <div className="card p-3 text-sm text-rose-300">
        API unreachable: {err}. Start the backend at <code>localhost:8000</code>.
      </div>
    );
  }
  if (!stats) return <div className="card p-3 text-sm text-slate-400">Loading stats…</div>;

  return (
    <div className="card p-3 flex flex-wrap items-center gap-2 text-sm">
      <span className="badge">backend: {stats.backend}</span>
      <span className="badge">chunks: {stats.indexed_chunks.toLocaleString()}</span>
      <span className="badge">bm25: {stats.bm25_records.toLocaleString()}</span>
      <span className="badge">embed: {stats.embedding_model}</span>
      <span className="badge">dim: {stats.embedding_dim}</span>
      <span className="badge">
        rerank: {stats.reranker_enabled ? "on" : "off"}
      </span>
      <span className="badge">reader: {stats.reader_model}</span>
      <button className="btn ml-auto" onClick={load}>↻ refresh</button>
    </div>
  );
}
