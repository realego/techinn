"use client"

import { useSyncExternalStore } from "react"

export type VisitAttribution = {
  source?: string
  medium?: string
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
  utm_term?: string
  utm_content?: string
  gclid?: string
  fbclid?: string
  referrer?: string
  landing_path: string
  first_seen_at: string
  last_seen_at: string
}

const storageKey = "techinn-visit-attribution"
const changedEvent = "techinn-attribution-change"
const attributionKeys = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"] as const

function classifySource(url: URL, referrer?: string) {
  const taggedSource = url.searchParams.get("utm_source")?.trim().slice(0, 200)
  const taggedMedium = url.searchParams.get("utm_medium")?.trim().slice(0, 200)
  if (taggedSource) return { source: taggedSource, medium: taggedMedium || "campaign" }
  if (url.searchParams.has("gclid")) return { source: "google", medium: "cpc" }
  if (url.searchParams.has("fbclid")) return { source: "facebook", medium: "paid-social" }
  if (referrer) return { source: referrer, medium: "referral" }
  return { source: "direct", medium: "none" }
}

function subscribe(onChange: () => void) {
  window.addEventListener(changedEvent, onChange)
  return () => window.removeEventListener(changedEvent, onChange)
}

function getSnapshot() {
  try {
    return window.localStorage.getItem(storageKey)
  } catch {
    return null
  }
}

export function useVisitAttribution() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, () => null)
  if (!snapshot) return null
  try {
    return JSON.parse(snapshot) as VisitAttribution
  } catch {
    return null
  }
}

export function captureVisitAttribution() {
  if (window.localStorage.getItem("techinn-cookie-consent-v1") !== "accepted") return
  const url = new URL(window.location.href)
  const incoming: Partial<VisitAttribution> = {}
  for (const key of attributionKeys) {
    const value = url.searchParams.get(key)?.trim().slice(0, 200)
    if (value) incoming[key] = value
  }
  const now = new Date().toISOString()
  let previous: VisitAttribution | null = null
  try {
    const raw = window.localStorage.getItem(storageKey)
    previous = raw ? JSON.parse(raw) as VisitAttribution : null
  } catch {
    previous = null
  }
  const referrer = document.referrer ? new URL(document.referrer).hostname.slice(0, 200) : undefined
  const classified = classifySource(url, referrer)
  const attribution: VisitAttribution = {
    ...previous,
    ...incoming,
    source: previous?.source ?? classified.source,
    medium: previous?.medium ?? classified.medium,
    landing_path: previous?.landing_path ?? `${url.pathname}${url.hash}`,
    first_seen_at: previous?.first_seen_at ?? now,
    last_seen_at: now,
    ...(referrer ? { referrer: previous?.referrer ?? referrer } : {}),
  }
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(attribution))
    window.dispatchEvent(new Event(changedEvent))
  } catch {
    return
  }
}
