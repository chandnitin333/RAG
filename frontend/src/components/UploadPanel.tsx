import { useRef, useState } from "react";
import { api } from "../api";
import type { UploadResult } from "../types";

export function UploadPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const onUpload = async () => {
    const files = Array.from(inputRef.current?.files ?? []);
    if (!files.length) return;
    setBusy(true);
    setErr(null);
    try {
      setResult(await api.upload(files));
      if (inputRef.current) inputRef.current.value = "";
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-4 space-y-3">
      <div className="text-sm font-semibold">Upload files</div>
      <p className="text-xs text-slate-400">
        PDF, DOCX, TXT, PNG/JPG. Files are extracted, chunked, embedded, and added to the index.
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-indigo-500 file:px-3 file:py-2 file:text-white hover:file:bg-indigo-400"
        accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg"
      />
      <button className="btn-primary w-full" disabled={busy} onClick={onUpload}>
        {busy ? "Uploading…" : "Upload & index"}
      </button>
      {err && <div className="text-sm text-rose-300">Error: {err}</div>}
      {result && (
        <ul className="text-xs space-y-1 text-slate-300">
          {result.results.map((r, i) => (
            <li key={i} className="flex justify-between gap-2">
              <span className="truncate">{r.file}</span>
              <span className="text-slate-400 shrink-0">
                {r.error
                  ? `error: ${r.error}`
                  : r.note
                    ? r.note
                    : `${r.indexed ?? 0} chunks`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
