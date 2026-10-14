/**
 * Read a list of sentences aloud with the device's voice (Web Speech API),
 * with a timeline a slider can show and move.
 *
 * One utterance per sentence, spoken in turn: some browsers stop a long
 * utterance after about fifteen seconds, and speaking sentence by sentence
 * lets the page highlight what is being read and jump anywhere in the list.
 *
 * The browser gives no audio clock for synthesised speech, so the timeline is
 * an estimate from the length of each sentence and the speaking rate. It is
 * corrected at every sentence: each one starts at its own estimated offset, so
 * the time shown never drifts more than a sentence away from the voice.
 *
 * Every (re)start bumps a run counter, so the end or error event of a sentence
 * that was cancelled (by a jump, a speed change or leaving the page) is ignored
 * instead of advancing the queue a second time.
 */
import { useEffect, useMemo, useRef, useState } from "react";

export const speechSupported =
  typeof window !== "undefined" &&
  "speechSynthesis" in window &&
  "SpeechSynthesisUtterance" in window;

/** A soft, unhurried delivery: slightly below the browser's default pace. */
const BASE_RATE = 0.95;

// Voice names that are female on the common systems (Windows, Edge's natural
// voices, macOS and iOS, Chrome's Google voices), and the Mandarin and Malay
// ones. Matched before the male list, because "female" contains "male".
const FEMALE = new RegExp([
  "female", "woman", "zira", "hazel", "catherine", "natasha", "aria", "jenny", "sonia",
  "libby", "clara", "emma", "michelle", "samantha", "karen", "moira", "tessa", "fiona",
  "serena", "victoria", "susan", "kate", "allison", "ava", "nicky", "zoe", "ellie",
  "isla", "olivia", "molly", "freya", "maisie", "xiaoxiao", "xiaoyi", "xiaohan",
  "xiaomo", "xiaorui", "huihui", "yaoyao", "ting-ting", "tingting", "meijia", "mei-jia",
  "sin-ji", "yasmin", "amira", "google uk english female", "google us english",
].join("|"), "i");
const MALE = /\b(male|david|mark|george|ryan|guy|daniel|james|william|liam|thomas|rizwan|yunxi|yunyang|yunjian|kangkang|osman|alex|fred|oliver|arthur|aaron|gordon|lee|james|christopher|eric|roger|steffan|brian|davis|tony|andrew)\b/i;
const NATURAL = /natural|neural|online|enhanced|premium/i;

function score(voice, lang) {
  const want = lang.toLowerCase();
  const have = (voice.lang || "").toLowerCase().replace("_", "-");
  let s = 0;
  if (have === want) s += 8;
  else if (have.split("-")[0] === want.split("-")[0]) s += 6;
  else return -1; // never read Mandarin in an English voice, or the reverse
  if (FEMALE.test(voice.name)) s += 4;
  else if (MALE.test(voice.name)) s -= 4;
  if (NATURAL.test(voice.name)) s += 2; // the natural voices sound softer
  if (voice.localService) s += 1;
  return s;
}

/** The softest female voice the device has for this language, if any. */
export function pickVoice(lang) {
  let best = null;
  let bestScore = -1;
  for (const voice of window.speechSynthesis.getVoices()) {
    const s = score(voice, lang);
    if (s > bestScore) {
      best = voice;
      bestScore = s;
    }
  }
  return best;
}

const CJK = /[㐀-鿿豈-﫿]/g;

/** Estimated seconds to speak one sentence at normal speed. */
function seconds(text) {
  const cjk = (text.match(CJK) || []).length;
  const words = text.replace(CJK, " ").split(/\s+/).filter(Boolean).length;
  return words * (60 / 160) + cjk / 4.2 + 0.35;
}

/** Estimated running time of a list of sentences at normal speed, in seconds. */
export function estimate(list) {
  return list.reduce((t, text) => t + seconds(text), 0);
}

