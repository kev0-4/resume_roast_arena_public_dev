"use client";

// The interviewer's "camera tile". There is no avatar to show -- Gemini's
// Live API returns audio and text only, no video (probed three ways, all
// dead ends) -- so this is what ChatGPT/Gemini voice mode do instead: a
// presence that reacts to the actual output waveform.
//
// The rings are driven straight from an AnalyserNode via rAF, writing to
// style on a ref. Deliberately NOT React state: this updates ~60x a second
// and re-rendering the tree at that rate would cost more than the whole
// audio pipeline.

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";

export function InterviewerPresence({
  amplitude,
  speaking,
  thinking,
  idle = false,
}: {
  amplitude: () => number;
  speaking: boolean;
  /** Connected, but nobody is talking -- waiting on the candidate. */
  thinking: boolean;
  /** Socket closed during an exercise round. Present and watching, but
   *  deliberately quiet -- the rings stop rather than idling forever. */
  idle?: boolean;
}) {
  const innerRef = useRef<HTMLDivElement>(null);
  const midRef = useRef<HTMLDivElement>(null);
  const outerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Nothing is playing during an exercise round, so there is no waveform
    // to follow. Skipping the rAF loop entirely keeps the main thread free
    // for the editor rather than animating a flat signal 60 times a second.
    if (idle) return;

    let frame = 0;
    // Smoothed so the rings glide instead of strobing on every buffer.
    let level = 0;

    const tick = () => {
      const target = amplitude();
      // Asymmetric smoothing: jump to a loud syllable quickly, fall away
      // slowly. Symmetric smoothing reads as laggy on speech onsets.
      level += (target - level) * (target > level ? 0.5 : 0.08);

      const scale = 1 + level * 0.35;
      if (innerRef.current) innerRef.current.style.transform = `scale(${scale})`;
      if (midRef.current) {
        midRef.current.style.transform = `scale(${1 + level * 0.6})`;
        midRef.current.style.opacity = `${0.35 + level * 0.4}`;
      }
      if (outerRef.current) {
        outerRef.current.style.transform = `scale(${1 + level * 0.95})`;
        outerRef.current.style.opacity = `${0.12 + level * 0.3}`;
      }
      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [amplitude, idle]);

  return (
    <div className="relative flex h-full w-full items-center justify-center">
      <div className="relative flex items-center justify-center">
        <div
          ref={outerRef}
          className="absolute h-44 w-44 rounded-full bg-brand-lime transition-colors duration-300 md:h-56 md:w-56"
        />
        <div
          ref={midRef}
          className="absolute h-32 w-32 rounded-full bg-brand-lime transition-colors duration-300 md:h-40 md:w-40"
        />
        {/* layoutId lets framer-motion morph this exact circle between the
            full-stage conversation view and the small tile in the exercise
            round, so the interviewer visibly travels instead of one element
            vanishing and another appearing. */}
        <motion.div
          layoutId="interviewer-presence"
          ref={innerRef}
          className={[
            "relative flex items-center justify-center rounded-full border-[3px] border-black shadow-[5px_5px_0_#000]",
            idle ? "h-16 w-16" : "h-24 w-24 md:h-32 md:w-32",
            speaking ? "bg-brand-lime" : "bg-white",
          ].join(" ")}
        >
          <span
            className={[
              "font-display uppercase tracking-tighter text-black",
              idle ? "text-xl" : "text-3xl md:text-4xl",
            ].join(" ")}
          >
            RR
          </span>
        </motion.div>
      </div>

      {!idle ? (
        <div className="absolute bottom-4 left-4 flex items-center gap-2 rounded-full border-2 border-black bg-white px-3 py-1.5 shadow-[3px_3px_0_#000]">
          <span
            className={[
              "h-2 w-2 rounded-full",
              speaking ? "bg-brand-lime" : thinking ? "animate-pulse bg-amber-400" : "bg-black/25",
            ].join(" ")}
          />
          <span className="font-mono text-[10px] font-black uppercase tracking-wide text-black">
            {speaking ? "Speaking" : thinking ? "Listening" : "Idle"}
          </span>
        </div>
      ) : null}
    </div>
  );
}
