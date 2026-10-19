"use client";

// Adapted from Magic UI's Word Rotate registry component:
// https://magicui.design/r/word-rotate.json
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";

export function WordRotate({ words, paused = false }: { words: ReactNode[]; paused?: boolean }) {
  const [index, setIndex] = useState(0);
  const currentIndex = useRef(0);
  const remaining = useRef<number[]>([]);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    if (paused || reducedMotion || words.length < 2) return;
    const timer = window.setInterval(() => {
      // Draw without replacement so every phrase gets a turn before recycling.
      // Keep the first server-rendered phrase stable to avoid hydration shifts.
      if (remaining.current.length === 0) {
        remaining.current = words.map((_, position) => position)
          .filter((position) => position !== currentIndex.current);
      }
      const pick = Math.floor(Math.random() * remaining.current.length);
      const [next] = remaining.current.splice(pick, 1);
      currentIndex.current = next;
      setIndex(next);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [words, paused, reducedMotion]);

  return (
    <span aria-hidden="true" className="relative grid min-h-[2.6em] items-center overflow-hidden sm:min-h-[1.4em]">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={reducedMotion ? 0 : index}
          className="block"
          initial={{ opacity: 0, y: 20, filter: "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -20, filter: "blur(4px)" }}
          transition={{ duration: reducedMotion ? 0 : 0.35, ease: "easeOut" }}
        >
          {words[reducedMotion ? 0 : index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
