import { useState } from "react";

interface Props {
  /** Element ID to capture (the assistant message + its citations). */
  targetId: string;
  /** Used as the PDF filename. */
  filename?: string;
}

export function DownloadPdfButton({ targetId, filename = "ragh-answer.pdf" }: Props) {
  const [busy, setBusy] = useState(false);

  const onClick = async () => {
    const el = document.getElementById(targetId);
    if (!el) return;
    setBusy(true);
    try {
      // Lazy-load html2pdf to keep initial bundle small.
      const mod = await import("html2pdf.js");
      const html2pdf = (mod as { default: any }).default || (mod as any);
      await html2pdf()
        .set({
          margin: [12, 12, 14, 12],
          filename,
          image: { type: "jpeg", quality: 0.94 },
          html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff",
            // walk into anchors so figure links render as their <img>
            ignoreElements: (n: HTMLElement) => n.tagName === "BUTTON",
          },
          jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
          pagebreak: { mode: ["avoid-all", "css", "legacy"] },
        })
        .from(el)
        .save();
    } catch (e) {
      // best-effort fallback: open the print dialog
      window.print();
      console.error("html2pdf failed:", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      className="btn"
      onClick={onClick}
      disabled={busy}
      title="export this answer (with figures + math) to PDF"
    >
      {busy ? "exporting…" : "↓ download PDF"}
    </button>
  );
}
