"use client"

import { usePathname } from "next/navigation"
import { useSyncExternalStore } from "react"

export function safeReturnPath(value: string | null, fallback = "/dashboard/") {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\x00-\x1f\x7f]/.test(value)) return fallback
  try {
    const url = new URL(value, "https://techinn.invalid")
    if (url.origin !== "https://techinn.invalid" || /%2f|%5c/i.test(url.pathname)
      || /^\/(?:login|blocks\/login|reset-password)\/?$/i.test(decodeURIComponent(url.pathname))) return fallback
    return url.pathname + url.search + url.hash
  } catch { return fallback }
}

export function getLoginReturnPath() {
  if (typeof window === "undefined") return "/dashboard/"
  return safeReturnPath(new URLSearchParams(window.location.search).get("next"))
}

function subscribe(callback: () => void) {
  window.addEventListener("popstate", callback)
  window.addEventListener("hashchange", callback)
  return () => {
    window.removeEventListener("popstate", callback)
    window.removeEventListener("hashchange", callback)
  }
}

export function useLoginReturnPath() {
  return useSyncExternalStore(subscribe, getLoginReturnPath, () => "/dashboard/")
}

export function useSignInHref() {
  const pathname = usePathname()
  const path = useSyncExternalStore(subscribe,
    () => safeReturnPath(window.location.pathname + window.location.search + window.location.hash),
    () => safeReturnPath(pathname))
  return "/login/?next=" + encodeURIComponent(path === "/" ? "/dashboard/" : path)
}
