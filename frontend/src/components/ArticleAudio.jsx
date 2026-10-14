/**
 * Listen to an article: its key points, or the whole thing.
 *
 * One player for both, so the two can never talk over each other. "Key
 * points" reads the In brief box and marks the point being read; "Full
 * article" reads every paragraph and subheading of the article as published,
 * unchanged, marking the paragraph being read and keeping it in view.
 *
 * The full text is read from the article on the page rather than sent twice,
 * so what is heard is always exactly what is shown. A subscriber-only article
 * a reader cannot open has no body on the page, and so no full reading.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { PauseIcon, PlayIcon, StopIcon } from "./Icon";
import { InBrief } from "./InBrief";
import { SpeechTimeline } from "./SpeechTimeline";
import { estimate, speechSupported, useSpeech } from "./useSpeech";
import { useI18n } from "../i18n";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
// Ends a sentence at . ! or ? (and a closing quote) before a capital or a quote.
// Chinese ends a sentence at 。！？ with no space after it.
const SENTENCE_END = /(?<=[.!?])["”’]?\s+(?=["“‘A-Z0-9])|(?<=[。！？])["”’]?/;

function sentences(text) {
  return text.split(SENTENCE_END).map((s) => s.trim()).filter(Boolean);
}

function minutes(parts, rate = 1) {
  return Math.max(1, Math.round(estimate(parts) / 60 / rate));
}

/** Each sentence of the article body, and the paragraph element it belongs to. */
function readBody(container) {
  const items = [];
  const blocks = [];
  if (!container) return { items, blocks };
  for (const block of container.children) {
    const text = block.textContent.replace(/\s+/g, " ").trim();
    if (!text) continue;
    const at = blocks.push(block) - 1;
    // A subheading is read as one line; a paragraph sentence by sentence.
    const parts = /^H[1-6]$/.test(block.tagName) ? [text] : sentences(text);
    for (const part of parts) items.push({ text: part, block: at });
  }
  return { items, blocks };
}

export function ArticleAudio({ title, brief, proseRef, bodyKey, voiceLang = "en-AU" }) {
  const { t } = useI18n();
  const [mode, setMode] = useState(brief ? "brief" : "full");
  const [body, setBody] = useState({ items: [], blocks: [] });
  const marked = useRef(null);

  // The article body is rendered by the page; read it once it is there.
  useEffect(() => {
    setBody(readBody(proseRef.current));
  }, [proseRef, bodyKey]);

  const briefParts = useMemo(
    () => (brief ? [`${title}. ${t("listen.inBrief")}`, ...brief.points] : []),
    [brief, title, t],
  );
  const fullParts = useMemo(() => [`${title}.`, ...body.items.map((i) => i.text)], [body, title]);
  const parts = mode === "brief" ? briefParts : fullParts;
  const speech = useSpeech({ lang: voiceLang, items: parts });
  const playing = speech.state !== "idle";

  // Mark the paragraph being read in the article itself, and keep it in view.
  useEffect(() => {
    marked.current?.classList.remove("is-reading");
    marked.current = null;
    if (mode !== "full" || speech.index < 1) return;
    const block = body.blocks[body.items[speech.index - 1]?.block];
    if (!block) return;
    block.classList.add("is-reading");
    marked.current = block;
    const box = block.getBoundingClientRect();
    if (box.top < 80 || box.bottom > window.innerHeight) {
      const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      block.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
    }
  }, [mode, speech.index, body]);

  // Leaving the page or switching mode clears the mark.
  useEffect(() => () => marked.current?.classList.remove("is-reading"), []);

  const canPlay = speechSupported && (brief?.narration?.mode ?? "browser") === "browser";
  const hasFull = body.items.length > 0;
  if (!canPlay || (!brief && !hasFull)) {
    return brief ? <InBrief brief={brief} current={-1} /> : null;
  }

  function choose(next) {
    if (next === mode) return;
    speech.stop();
    setMode(next);
  }

  function toggle() {
    if (speech.state === "speaking") speech.pause();
    else if (speech.state === "paused") speech.resume();
    else speech.play();
  }

  const label = speech.state === "speaking" ? t("listen.pause")
    : speech.state === "paused" ? t("listen.resume") : t("listen.listen");

  return (
    <>
      <div className="listen" role="group" aria-label={t("listen.group")}>
        <button type="button" className="listen-play" onClick={toggle}
          aria-label={`${label}: ${mode === "brief" ? t("listen.keyPoints") : t("listen.fullArticle")}`}>
          {speech.state === "speaking" ? <PauseIcon size={18} /> : <PlayIcon size={18} />}
          <span>{label}</span>
        </button>

        <div className="listen-modes" role="radiogroup" aria-label={t("listen.modes")}>
          {brief && (
            <button type="button" role="radio" aria-checked={mode === "brief"}
              className="listen-mode" onClick={() => choose("brief")}>
              {t("listen.keyPoints")} <span className="listen-time">{t("listen.min", { n: minutes(briefParts, speech.rate) })}</span>
            </button>
          )}
          {hasFull && (
            <button type="button" role="radio" aria-checked={mode === "full"}
              className="listen-mode" onClick={() => choose("full")}>
              {t("listen.fullArticle")} <span className="listen-time">{t("listen.min", { n: minutes(fullParts, speech.rate) })}</span>
            </button>
          )}
        </div>

        <div className="listen-end">
          {playing && (
            <button type="button" className="listen-stop" onClick={speech.stop}
              aria-label={t("listen.stop")}>
              <StopIcon size={16} />
            </button>
          )}
          <label className="listen-speed">
            <span className="sr-only">{t("listen.speed")}</span>
            <select value={speech.rate} onChange={(e) => speech.setRate(Number(e.target.value))}
              aria-label={t("listen.speed")}>
              {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
          </label>
        </div>
      </div>

      <SpeechTimeline speech={speech}
        label={mode === "brief" ? t("listen.posBrief") : t("listen.posArticle")} />

      {brief && <InBrief brief={brief} current={mode === "brief" ? speech.index - 1 : -1} />}
    </>
  );
}
