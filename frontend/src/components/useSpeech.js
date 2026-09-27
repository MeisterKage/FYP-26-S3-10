/**
 * Read a list of sentences aloud with the device's own voice (Web Speech API).
 *
 * One utterance per sentence, spoken in turn: some browsers stop a long
 * utterance after about fifteen seconds, and speaking sentence by sentence
 * lets the page highlight what is being read and jump anywhere in the list.
 *
 * Every (re)start bumps a run counter, so the end or error event of a sentence
 * that was cancelled (by a jump, a speed change or leaving the page) is ignored
 * instead of advancing the queue a second time.
 */
import { useEffect, useRef, useState } from "react";

export const speechSupported =
  typeof window !== "undefined" &&
  "speechSynthesis" in window &&
  "SpeechSynthesisUtterance" in window;

function pickVoice(lang) {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang === lang) ||
    voices.find((v) => v.lang?.replace("_", "-") === lang) ||
    voices.find((v) => v.lang?.startsWith("en-GB")) ||
    voices.find((v) => v.lang?.startsWith("en")) ||
    null
  );
}

export function useSpeech({ lang = "en-AU", onPosition, onFinish } = {}) {
  // idle | speaking | paused
  const [state, setState] = useState("idle");
  const [index, setIndex] = useState(-1);
  const [rate, setRateState] = useState(1);
  const items = useRef([]);
  const rateRef = useRef(1);
  const run = useRef(0);
  const pos = useRef(-1);
  const positionCallback = useRef(onPosition);
  positionCallback.current = onPosition;
  const finishCallback = useRef(onFinish);
  finishCallback.current = onFinish;

  // Stop talking when the page that started it goes away.
  useEffect(
    () => () => {
      run.current += 1;
      if (speechSupported) window.speechSynthesis.cancel();
    },
    [],
  );

  function finish() {
    run.current += 1;
    pos.current = -1;
    setIndex(-1);
    setState("idle");
  }

  function sayFrom(i) {
    const synth = window.speechSynthesis;
    if (i < 0 || i >= items.current.length) {
      finish();
      // Reached the end, as opposed to being stopped.
      if (i > 0) finishCallback.current?.();
      return;
    }
    run.current += 1;
    const mine = run.current;
    pos.current = i;
    setIndex(i);
    setState("speaking");
    positionCallback.current?.(i);

    const u = new SpeechSynthesisUtterance(items.current[i]);
    const voice = pickVoice(lang);
    if (voice) u.voice = voice;
    u.lang = voice?.lang || lang;
    u.rate = rateRef.current;
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

  return {
    state,
    index,
    rate,
    /** Start reading `list` from sentence `from`. */
    play(list, from = 0) {
      items.current = list;
      sayFrom(from);
    },
    jump(i) {
      sayFrom(i);
    },
    pause() {
      window.speechSynthesis.pause();
      setState("paused");
    },
    resume() {
      const synth = window.speechSynthesis;
      synth.resume();
      setState("speaking");
      // Some browsers drop the queue while paused; pick up the same sentence.
      const mine = run.current;
      setTimeout(() => {
        if (run.current === mine && !synth.speaking) sayFrom(pos.current);
      }, 250);
    },
    stop() {
      window.speechSynthesis.cancel();
      finish();
    },
    setRate(next) {
      rateRef.current = next;
      setRateState(next);
      // A new rate applies from the start of the current sentence.
      if (pos.current >= 0) sayFrom(pos.current);
    },
  };
}
