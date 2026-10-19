"use client"

import { useEffect } from "react"

import { apiRequest, getApiSession, saveApiSession, touchApiSession } from "@/lib/api"

export function SessionActivity() {
  useEffect(() => {
    let lastSent = 0
    const active = () => {
      if (document.visibilityState !== "visible" || Date.now() - lastSent < 60_000) return
      if (!touchApiSession()) return
      const session = getApiSession()
      lastSent = Date.now()
      void apiRequest<{ access?: string; refresh?: string }>("/auth/activity/", { method: "POST", keepalive: true }).then((tokens) => {
        const current = getApiSession()
        if (current && current.refresh === session?.refresh && tokens.access && tokens.refresh) {
          saveApiSession({ ...current, access: tokens.access, refresh: tokens.refresh })
        }
      }).catch(() => {})
    }
    const events = ["pointerdown", "keydown", "scroll", "focus"] as const
    events.forEach((name) => window.addEventListener(name, active, { passive: true }))
    document.addEventListener("visibilitychange", active)
    active()
    const expiry = window.setInterval(() => { getApiSession() }, 30_000)
    return () => {
      events.forEach((name) => window.removeEventListener(name, active))
      document.removeEventListener("visibilitychange", active)
      window.clearInterval(expiry)
    }
  }, [])
  return null
}
