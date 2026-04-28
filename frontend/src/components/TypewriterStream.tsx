import { useEffect, useRef, useState } from "react";

interface Props {
  /** The latest full text to display. Grows as tokens stream in. */
  text: string;
  /** While true, characters are revealed at typewriter speed. When it flips
   *  false (stream ended), the rest of the text snaps in immediately. */
  streaming: boolean;
  /** When false, shows `text` verbatim with no animation. */
  enabled?: boolean;
}

/** Reveals characters at a controlled pace, never falling more than a
 *  half-second behind the actual stream. Snaps to full text as soon as the
 *  stream finishes. */
export function TypewriterStream({ text, streaming, enabled = true }: Props) {
  const [shown, setShown] = useState(enabled ? "" : text);
  const rafRef = useRef<number | null>(null);

  // Streaming finished → snap to full text immediately so MessageRenderer
  // can render the complete Markdown / LaTeX.
  useEffect(() => {
    if (!streaming) setShown(text);
  }, [streaming, text]);

  // While streaming, advance shown.length toward text.length on each tick.
  useEffect(() => {
    if (!enabled || !streaming) return;
    if (shown.length >= text.length) return;

    const tick = () => {
      setShown((cur) => {
        if (cur.length >= text.length) return cur;
        const lag = text.length - cur.length;
        // Catch-up curve: reveal more chars per tick when farther behind.
        const step =
          lag > 200 ? Math.ceil(lag / 12) :
          lag > 80  ? 4 :
          lag > 30  ? 2 :
          1;
        return text.slice(0, cur.length + step);
      });
    };

    rafRef.current = window.setTimeout(tick, 18);
    return () => {
      if (rafRef.current != null) window.clearTimeout(rafRef.current);
    };
  }, [enabled, streaming, shown.length, text.length, text]);

  return (
    <>
      <span className="whitespace-pre-wrap leading-relaxed">{shown}</span>
      {streaming && (
        <span
          aria-hidden
          className="tw-cursor align-baseline ml-[1px] text-indigo-300"
        >
          ▋
        </span>
      )}
    </>
  );
}
