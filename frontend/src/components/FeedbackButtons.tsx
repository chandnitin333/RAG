import { useState } from "react";
import { api } from "../api";

interface Props {
  interactionId: string;
  question: string;
  correctedQuery: string;
  answer: string;
}

export function FeedbackButtons({ interactionId }: Props) {
  const [rating, setRating] = useState<1 | -1 | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCorrection, setShowCorrection] = useState(false);
  const [correction, setCorrection] = useState("");

  const send = async (r: 1 | -1, correctedAnswer?: string) => {
    setBusy(true);
    try {
      await api.feedback({
        interaction_id: interactionId,
        rating: r,
        corrected_answer: correctedAnswer || null,
      });
      setRating(r);
      if (r === -1 && !correctedAnswer) setShowCorrection(true);
    } catch (e) {
      console.error("feedback failed", e);
    } finally {
      setBusy(false);
    }
  };

  const submitCorrection = async () => {
    if (!correction.trim()) {
      setShowCorrection(false);
      return;
    }
    await send(-1, correction.trim());
    setShowCorrection(false);
  };

  return (
    <div className="flex items-center gap-1">
      <button
        className={`btn ${rating === 1 ? "bg-emerald-500/20 border-emerald-500/40" : ""}`}
        onClick={() => send(1)}
        disabled={busy || rating !== null}
        title="this answer was helpful — keeps the (Q, A) pair as a positive training example"
      >
        👍
      </button>
      <button
        className={`btn ${rating === -1 ? "bg-rose-500/20 border-rose-500/40" : ""}`}
        onClick={() => send(-1)}
        disabled={busy || rating !== null}
        title="this answer was wrong — optionally provide a correction to use as training target"
      >
        👎
      </button>
      {showCorrection && (
        <div className="flex-1 flex items-center gap-1 ml-2">
          <input
            className="input flex-1 text-xs"
            placeholder="optional: write the answer you wish you'd gotten"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitCorrection()}
          />
          <button className="btn" onClick={submitCorrection}>save</button>
          <button className="btn" onClick={() => setShowCorrection(false)}>skip</button>
        </div>
      )}
    </div>
  );
}