export function clock(total) {
  const s = Math.max(0, Math.round(total));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function useSpeech({ lang = "en-AU", items = [], onPosition, onFinish } = {}) {
  // idle | speaking | paused
  const [state, setState] = useState("idle");
  const [index, setIndex] = useState(-1);
  const [rate, setRateState] = useState(1);
  const [cursor, setCursor] = useState(0); // where Play starts when idle
  const [, setTick] = useState(0);

  const list = useRef(items);
  list.current = items;
  const rateRef = useRef(1);
  const run = useRef(0);
  const pos = useRef(-1);
  const startedAt = useRef(0);
  const pausedAt = useRef(0);
  const positionCallback = useRef(onPosition);
  positionCallback.current = onPosition;
  const finishCallback = useRef(onFinish);
  finishCallback.current = onFinish;

  // Seconds per sentence at normal speed, and where each one starts.
  const timing = useMemo(() => {
    const lengths = items.map(seconds);
    const starts = [];
    let t = 0;
    for (const len of lengths) {
      starts.push(t);
      t += len;
    }
    return { lengths, starts, total: t };
  }, [items]);

  // Stop talking when the page that started it goes away.
  useEffect(
    () => () => {
      run.current += 1;
      if (speechSupported) window.speechSynthesis.cancel();
    },
    [],
  );

  // A new text (another article or another mode) starts from the beginning.
  useEffect(() => setCursor(0), [items]);

  // While speaking, redraw a few times a second so the clock moves.
  useEffect(() => {
    if (state !== "speaking") return undefined;
    const timer = setInterval(() => setTick((t) => t + 1), 250);
    return () => clearInterval(timer);
  }, [state]);

  function finish() {
    run.current += 1;
    pos.current = -1;
    setIndex(-1);
    setState("idle");
  }

  function sayFrom(i) {
    const synth = window.speechSynthesis;
    if (i < 0 || i >= list.current.length) {
      finish();
      setCursor(0);
      // Reached the end, as opposed to being stopped.
      if (i > 0) finishCallback.current?.();
      return;
    }
    run.current += 1;
    const mine = run.current;
    pos.current = i;
    setIndex(i);
    setState("speaking");
    startedAt.current = performance.now();
    positionCallback.current?.(i);

    const u = new SpeechSynthesisUtterance(list.current[i]);
    const voice = pickVoice(lang);
    if (voice) u.voice = voice;
    u.lang = voice?.lang || lang;
    u.rate = BASE_RATE * rateRef.current;
    u.onstart = () => {
      if (run.current === mine) startedAt.current = performance.now();
    };
    u.onend = () => {
      if (run.current === mine) sayFrom(i + 1);
    };
    u.onerror = (event) => {
      if (run.current !== mine) return;
      if (event.error === "interrupted" || event.error === "canceled") return;
      sayFrom(i + 1);
    };

    const start = () => {
      if (run.current === mine) synth.speak(u);
    };
    // Chrome can drop a sentence queued in the same tick as a cancel.
    if (synth.speaking || synth.pending) {
      synth.cancel();
      setTimeout(start, 60);
    } else {
      start();
    }
  }

  /** The sentence that contains this moment (in seconds at the current speed). */
  function sentenceAt(time) {
    const t = time * rateRef.current;
    let i = 0;
    while (i + 1 < timing.starts.length && timing.starts[i + 1] <= t) i += 1;
    return i;
  }

  // Elapsed and total time at the current speed.
  const speed = rate || 1;
  let elapsed = (timing.starts[cursor] || 0) / speed;
  if (index >= 0) {
    const now = state === "paused" ? pausedAt.current : performance.now();
    const into = Math.max(0, (now - startedAt.current) / 1000);
    const within = Math.min(into, timing.lengths[index] / speed);
    elapsed = timing.starts[index] / speed + within;
  }

  return {
    state,
    index,
    rate,
    cursor,
    elapsed,
    total: timing.total / speed,
    /** Start reading, from the slider's position if it was moved. */
    play(from) {
      sayFrom(from ?? cursor);
    },
    jump(i) {
      sayFrom(i);
    },
    /** Set where Play will start, without starting (when idle). */
    cue(i) {
      if (state === "idle") setCursor(Math.max(0, Math.min(i, list.current.length - 1)));
    },
    /** Move to a moment on the timeline; keeps playing if it was. */
    seek(time) {
      const i = sentenceAt(time);
      if (state === "idle") setCursor(i);
      else sayFrom(i);
    },
    pause() {
      window.speechSynthesis.pause();
      pausedAt.current = performance.now();
      setState("paused");
    },
    resume() {
      const synth = window.speechSynthesis;
      synth.resume();
      startedAt.current += performance.now() - pausedAt.current;
      setState("speaking");
      // Some browsers drop the queue while paused; pick up the same sentence.
      const mine = run.current;
      setTimeout(() => {
        if (run.current === mine && !synth.speaking) sayFrom(pos.current);
      }, 250);
    },
    stop() {
      const at = pos.current;
      window.speechSynthesis.cancel();
      finish();
      // Stopping keeps the place, like an audio player's stop-and-hold.
      if (at >= 0) setCursor(at);
    },
    setRate(next) {
      rateRef.current = next;
      setRateState(next);
      // A new rate applies from the start of the current sentence.
      if (pos.current >= 0) sayFrom(pos.current);
    },
  };
}
