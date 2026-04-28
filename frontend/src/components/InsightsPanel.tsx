import { useEffect, useState } from "react";
import { api } from "../api";
import { useUserId } from "../hooks/useUserId";
import type { InsightsResponse } from "../types";

export function InsightsPanel() {
  const userId = useUserId();
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [days, setDays] = useState(30);

  const load = () => {
    api.insights(userId, days).then(setData).catch(() => setData(null));
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, days]);

  if (!data) {
    return (
      <div className="card p-4 text-sm text-slate-400">
        No insights yet — ask a few questions to populate your study profile.
      </div>
    );
  }

  return (
    <div className="card p-4 space-y-4 text-sm">
      <div className="flex items-center gap-2">
        <h3 className="font-semibold">Your study profile</h3>
        <span className="badge ml-auto">{data.total_questions} questions / {data.window_days}d</span>
        <select
          className="select text-xs py-1"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={7}>7d</option>
          <option value={30}>30d</option>
          <option value={90}>90d</option>
        </select>
      </div>

      {Object.keys(data.by_subject).length > 0 && (
        <section>
          <div className="label">By subject</div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(data.by_subject).map(([s, n]) => (
              <span key={s} className="badge">{s}: {n}</span>
            ))}
          </div>
        </section>
      )}

      {Object.keys(data.by_agent).length > 0 && (
        <section>
          <div className="label">By agent</div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(data.by_agent).map(([a, n]) => (
              <span key={a} className="badge">{a}: {n}</span>
            ))}
          </div>
        </section>
      )}

      {data.recommendations.length > 0 && (
        <section>
          <div className="label">Suggested focus</div>
          <ul className="space-y-2">
            {data.recommendations.map((r, i) => (
              <li key={i} className="bg-ink/40 border border-line rounded-md p-2">
                <div className="text-slate-200 text-xs font-semibold truncate" title={r.chapter}>
                  {r.subject} • {r.chapter}
                </div>
                <div className="text-xs text-slate-400">{r.rationale}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.recent.length > 0 && (
        <section>
          <div className="label">Recent questions</div>
          <ul className="space-y-1 text-xs text-slate-400 max-h-40 overflow-y-auto">
            {data.recent.map((r, i) => (
              <li key={i} className="truncate" title={r.query}>
                <span className="text-slate-500">[{r.agent || "?"}]</span> {r.query}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
