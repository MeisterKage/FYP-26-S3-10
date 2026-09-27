/**
 * "In brief": the key points of a long article, which a reader can also listen to.
 *
 * The points are the article's own sentences, chosen by the server, so the box
 * can never say anything the article does not. Narration comes in two modes:
 * "browser" speaks the text with the reader's own device voice (free, and the
 * text never leaves the device); "audio" plays a recorded file, for when a
 * text-to-speech service is connected on the server.
 */
import { useEffect, useRef, useState } from "react";

import { PauseIcon, SpeakerIcon, StopIcon } from "./Icon";

const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

function pickVoice(lang) {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang === lang) ||
    voices.find((v) => v.lang?.startsWith("en-GB")) ||
    voices.find((v) => v.lang?.startsWith("en")) ||
    null
  );
}

function useNarration({ title, points, voice }) {
  // idle | speaking | paused. `current` is the point being read, highlighted.
  const [state, setState] = useState("idle");
  const [current, setCurrent] = useState(-1);
  const alive = useRef(true);

  // Stop talking when the reader leaves the article.
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      window.speechSynthesis.cancel();
    };
  }, []);

  function speak() {
    const synth = window.speechSynthesis;
    synth.cancel();
    // One utterance per sentence: some browsers cut off a long utterance after
    // about fifteen seconds, and it lets the box follow along.
    const parts = [{ text: `${title}. In brief.`, index: -1 }, ...points.map((text, index) => ({ text, index }))];
    const chosen = pickVoice(voice?.lang || "en-AU");
    parts.forEach((part, i) => {
      const u = new SpeechSynthesisUtterance(part.text);
      if (chosen) u.voice = chosen;
      u.lang = chosen?.lang || voice?.lang || "en-AU";
      u.rate = voice?.rate || 1;
      u.onstart = () => alive.current && setCurrent(part.index);
      if (i === parts.length - 1) {
        u.onend = () => {
          if (!alive.current) return;
          setState("idle");
          setCurrent(-1);
        };
      }
      synth.speak(u);
    });
    setState("speaking");
  }

  function toggle() {
    const synth = window.speechSynthesis;
    if (state === "idle") speak();
    else if (state === "speaking") {
      synth.pause();
      setState("paused");
    } else {
      synth.resume();
      setState("speaking");
    }
  }

  function stop() {
    window.speechSynthesis.cancel();
    setState("idle");
    setCurrent(-1);
  }

  return {
    current,
    controls: (
      <div className="brief-controls">
        <button type="button" className="brief-listen" onClick={toggle}
          aria-label={state === "speaking" ? "Pause narration" : state === "paused" ? "Resume narration" : "Listen to the key points"}>
          {state === "speaking" ? <PauseIcon size={16} /> : <SpeakerIcon size={16} />}
          <span>{state === "speaking" ? "Pause" : state === "paused" ? "Resume" : "Listen"}</span>
        </button>
        {state !== "idle" && (
          <button type="button" className="brief-stop" onClick={stop} aria-label="Stop narration">
            <StopIcon size={16} />
          </button>
        )}
      </div>
    ),
  };
}

export function InBrief({ title, brief }) {
  const narration = brief.narration || {};
  const browser = narration.mode === "browser" && canSpeak;
  const spoken = useNarration({ title, points: brief.points, voice: narration.voice });

  return (
    <aside className="brief" aria-labelledby="brief-title">
      <div className="brief-head">
        <p className="label" id="brief-title">
          In brief <span className="brief-time">· {brief.readingMinutes} min read</span>
        </p>
        {browser && spoken.controls}
      </div>
      <ul className="brief-points">
        {brief.points.map((point, i) => (
          <li key={i} className={browser && spoken.current === i ? "is-reading" : undefined}>
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
