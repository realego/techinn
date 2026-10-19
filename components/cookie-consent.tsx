"use client";

import Link from "next/link";
import { Cookie } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

const CONSENT_KEY = "techinn-cookie-consent-v1";
const META_PIXEL_ID = "2201018497485737";

type MetaPixelFunction = ((...args: unknown[]) => void) & {
  queue?: unknown[];
};

declare global {
  interface Window {
    fbq?: MetaPixelFunction;
  }
}

type ConsentChoice = "accepted" | "rejected";

function loadMetaPixel() {
  if (typeof window === "undefined" || window.fbq) return;

  const fbq: MetaPixelFunction = function (...args: unknown[]) {
    // Meta's queue is consumed by the script after it loads.
    (fbq as typeof fbq & { queue?: unknown[] }).queue?.push(args);
  };
  fbq.queue = [];
  window.fbq = fbq;

  const script = document.createElement("script");
  script.async = true;
  script.src = "https://connect.facebook.net/en_US/fbevents.js";
  script.dataset.techinnConsent = "advertising";
  document.head.appendChild(script);
  window.fbq("init", META_PIXEL_ID);
  window.fbq("track", "PageView");
}

function disableMetaPixel() {
  if (typeof window === "undefined") return;
  document.querySelectorAll('script[data-techinn-consent="advertising"]').forEach((script) => script.remove());
  delete window.fbq;
}

export function CookieConsent() {
  const [choice, setChoice] = useState<ConsentChoice | null>(null);
  const [open, setOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showFloating, setShowFloating] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(CONSENT_KEY) as ConsentChoice | null;
    setChoice(saved === "accepted" || saved === "rejected" ? saved : null);
    setShowFloating(saved === "accepted" || saved === "rejected");
    if (saved === "accepted") loadMetaPixel();
  }, []);

  useEffect(() => {
    function openCookieSettings() {
      setOpen(true);
      setShowFloating(true);
    }
    window.addEventListener("techinn-open-cookie-settings", openCookieSettings);
    return () => window.removeEventListener("techinn-open-cookie-settings", openCookieSettings);
  }, []);

  useEffect(() => {
    if (!choice || open || !showFloating) return;
    const timeout = window.setTimeout(() => setShowFloating(false), 15000);
    return () => window.clearTimeout(timeout);
  }, [choice, open, showFloating]);

  function saveConsent(next: ConsentChoice) {
    window.localStorage.setItem(CONSENT_KEY, next);
    setChoice(next);
    setOpen(false);
    setSettingsOpen(false);
    setShowFloating(true);
    if (next === "accepted") loadMetaPixel();
    else disableMetaPixel();
    if (next === "accepted") window.dispatchEvent(new Event("techinn-consent-accepted"));
  }

  if (choice && !open && !showFloating) return null;

  if (choice && !open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
      className="fixed bottom-2 right-2 z-50 rounded-full border border-orange-300/70 bg-background/95 px-2.5 py-1.5 text-[11px] font-medium text-foreground shadow-lg backdrop-blur transition hover:border-orange-500 hover:text-orange-500 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-orange-500"
      >
        Cookie settings
      </button>
    );
  }

  return (
    <aside
      aria-label="Cookie preferences"
      className="fixed inset-x-2 bottom-2 z-50 mx-auto max-w-5xl rounded-lg border border-orange-300/60 bg-background/95 px-3 py-2.5 shadow-xl backdrop-blur-md dark:border-orange-700/60 sm:inset-x-4 sm:px-4 sm:py-3"
    >
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 max-w-3xl space-y-0.5">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground"><Cookie aria-hidden="true" className="size-4 text-orange-500" /> Cookies &amp; Privacy</p>
          {detailsOpen ? (
            <>
              <p className="text-xs leading-4 text-muted-foreground">
                TechInn uses essential cookies to keep the site secure. With your permission, we also use Meta measurement cookies to understand campaigns and improve our services. You can change this choice any time in Cookie settings.
              </p>
              <Link href="/privacy/" className="text-[11px] font-medium text-orange-500 underline underline-offset-2 hover:text-orange-400">
                Read our privacy policy
              </Link>
            </>
          ) : (
            <div className="flex min-w-0 items-center gap-2 text-xs leading-4 text-muted-foreground">
              <p className="min-w-0 truncate">Essential cookies keep TechInn secure; optional Meta measurement cookies need your permission.</p>
              <button type="button" className="shrink-0 font-medium text-orange-500 underline underline-offset-2 hover:text-orange-400" onClick={() => setDetailsOpen(true)}>
                Read more
              </button>
            </div>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5 sm:justify-end">
          <Button type="button" size="xs" variant="ghost" onClick={() => setSettingsOpen((value) => !value)}>
            Settings
          </Button>
          <Button type="button" size="xs" variant="outline" onClick={() => saveConsent("rejected")}>
            Reject
          </Button>
          <Button type="button" size="xs" className="min-w-32 px-5" onClick={() => saveConsent("accepted")}>
            Accept
          </Button>
        </div>
      </div>
      {settingsOpen && (
        <div className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <p><strong className="text-foreground">Essential cookies</strong> are always active because sign-in, cart, security, and checkout depend on them.</p>
            <p><strong className="text-foreground">Meta measurement</strong> is optional and stays off until you accept.</p>
          </div>
        </div>
      )}
    </aside>
  );
}
