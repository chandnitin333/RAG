import { useState } from "react";
import type { Conversation } from "../hooks/useConversations";

interface Props {
  list: Conversation[];
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  collapsed: boolean;
  onToggle: () => void;
}

function timeAgo(ts: number): string {
  const s = Math.max(1, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function ConversationSidebar({
  list,
  activeId,
  onNew,
  onOpen,
  onDelete,
  onRename,
  collapsed,
  onToggle,
}: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  if (collapsed) {
    return (
      <aside className="w-12 shrink-0 border-r border-line/60 bg-ink/40 flex flex-col items-center py-3 gap-2">
        <button className="btn !px-2" title="expand" onClick={onToggle}>›</button>
        <button className="btn-primary !px-2" title="new chat" onClick={onNew}>+</button>
      </aside>
    );
  }

  return (
    <aside className="w-64 shrink-0 border-r border-line/60 bg-ink/30 flex flex-col">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-line/40">
        <button className="btn !px-2" title="collapse" onClick={onToggle}>‹</button>
        <button className="btn-primary flex-1 text-sm" onClick={onNew}>
          + New chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-1">
        {list.length === 0 && (
          <div className="text-xs text-slate-500 p-3">
            No conversations yet. Click <span className="text-indigo-300">+ New chat</span> to start.
          </div>
        )}
        {list.map((c) => {
          const isActive = c.id === activeId;
          const isEditing = editing === c.id;
          return (
            <div
              key={c.id}
              className={
                "group flex items-center gap-1 px-2 py-1.5 rounded-md mx-1 my-0.5 cursor-pointer transition " +
                (isActive
                  ? "bg-indigo-500/15 border border-indigo-500/30 text-indigo-100"
                  : "hover:bg-line/40 border border-transparent text-slate-300")
              }
              onClick={() => !isEditing && onOpen(c.id)}
            >
              {isEditing ? (
                <input
                  className="input flex-1 text-xs py-1"
                  value={editText}
                  autoFocus
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      onRename(c.id, editText.trim() || c.title);
                      setEditing(null);
                    } else if (e.key === "Escape") {
                      setEditing(null);
                    }
                  }}
                  onBlur={() => {
                    onRename(c.id, editText.trim() || c.title);
                    setEditing(null);
                  }}
                />
              ) : (
                <>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm truncate" title={c.title}>
                      {c.title}
                    </div>
                    <div className="text-[10px] text-slate-500">
                      {c.turns.length} msgs · {timeAgo(c.updatedAt)} ago
                    </div>
                  </div>
                  <button
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-100 px-1"
                    title="rename"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditing(c.id);
                      setEditText(c.title);
                    }}
                  >
                    ✎
                  </button>
                  <button
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-300 px-1"
                    title="delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(`Delete "${c.title}"?`)) onDelete(c.id);
                    }}
                  >
                    ✕
                  </button>
                </>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
