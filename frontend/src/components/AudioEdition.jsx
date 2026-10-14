/**
 * A monthly digest as an audio book.
 *
 * The server sends the edition as chapters (introduction, the month in brief,
 * one chapter per article with its key points, corrections, closing), each a
 * list of sentences. This plays them with the reader's own device voice, shows
 * the chapter being read with the current sentence marked, and lets the reader
 * jump between chapters, change speed, and pick up where they left off.
 *
 * Without speech support the edition is still here to read: the same chapters,
 * as text.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { NextIcon, PauseIcon, PlayIcon, PrevIcon, StopIcon } from "./Icon";
import { SpeechTimeline } from "./SpeechTimeline";
import { clock, speechSupported, useSpeech } from "./useSpeech";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

// The listening position is a per-reader convenience: kept in this browser
// only, and the page works the same when storage is unavailable.
function readSaved(key) {
  try {
    const n = Number(window.localStorage.getItem(key));
    return Number.isInteger(n) && n > 0 ? n : -1;
  } catch {
    return -1;
  }
}

function writeSaved(key, value) {
  try {
    if (value > 0) window.localStorage.setItem(key, String(value));
    else window.localStorage.removeItem(key);
  } catch {
    /* storage blocked: nothing to remember */
  }
}

export function AudioEdition({ listen, topic, monthLabel, storageKey }) {
  const chapters = listen.chapters;
  const narration = listen.narration || {};
  const canPlay = narration.mode === "browser" && speechSupported;

  // Every sentence in reading order, and which chapter it belongs to.
  const book = useMemo(() => {
    const sentences = [];
    const owner = [];
    const starts = [];
    chapters.forEach((chapter, ci) => {
      starts.push(sentences.length);
      chapter.parts.forEach((part, pi) => {
        sentences.push(part);
        owner.push([ci, pi]);
      });
    });
    return { sentences, owner, starts };
  }, [chapters]);

  const speech = useSpeech({
    lang: narration.voice?.lang || "en-AU",
    items: book.sentences,
    onPosition: (i) => writeSaved(storageKey, i),
    onFinish: () => writeSaved(storageKey, -1),
  });

  // Pick up where this reader stopped last time.
  useEffect(() => {
    const saved = readSaved(storageKey);
    if (saved > 0 && saved < book.sentences.length) speech.cue(saved);
    // Once, when the edition loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, book]);

  const playing = speech.index >= 0;
  // Playing: the sentence being read. Stopped: where Play will start.
  const at = playing ? speech.index : speech.cursor;
  const [chapterIndex, partIndex] = book.owner[at] || [0, 0];
  const chapter = chapters[chapterIndex];
  const resumeHere = !playing && speech.cursor > 0;

  function playFrom(ci) {
    if (!canPlay) {
      speech.cue(book.starts[ci]);
      return;
    }
    if (playing) speech.jump(book.starts[ci]);
    else speech.play(book.starts[ci]);
  }

  function toggle() {
    if (speech.state === "speaking") speech.pause();
    else if (speech.state === "paused") speech.resume();
    else speech.play();
  }

  function previous() {
    // Like any audio book: back to the start of this chapter first, then to the one before.
    const target = partIndex > 0 ? chapterIndex : Math.max(0, chapterIndex - 1);
    if (playing) speech.jump(book.starts[target]);
    else speech.cue(book.starts[target]);
  }

  function next() {
    const target = Math.min(chapters.length - 1, chapterIndex + 1);
    if (playing) speech.jump(book.starts[target]);
    else speech.cue(book.starts[target]);
  }

  function startOver() {
    writeSaved(storageKey, -1);
    if (canPlay) speech.play(0);
  }

  const playLabel =
    speech.state === "speaking" ? "Pause" : speech.state === "paused" ? "Resume"
      : resumeHere ? "Resume" : "Play";

  return (
    <section className="book" aria-labelledby="book-title">
      <header className="book-head">
        <p className="label">Audio edition</p>
        <h2 className="heading mt-3" id="book-title">
          Listen to {topic}, {monthLabel}
        </h2>
        <p className="meta mt-3">
          {chapters.length} chapters · about {listen.minutes} min at normal speed ·{" "}
          {canPlay ? "read aloud in a soft voice" : "your browser cannot read aloud, so here is the text"}
        </p>
      </header>

      {canPlay && (
        <div className="book-controls">
          <div className="book-buttons">
            <button type="button" className="book-btn" onClick={previous}
              aria-label="Previous chapter" disabled={chapterIndex === 0 && partIndex <= 0}>
              <PrevIcon size={18} />
            </button>
            <button type="button" className="book-btn book-btn--play" onClick={toggle}
              aria-label={`${playLabel} the audio edition`}>
              {speech.state === "speaking" ? <PauseIcon size={20} /> : <PlayIcon size={20} />}
            </button>
            <button type="button" className="book-btn" onClick={next}
              aria-label="Next chapter" disabled={chapterIndex === chapters.length - 1}>
              <NextIcon size={18} />
            </button>
            {speech.state !== "idle" && (
              <button type="button" className="book-btn" onClick={speech.stop}
                aria-label="Stop and keep my place">
                <StopIcon size={16} />
              </button>
            )}
          </div>
          <div className="book-progress-wrap">
            <SpeechTimeline speech={speech} label="Position in the audio edition" />
            {resumeHere && (
              <p className="book-time">
                <button type="button" className="link-quiet book-over" onClick={startOver}>
                  Start from the beginning
                </button>
              </p>
            )}
          </div>
          <label className="book-speed">
            <span>Speed</span>
            <select value={speech.rate} onChange={(e) => speech.setRate(Number(e.target.value))}>
              {SPEEDS.map((s) => (
                <option key={s} value={s}>{s}×</option>
              ))}
            </select>
          </label>
        </div>
      )}

      <div className="book-body">
        <nav className="book-contents" aria-label="Chapters">
          <p className="label">Contents</p>
          <ol>
            {chapters.map((c, ci) => (
              <li key={c.id}>
                <button type="button" onClick={() => playFrom(ci)}
                  className={ci === chapterIndex ? "is-current" : undefined}
                  aria-current={ci === chapterIndex ? "true" : undefined}>
                  <span className="book-num">{ci + 1}</span>
                  <span className="book-name">{c.title}</span>
                  <span className="book-dur">{clock(c.seconds / (speech.rate || 1))}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <article className="book-reader">
          <p className="label">
            Chapter {chapterIndex + 1} of {chapters.length}
            {playing && speech.state === "speaking" && <span className="book-live"> · Now reading</span>}
          </p>
          <h3 className="book-chapter mt-3">{chapter.title}</h3>
          <div className="book-text mt-4">
            {chapter.parts.map((part, pi) => (
              <p key={pi} className={playing && pi === partIndex ? "is-reading" : undefined}>
                {part}
              </p>
            ))}
          </div>
          {narration.mode === "audio" && narration.chapters?.[chapter.id] && (
            <audio className="brief-audio" controls preload="none" src={narration.chapters[chapter.id]}>
              Your browser cannot play this recording.
            </audio>
          )}
          {chapter.slug && (
            <p className="mt-5">
              <Link className="link-quiet book-read" to={`/articles/${chapter.slug}`}>
                Read the full article
              </Link>
            </p>
          )}
        </article>
      </div>

      <p className="book-note">
        Article summaries are AI generated. Subscriber-only articles are summarised only for their
        subscribers.
      </p>
    </section>
  );
}
