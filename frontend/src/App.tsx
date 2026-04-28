import { useState } from "react";
import { StatsBar } from "./components/StatsBar";
import { ChatPanel } from "./components/ChatPanel";
import { FilterPanel } from "./components/FilterPanel";
import { IngestPanel } from "./components/IngestPanel";
import { UploadPanel } from "./components/UploadPanel";
import { InsightsPanel } from "./components/InsightsPanel";
import type { QueryFilters } from "./types";

type Tab = "chat" | "insights" | "ingest" | "upload";

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  const [filters, setFilters] = useState<QueryFilters>({});

  return (
    <div className="min-h-full">
      <header className="border-b border-line/60 bg-ink/40 backdrop-blur sticky top-0 z-10">
        <div className="px-6 py-4 flex items-center gap-4">
          <div className="text-lg font-semibold tracking-tight">
            RAGH <span className="text-slate-500 font-normal">— ask your books</span>
          </div>
          <nav className="flex gap-1 ml-6">
            {(["chat", "insights", "ingest", "upload"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-md text-sm transition ${
                  tab === t
                    ? "bg-indigo-500/20 text-indigo-200 border border-indigo-500/30"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {t}
              </button>
            ))}
          </nav>
          <div className="ml-auto text-xs text-slate-500">v0.2 · self-hosted</div>
        </div>
      </header>

      <main className="px-6 py-6 space-y-4">
        <StatsBar />

        {tab === "chat" && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">
            <ChatPanel filters={filters} />
            <div className="space-y-4">
              <FilterPanel value={filters} onChange={setFilters} />
              <InsightsPanel />
            </div>
          </div>
        )}

        {tab === "insights" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <InsightsPanel />
            <div className="card p-4 text-sm text-slate-400 leading-relaxed">
              <div className="font-semibold text-slate-200 mb-2">
                What's tracked
              </div>
              <ul className="list-disc pl-5 space-y-1">
                <li>Every question you ask is logged with its subject/book/chapter and the agent that answered.</li>
                <li>Chapters with 3+ questions are flagged as your current focus areas.</li>
                <li>"Suggested focus" turns those into concrete revision tasks.</li>
                <li>Your anonymous user ID is stored in this browser only — no account needed.</li>
              </ul>
            </div>
          </div>
        )}

        {tab === "ingest" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <IngestPanel />
            <div className="card p-4 text-sm text-slate-400 leading-relaxed">
              <div className="font-semibold text-slate-200 mb-2">
                What "ingest corpus" does
              </div>
              <ol className="list-decimal pl-5 space-y-1">
                <li>
                  Walks <code>Book Mapping/</code> and <code>Command Capsule/</code>{" "}
                  in place — no files are moved.
                </li>
                <li>Builds a manifest with subject / book / chapter metadata.</li>
                <li>
                  For each file: extract text (PDF → DOCX → image OCR), chunk,
                  embed with <code>bge-small</code>, write to your vector DB.
                </li>
                <li>
                  Saves progress to <code>ingest_state.json</code> so you can resume.
                </li>
              </ol>
            </div>
          </div>
        )}

        {tab === "upload" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <UploadPanel />
            <div className="card p-4 text-sm text-slate-400 leading-relaxed">
              <div className="font-semibold text-slate-200 mb-2">
                Use upload for one-off documents
              </div>
              <p>
                Anything you upload here gets the metadata{" "}
                <span className="badge">subject: Uploaded</span> and{" "}
                <span className="badge">book: User Upload</span>, so you can filter
                them in queries the same way as corpus material.
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
