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
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { NextIcon, PauseIcon, PlayIcon, PrevIcon, StopIcon } from "./Icon";
import { speechSupported, useSpeech } from "./useSpeech";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
const WPM = 160;

function clock(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

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

  // Every sentence in reading order, which chapter it belongs to, and the
  // words spoken before it (for the elapsed time).
  const book = useMemo(() => {
    const sentences = [];
    const owner = [];
    const starts = [];
    const before = [];
    let words = 0;
    chapters.forEach((chapter, ci) => {
      starts.push(sentences.length);
      chapter.parts.forEach((part, pi) => {
        sentences.push(part);
        owner.push([ci, pi]);
        before.push(words);
        words += part.split(/\s+/).length;
      });
    });
    return { sentences, owner, starts, before, words };
  }, [chapters]);

  const [saved, setSaved] = useState(() => {
    const n = readSaved(storageKey);
    return n < book.sentences.length ? n : -1;
  });
  const [viewing, setViewing] = useState(() => (saved > 0 ? book.owner[saved][0] : 0));

  const speech = useSpeech({
    lang: narration.voice?.lang || "en-AU",
    onPosition: (i) => {
      writeSaved(storageKey, i);
      setSaved(i);
    },
    onFinish: () => {
      writeSaved(storageKey, -1);
      setSaved(-1);
      setViewing(0);
    },
  });

  const playing = speech.index >= 0;
  const [chapterIndex, partIndex] = playing ? book.owner[speech.index] : [viewing, -1];
  const chapter = chapters[chapterIndex];
  const resumeHere = !playing && saved > 0 && book.owner[saved][0] === viewing;

  const elapsedWords = playing ? book.before[speech.index] : resumeHere ? book.before[saved] : 0;
  const pace = WPM * (speech.rate || 1);
  const elapsed = (elapsedWords / pace) * 60;
  const total = (book.words / pace) * 60;

  function playFrom(ci) {
    setViewing(ci);
    if (!canPlay) return;
    if (playing) speech.jump(book.starts[ci]);
    else speech.play(book.sentences, book.starts[ci]);
  }

  function toggle() {
    if (speech.state === "speaking") speech.pause();
    else if (speech.state === "paused") speech.resume();
    else speech.play(book.sentences, resumeHere ? saved : book.starts[viewing]);
  }

  function previous() {
    // Like any audio book: back to the start of this chapter first, then to the one before.
    const target = playing && partIndex > 0 ? chapterIndex : Math.max(0, chapterIndex - 1);
    if (playing) speech.jump(book.starts[target]);
    else setViewing(target);
  }

  function next() {
    const target = Math.min(chapters.length - 1, chapterIndex + 1);
    if (playing) speech.jump(book.starts[target]);
    else setViewing(target);
  }

  function startOver() {
    writeSaved(storageKey, -1);
    setSaved(-1);
    setViewing(0);
    if (canPlay) speech.play(book.sentences, 0);
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
          {canPlay ? "read by your device's voice" : "your browser cannot read aloud, so here is the text"}
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
            <div className="book-progress" role="progressbar" aria-label="Listening progress"
              aria-valuemin={0} aria-valuemax={Math.round(total)} aria-valuenow={Math.round(elapsed)}
              aria-valuetext={`${clock(elapsed)} of ${clock(total)}`}>
              <i style={{ width: `${total ? (elapsed / total) * 100 : 0}%` }} />
            </div>
            <p className="book-time">
              {clock(elapsed)} / {clock(total)}
              {resumeHere && (
                <>
                  {" · "}
                  <button type="button" className="link-quiet book-over" onClick={startOver}>
                    Start from the beginning
                  </button>
                </>
              )}
            </p>
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
        Article summaries are the writers&rsquo; own sentences, chosen automatically. Subscriber-only
        articles are summarised only for their subscribers, and republished articles are read
        from their own opening, unchanged.
      </p>
    </section>
  );
}
