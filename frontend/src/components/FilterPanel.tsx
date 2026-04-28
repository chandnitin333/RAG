import { useEffect, useState } from "react";
import { api } from "../api";
import type { ManifestSummary, QueryFilters } from "../types";

interface Props {
  value: QueryFilters;
  onChange: (f: QueryFilters) => void;
}

export function FilterPanel({ value, onChange }: Props) {
  const [summary, setSummary] = useState<ManifestSummary | null>(null);

  useEffect(() => {
    api.manifestSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  const subjects = summary ? Object.keys(summary.by_subject) : [];
  const books = summary?.books ?? [];

  return (
    <div className="card p-4 space-y-3">
      <div className="text-sm font-semibold">Filters</div>
      <div>
        <label className="label">Subject</label>
        <select
          className="select w-full"
          value={value.subject ?? ""}
          onChange={(e) => onChange({ ...value, subject: e.target.value || undefined })}
        >
          <option value="">— any —</option>
          {subjects.map((s) => (
            <option key={s} value={s}>
              {s} ({summary?.by_subject[s]})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="label">Book / volume</label>
        <select
          className="select w-full"
          value={value.book ?? ""}
          onChange={(e) => onChange({ ...value, book: e.target.value || undefined })}
        >
          <option value="">— any —</option>
          {books.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="label">Chapter (exact match)</label>
        <input
          className="input w-full"
          value={value.chapter ?? ""}
          placeholder="optional"
          onChange={(e) => onChange({ ...value, chapter: e.target.value || undefined })}
        />
      </div>
      <button
        className="btn w-full"
        onClick={() => onChange({})}
        disabled={!value.subject && !value.book && !value.chapter}
      >
        clear all
      </button>
    </div>
  );
}
