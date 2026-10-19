"use client";

export function CookieSettingsTrigger() {
  return (
    <button
      type="button"
      className="text-left text-muted-foreground transition hover:text-foreground"
      onClick={() => window.dispatchEvent(new Event("techinn-open-cookie-settings"))}
    >
      Cookie settings
    </button>
  );
}

