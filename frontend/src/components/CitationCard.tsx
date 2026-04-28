import { api } from "../api";
import type { Citation } from "../types";
import { MessageRenderer } from "./MessageRenderer";

interface Props {
  citation: Citation;
}

/** Light client-side polish on top of the backend's symbol-remap. */
function bookify(s: string): string {
  if (!s) return "";
  return (
    s
      // any private-use leftover the backend missed
      .replace(/[-]/g, "")
      .replace(/[ \t]{2,}/g, " ")
      .replace(/(\w)-\n(\w)/g, "$1$2")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/([a-z,;:])\n(?=[a-z])/g, "$1 ")
      .trim()
  );
}

export function CitationCard({ citation }: Props) {
  const isImageChunk = citation.kind === "image";

  const directImageUrl = isImageChunk && citation.image_url
    ? api.figureUrl(citation.image_url)
    : null;

  const content = bookify(citation.content || citation.preview || "");

  return (
    <article className="rounded-md bg-[#1f2330] text-white border border-[#2a3040] shadow-sm p-5 space-y-3">

      {/* Image chunk → render the figure inline, with OCR caption underneath */}
      {directImageUrl && (
        <figure className="space-y-2">
          <a
            href={directImageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="block rounded-sm overflow-hidden border border-[#2a3040] bg-white hover:ring-2 hover:ring-indigo-400/40 transition"
          >
            <img
              src={directImageUrl}
              alt={citation.ocr_text || "figure"}
              className="w-full"
              loading="lazy"
            />
          </a>
          {citation.ocr_text && citation.ocr_text.trim() && (
            <figcaption className="text-xs italic text-slate-400 text-center">
              {citation.ocr_text.trim()}
            </figcaption>
          )}
        </figure>
      )}

      {/* Text chunk → render as HTML through the same pipeline as chat answers
          (Markdown + KaTeX + SVG/Mermaid). Dark gray bg, white text. */}
      {!directImageUrl && content && (
        <div
          className="prose-rendered"
          style={{
            color: "#ffffff",
            lineHeight: 1.7,
            fontSize: "15px",
          }}
        >
          <MessageRenderer text={content} />
        </div>
      )}
    </article>
  );
}
