import { useEffect, useMemo, useRef, useState } from "react";
import mermaid from "mermaid";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { MathJax, MathJaxContext } from "better-react-mathjax";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  securityLevel: "loose",
  fontFamily: "ui-sans-serif, system-ui",
});

marked.setOptions({ gfm: true, breaks: false });

// MathJax configuration — same delimiters ChatGPT-style chat tools accept.
const MATHJAX_CONFIG = {
  loader: { load: ["[tex]/ams", "[tex]/color", "[tex]/cancel", "[tex]/mhchem"] },
  tex: {
    inlineMath: [
      ["$", "$"],
      ["\\(", "\\)"],
    ],
    displayMath: [
      ["$$", "$$"],
      ["\\[", "\\]"],
    ],
    packages: { "[+]": ["ams", "color", "cancel", "mhchem"] },
    processEscapes: true,
  },
  options: {
    renderActions: {
      addCss: [200, () => undefined, () => undefined],
    },
    skipHtmlTags: { "[-]": ["pre", "code"] },
  },
  startup: {
    typeset: false,
  },
};

// ─────────────────────────── code-fence segmentation ───────────────────────
interface Block {
  kind: "markdown" | "svg" | "mermaid" | "code";
  lang?: string;
  body: string;
}

const FENCE = /```(\w+)?\n([\s\S]*?)```/g;

function splitFences(input: string): Block[] {
  const out: Block[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = FENCE.exec(input)) !== null) {
    if (m.index > last) out.push({ kind: "markdown", body: input.slice(last, m.index) });
    const lang = (m[1] || "").toLowerCase();
    const body = m[2];
    if (lang === "svg") out.push({ kind: "svg", body });
    else if (lang === "mermaid") out.push({ kind: "mermaid", body });
    else out.push({ kind: "code", lang, body });
    last = m.index + m[0].length;
  }
  if (last < input.length) out.push({ kind: "markdown", body: input.slice(last) });
  return out;
}

// ─────────────────────────── markdown → safe HTML ───────────────────────────
/** Run marked on the source, but PRESERVE math delimiters so MathJax sees
 *  them in the final DOM. We escape the $..$ regions to placeholders before
 *  marked, then restore them after. */
function renderMarkdownPreservingMath(src: string): string {
  const slots: string[] = [];
  const protect = (re: RegExp) =>
    src.replace(re, (m) => {
      slots.push(m);
      return `@@MJX${slots.length - 1}@@`;
    });
  src = protect(/\$\$[\s\S]+?\$\$/g);
  src = protect(/\\\[[\s\S]+?\\\]/g);
  src = protect(/\\\([\s\S]+?\\\)/g);
  src = protect(/(^|[^\\$])\$[^\n$]+?\$/g); // crude inline $...$
  let html = marked.parse(src, { async: false }) as string;
  html = html.replace(/@@MJX(\d+)@@/g, (_, i) => slots[Number(i)] || "");
  return DOMPurify.sanitize(html, { ADD_TAGS: ["mjx-container"], ADD_ATTR: ["class", "style"] });
}

// ─────────────────────────── block components ──────────────────────────────
function MermaidBlock({ source }: { source: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    const id = `mmd-${Math.random().toString(36).slice(2, 10)}`;
    mermaid
      .render(id, source)
      .then(({ svg }) => {
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          setErr(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [source]);
  return (
    <div className="rounded-md border border-line bg-white p-2 overflow-x-auto">
      <div ref={ref} />
      {err && <div className="text-xs text-rose-300 mt-1">mermaid: {err}</div>}
    </div>
  );
}

function sanitizeSvg(svg: string): string {
  return svg
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son\w+="[^"]*"/gi, "")
    .replace(/\son\w+='[^']*'/gi, "")
    .replace(/javascript:/gi, "");
}

function SvgBlock({ source }: { source: string }) {
  return (
    <div
      className="rounded-md border border-line bg-white p-2 overflow-x-auto [&_svg]:w-full [&_svg]:h-auto"
      dangerouslySetInnerHTML={{ __html: sanitizeSvg(source) }}
    />
  );
}

function CodeBlock({ lang, source }: { lang?: string; source: string }) {
  return (
    <pre className="rounded-md border border-line bg-ink/60 p-3 overflow-x-auto text-xs">
      {lang && <div className="text-slate-500 mb-1">{lang}</div>}
      <code>{source}</code>
    </pre>
  );
}

function MarkdownBlock({ source }: { source: string }) {
  const html = useMemo(() => renderMarkdownPreservingMath(source), [source]);
  return (
    <MathJax dynamic hideUntilTypeset="first">
      <div
        className="prose-rendered leading-relaxed"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </MathJax>
  );
}

// ─────────────────────────── public API ─────────────────────────────────────
export function MessageRenderer({ text }: { text: string }) {
  const blocks = splitFences(text);
  return (
    <MathJaxContext version={3} config={MATHJAX_CONFIG}>
      <div className="space-y-3">
        {blocks.map((b, i) => {
          if (b.kind === "markdown") return <MarkdownBlock key={i} source={b.body} />;
          if (b.kind === "svg") return <SvgBlock key={i} source={b.body} />;
          if (b.kind === "mermaid") return <MermaidBlock key={i} source={b.body} />;
          return <CodeBlock key={i} lang={b.lang} source={b.body} />;
        })}
      </div>
    </MathJaxContext>
  );
}
