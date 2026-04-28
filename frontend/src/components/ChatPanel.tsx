import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { AgentName, ChatMessage, QueryFilters } from "../types";
import type { Turn } from "../hooks/useConversations";
import { useConversations } from "../hooks/useConversations";
import { useUserId } from "../hooks/useUserId";
import { MessageRenderer } from "./MessageRenderer";
import { TypewriterStream } from "./TypewriterStream";
import { DownloadPdfButton } from "./DownloadPdfButton";
import { FeedbackButtons } from "./FeedbackButtons";
import { ConversationSidebar } from "./ConversationSidebar";

interface Props {
  filters: QueryFilters;
}

const EXAMPLES = [
  { emoji: "📐", title: "Explain a concept", prompt: "Explain the relationship between degrees and radians, with one example." },
  { emoji: "🧮", title: "Solve a problem", prompt: "Solve: a circular arc of length π cm in a circle of radius 6 cm — find the angle in radians and degrees." },
  { emoji: "🎨", title: "Draw a diagram", prompt: "Draw a labelled diagram of a vector with x and y components in 2D." },
  { emoji: "📅", title: "Plan revision", prompt: "Make a 3-day study plan for trigonometry covering basics, identities, and problem solving." },
];

export function ChatPanel({ filters }: Props) {
  const conv = useConversations();
  const userId = useUserId();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [agent, setAgent] = useState<AgentName | "auto">("auto");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const turns: Turn[] = useMemo(() => conv.active?.turns ?? [], [conv.active]);

  // auto-scroll to bottom on new content
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  // auto-resize textarea
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = Math.min(ta.scrollHeight, 220) + "px";
  }, [input]);

  const updateLastAssistant = (mut: (t: Turn) => Turn) => {
    const id = conv.activeId;
    if (!id) return;
    conv.updateTurns(id, (cur) => {
      const out = cur.slice();
      if (out.length && out[out.length - 1].role === "assistant") {
        out[out.length - 1] = mut(out[out.length - 1]);
      }
      return out;
    });
  };

  const sendQuery = async (text: string, replaceLast: boolean = false) => {
    const id = conv.ensureActive();
    const baseTurns: Turn[] = (() => {
      const cur = (conv.list.find((c) => c.id === id)?.turns ?? []).slice();
      if (replaceLast && cur.length && cur[cur.length - 1].role === "assistant") {
        cur.pop();
      }
      return cur;
    })();

    const userTurn: Turn = { role: "user", content: text };
    const placeholder: Turn = { role: "assistant", content: "", streaming: true };
    const next = replaceLast ? [...baseTurns, placeholder] : [...baseTurns, userTurn, placeholder];
    conv.updateTurns(id, () => next);

    setBusy(true);
    setErr(null);
    abortRef.current = new AbortController();
    const messages: ChatMessage[] = (replaceLast ? [...baseTurns] : [...baseTurns, userTurn]).map(
      (t) => ({ role: t.role, content: t.content })
    );
    try {
      await api.chatStream(
        {
          messages,
          top_k: 5,
          user_id: userId,
          agent: agent === "auto" ? null : (agent as AgentName),
          ...filters,
        },
        (ev) => {
          updateLastAssistant((last) => {
            const out = { ...last };
            if (ev.type === "interaction_id") out.interactionId = ev.data;
            else if (ev.type === "corrected") out.corrected = ev.data;
            else if (ev.type === "agent") {
              out.agent = ev.data.agent;
              out.agentLabel = ev.data.label;
            }
            else if (ev.type === "citations") out.citations = ev.data;
            else if (ev.type === "token") out.content = (out.content || "") + ev.data;
            else if (ev.type === "done") out.streaming = false;
            else if (ev.type === "error") {
              out.content = (out.content || "") + `\n\n[error: ${ev.data}]`;
              out.streaming = false;
            }
            return out;
          });
        },
        abortRef.current.signal
      );
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") {
        // user clicked stop — leave whatever we have
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
      updateLastAssistant((last) => ({ ...last, streaming: false }));
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    await sendQuery(text);
  };

  const stop = () => {
    abortRef.current?.abort();
  };

  const regenerate = async () => {
    const lastUser = [...turns].reverse().find((t) => t.role === "user");
    if (!lastUser || busy) return;
    await sendQuery(lastUser.content, true);
  };

  const copyAnswer = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* ignore */
    }
  };

  const empty = turns.length === 0;

  return (
    <div className="flex h-[calc(100vh-150px)] min-h-[520px] rounded-xl overflow-hidden border border-line">
      <ConversationSidebar
        list={conv.list}
        activeId={conv.activeId}
        onNew={() => {
          conv.create();
          setInput("");
          setErr(null);
        }}
        onOpen={conv.open}
        onDelete={conv.remove}
        onRename={conv.rename}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
      />

      <div className="flex-1 flex flex-col bg-panel/40 min-w-0">
        <div className="px-4 py-2 border-b border-line/60 flex items-center gap-3 flex-wrap text-xs">
          <div className="font-semibold text-slate-200 truncate max-w-[24rem]">
            {conv.active?.title ?? "New chat"}
          </div>
          <div className="flex gap-1">
            {filters.subject && <span className="badge">subject={filters.subject}</span>}
            {filters.book && <span className="badge">book={filters.book}</span>}
            {filters.chapter && <span className="badge">chapter={filters.chapter}</span>}
          </div>
          <label className="text-slate-400 flex items-center gap-2 ml-auto">
            agent
            <select
              className="select py-1"
              value={agent}
              onChange={(e) => setAgent(e.target.value as typeof agent)}
            >
              <option value="auto">🤖 auto-route</option>
              <option value="solver">🧮 Solver</option>
              <option value="teacher">📚 Teacher</option>
              <option value="diagram">🎨 Diagram</option>
              <option value="planner">📅 Planner</option>
              <option value="quizzer">❓ Quizzer</option>
            </select>
          </label>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6">
          {empty && (
            <div className="w-full h-full flex flex-col items-center justify-center gap-6">
              <div className="text-center">
                <div className="text-3xl font-semibold text-slate-100">Ask anything</div>
                <div className="text-slate-400 text-sm mt-1">
                  Grounded in your indexed JEE/NEET books — answers cite the source pages.
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex.title}
                    onClick={() => {
                      setInput(ex.prompt);
                      setTimeout(() => taRef.current?.focus(), 0);
                    }}
                    className="text-left card p-4 hover:bg-line/40 transition group"
                  >
                    <div className="text-xs uppercase tracking-wider text-slate-400 flex items-center gap-2">
                      <span className="text-base">{ex.emoji}</span>
                      <span>{ex.title}</span>
                    </div>
                    <div className="text-sm text-slate-200 mt-1 group-hover:text-white">
                      {ex.prompt}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="w-full space-y-5">
            {turns.map((t, i) => (
              <div
                key={i}
                className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  id={t.role === "assistant" ? `assistant-msg-${i}` : undefined}
                  className={
                    t.role === "user"
                      ? "max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 bg-indigo-500/15 border border-indigo-500/30 text-indigo-100"
                      : "w-full rounded-2xl rounded-bl-sm px-4 py-3 bg-panel border border-line text-slate-100 space-y-3"
                  }
                >
                  {t.role === "assistant" && (
                    <div className="flex flex-wrap gap-2 items-center text-xs text-slate-400">
                      {t.agentLabel && (
                        <span className="badge bg-indigo-500/15 border-indigo-500/30 text-indigo-200">
                          {t.agentLabel}
                        </span>
                      )}
                      {t.corrected && t.corrected.trim() && t.corrected !== t.content && (
                        <span className="italic">
                          Searched as: <span className="text-slate-300">"{t.corrected}"</span>
                        </span>
                      )}
                      {t.streaming && (
                        <span className="text-indigo-300 inline-flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
                          writing…
                        </span>
                      )}
                    </div>
                  )}

                  {t.role === "assistant" ? (
                    t.streaming ? (
                      <TypewriterStream text={t.content} streaming={true} />
                    ) : (
                      <MessageRenderer text={t.content} />
                    )
                  ) : (
                    <div className="whitespace-pre-wrap leading-relaxed">{t.content}</div>
                  )}


                  {t.role === "assistant" && !t.streaming && (
                    <div className="flex items-center gap-2 pt-2 border-t border-line/40">
                      {t.interactionId && (
                        <FeedbackButtons
                          interactionId={t.interactionId}
                          question={turns[i - 1]?.content || ""}
                          correctedQuery={t.corrected || ""}
                          answer={t.content}
                        />
                      )}
                      <button
                        className="btn"
                        onClick={() => copyAnswer(t.content)}
                        title="copy answer text"
                      >
                        ⧉ copy
                      </button>
                      {i === turns.length - 1 && (
                        <button
                          className="btn"
                          onClick={regenerate}
                          disabled={busy}
                          title="regenerate this answer"
                        >
                          ↻ regenerate
                        </button>
                      )}
                      <DownloadPdfButton
                        targetId={`assistant-msg-${i}`}
                        filename={`ragh-${(t.corrected || conv.active?.title || "answer").slice(0, 40).replace(/\s+/g, "-")}.pdf`}
                      />
                    </div>
                  )}
                </div>
              </div>
            ))}

            {err && (
              <div className="rounded-md border border-rose-500/40 bg-rose-500/10 text-rose-200 text-sm p-3">
                {err}
              </div>
            )}
          </div>
        </div>

        <div className="border-t border-line/60 p-3">
          <div className="w-full flex items-end gap-2">
            <textarea
              ref={taRef}
              className="textarea flex-1 resize-none"
              placeholder="Ask anything…  (Enter to send, Shift+Enter for newline)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={1}
              style={{ minHeight: 44, maxHeight: 220 }}
            />
            {busy ? (
              <button className="btn" onClick={stop} title="stop generating">
                ◼ stop
              </button>
            ) : (
              <button className="btn-primary" onClick={send} disabled={!input.trim()}>
                Send
              </button>
            )}
          </div>
          <div className="w-full mt-2 text-[11px] text-slate-500 flex items-center gap-3">
            <span>Enter ↵ to send · Shift+Enter for newline</span>
            <span className="ml-auto">user: {userId}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
