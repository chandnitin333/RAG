import { useEffect, useState } from "react";
import { api } from "../api";
import type { IngestResult, ManifestSummary } from "../types";

export function IngestPanel() {
  const [summary, setSummary] = useState<ManifestSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rebuildManifest, setRebuildManifest] = useState(false);
  const [rebuildIndex, setRebuildIndex] = useState(false);
  const [limit, setLimit] = useState<number | "">("");

  const refreshSummary = async () => {
    try {
      setSummary(await api.manifestSummary());
    } catch {
      setSummary(null);
    }
  };

  useEffect(() => {
    refreshSummary();
  }, []);

  const ingest = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.ingestCorpus({
        rebuild_manifest: rebuildManifest,
        rebuild_index: rebuildIndex,
        limit: limit === "" ? null : Number(limit),
      });
      setResult(r);
      await refreshSummary();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const rebuildManifestOnly = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.rebuildManifest();
      await refreshSummary();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-4 space-y-3">
      <div className="text-sm font-semibold">Corpus ingestion</div>
      {summary ? (
        <div className="text-xs text-slate-400 space-y-1">
          <div>
            {summary.total_files.toLocaleString()} files —{" "}
            {(summary.total_bytes / 1024 / 1024 / 1024).toFixed(2)} GB
          </div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(summary.by_subject).map(([k, v]) => (
              <span className="badge" key={k}>
                {k}: {v}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(summary.by_source).map(([k, v]) => (
              <span className="badge" key={k}>
                {k}: {v}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-xs text-slate-500">No manifest yet.</div>
      )}

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={rebuildManifest}
          onChange={(e) => setRebuildManifest(e.target.checked)}
        />
        rebuild manifest before ingest
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={rebuildIndex}
          onChange={(e) => setRebuildIndex(e.target.checked)}
        />
        re-ingest already-indexed files (forget state)
      </label>
      <label className="text-sm flex items-center gap-2">
        limit (test runs):
        <input
          type="number"
          min={1}
          className="input w-24"
          placeholder="all"
          value={limit}
          onChange={(e) =>
            setLimit(e.target.value === "" ? "" : Number(e.target.value))
          }
        />
      </label>

      <div className="flex gap-2">
        <button className="btn" disabled={busy} onClick={rebuildManifestOnly}>
          rebuild manifest
        </button>
        <button className="btn-primary flex-1" disabled={busy} onClick={ingest}>
          {busy ? "Working… (may take a while)" : "Ingest corpus"}
        </button>
      </div>

      {err && <div className="text-sm text-rose-300">Error: {err}</div>}
      {result && (
        <div className="text-xs text-slate-300 space-y-1 border-t border-line pt-3">
          <div>processed: {result.total_files}</div>
          <div className="flex flex-wrap gap-1">
            <span className="badge">ok: {result.ok}</span>
            <span className="badge">skipped: {result.skipped}</span>
            <span className="badge">failed: {result.failed}</span>
            <span className="badge">chunks added: {result.total_chunks}</span>
            <span className="badge">elapsed: {result.elapsed_sec}s</span>
            <span className="badge">store size: {result.store_count}</span>
          </div>
        </div>
      )}
      <p className="text-xs text-slate-500 leading-relaxed">
        Heads-up: first full ingest of the JEE corpus is hours of work (PDF
        parse + OCR + embedding). It's resumable — if you re-run, completed
        files are skipped via <code>data/index/ingest_state.json</code>.
      </p>
    </div>
  );
}
