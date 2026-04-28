import type { Citation } from "../types";

interface Props {
  citations: Citation[];
}

export function Citations({ citations }: Props) {
  if (!citations.length) return null;
  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold text-slate-300">Citations</div>
      <ol className="space-y-2">
        {citations.map((c) => (
          <li
            key={c.index}
            className="card p-3 text-sm flex flex-col gap-1"
          >
            <div className="flex flex-wrap gap-2 items-center">
              <span className="badge bg-indigo-500/15 text-indigo-200 border-indigo-500/30">
                [{c.index}]
              </span>
              {c.subject && <span className="badge">{c.subject}</span>}
              {c.book && (
                <span className="badge truncate max-w-[16rem]" title={c.book}>
                  {c.book}
                </span>
              )}
              {c.chapter && (
                <span className="badge truncate max-w-[14rem]" title={c.chapter}>
                  {c.chapter}
                </span>
              )}
              {typeof c.score === "number" && (
                <span className="badge">score {c.score.toFixed(3)}</span>
              )}
            </div>
            {c.preview && (
              <p className="text-slate-300 leading-relaxed">{c.preview}</p>
            )}
            {c.source_file && (
              <p
                className="text-xs text-slate-500 truncate"
                title={c.source_file}
              >
                {c.source_file}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
