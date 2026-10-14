/**
 * The listening timeline: elapsed time, a slider to move through the reading,
 * and the total. Times are estimates (see useSpeech), corrected at every
 * sentence. Dragging moves on release, so the voice does not stutter through
 * every sentence the thumb passes.
 */
import { useState } from "react";

import { clock } from "./useSpeech";

export function SpeechTimeline({ speech, label = "Listening position" }) {
  const [drag, setDrag] = useState(null);
  const total = Math.max(1, speech.total);
  const value = drag ?? Math.min(speech.elapsed, total);
  const commit = () => {
    if (drag != null) speech.seek(drag);
    setDrag(null);
  };

  return (
    <div className="timeline">
      <span className="timeline-time">{clock(value)}</span>
      <input
        type="range"
        className="timeline-range"
        min={0}
        max={total}
        step={0.5}
        value={value}
        style={{ "--pct": `${(value / total) * 100}%` }}
        onChange={(e) => setDrag(Number(e.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={commit}
        aria-label={label}
        aria-valuetext={`${clock(value)} of ${clock(total)}`}
      />
      <span className="timeline-time">{clock(total)}</span>
    </div>
  );
}
