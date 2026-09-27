/**
 * "In brief": the key points of a long article, which a reader can also listen to.
 *
 * The points are the article's own sentences, chosen by the server, so the box
 * can never say anything the article does not. Narration comes in two modes:
 * "browser" speaks the text with the reader's own device voice (free, and the
 * text never leaves the device); "audio" plays a recorded file, for when a
 * text-to-speech service is connected on the server.
 */
import { PauseIcon, SpeakerIcon, StopIcon } from "./Icon";
import { speechSupported, useSpeech } from "./useSpeech";

export function InBrief({ title, brief }) {
  const narration = brief.narration || {};
  const browser = narration.mode === "browser" && speechSupported;
  const speech = useSpeech({ lang: narration.voice?.lang || "en-AU" });
  // Sentence 0 is the headline; the points follow it.
  const current = speech.index - 1;

  function toggle() {
    if (speech.state === "idle") speech.play([`${title}. In brief.`, ...brief.points]);
    else if (speech.state === "speaking") speech.pause();
    else speech.resume();
  }

  const label =
    speech.state === "speaking" ? "Pause" : speech.state === "paused" ? "Resume" : "Listen";

  return (
    <aside className="brief" aria-labelledby="brief-title">
      <div className="brief-head">
        <p className="label" id="brief-title">
          In brief <span className="brief-time">· {brief.readingMinutes} min read</span>
        </p>
        {browser && (
          <div className="brief-controls">
            <button type="button" className="brief-listen" onClick={toggle}
              aria-label={speech.state === "idle" ? "Listen to the key points" : `${label} narration`}>
              {speech.state === "speaking" ? <PauseIcon size={16} /> : <SpeakerIcon size={16} />}
              <span>{label}</span>
            </button>
            {speech.state !== "idle" && (
              <button type="button" className="brief-stop" onClick={speech.stop}
                aria-label="Stop narration">
                <StopIcon size={16} />
              </button>
            )}
          </div>
        )}
      </div>
      <ul className="brief-points">
        {brief.points.map((point, i) => (
          <li key={i} className={browser && current === i ? "is-reading" : undefined}>
            {point}
          </li>
        ))}
      </ul>
      {narration.mode === "audio" && narration.url && (
        <audio className="brief-audio" controls preload="none" src={narration.url}>
          Your browser cannot play this recording.
        </audio>
      )}
      <p className="brief-method">{brief.method}</p>
    </aside>
  );
}
