"use client";

import { Pause, Play } from "lucide-react";
import { useState } from "react";

import { WordRotate } from "@/components/magicui/word-rotate";

const accent = "text-orange-600 dark:text-orange-400";
const phrases = [
  <>Find <span className={accent}>your domain</span></>,
  <>Welcome to <span className={accent}>TechInn</span></>,
  <>Make your business <span className={accent}>stand out.</span></>,
  <>Your next big idea <span className={accent}>starts here.</span></>,
  <>Big dreams. <span className={accent}>Small beginnings.</span></>,
  <>Your business. <span className={accent}>Your own domain.</span></>,
  <>A local name. <span className={accent}>A global vision.</span></>,
  <>Give your website <span className={accent}>a home.</span></>,
  <>Hosting for <span className={accent}>your next chapter.</span></>,
  <>Room to launch. <span className={accent}>Space to grow.</span></>,
  <>Your domain. <span className={accent}>Your business email.</span></>,
  <>Make every email <span className={accent}>look the part.</span></>,
  <>Your website, <span className={accent}>from just $60.</span></>,
  <>Turn visitors <span className={accent}>into customers.</span></>,
  <>An app idea? <span className={accent}>Let’s build it.</span></>,
  <>Put your business <span className={accent}>in their pocket.</span></>,
  <>Hello, dreamer. <span className={accent}>Let’s get online.</span></>,
  <>Start small. <span className={accent}>Think bigger.</span></>,
];

export function HomeDomainHeading() {
  const [paused, setPaused] = useState(false);
  return (
    <div className="relative mx-auto mb-5 max-w-3xl px-8">
      <h2 className="text-xl leading-tight font-semibold tracking-tight sm:text-3xl">
        <span className="sr-only">Welcome to TechInn. Find your domain and explore web hosting, business email, website design, and app development.</span>
        <WordRotate words={phrases} paused={paused} />
      </h2>
      <button
        type="button"
        onClick={() => setPaused((value) => !value)}
        aria-label={paused ? "Resume headline animation" : "Pause headline animation"}
        aria-pressed={paused}
        className="text-muted-foreground hover:text-foreground focus-visible:ring-ring absolute top-1/2 right-0 flex size-8 -translate-y-1/2 items-center justify-center rounded-full transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:outline-none motion-reduce:hidden"
      >
        {paused ? <Play className="size-3" /> : <Pause className="size-3" />}
      </button>
    </div>
  );
}
