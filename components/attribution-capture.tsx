"use client"

import { useEffect } from "react"

import { captureVisitAttribution } from "@/lib/attribution"

export function AttributionCapture() {
  useEffect(() => {
    captureVisitAttribution()
    window.addEventListener("popstate", captureVisitAttribution)
    window.addEventListener("techinn-consent-accepted", captureVisitAttribution)
    return () => {
      window.removeEventListener("popstate", captureVisitAttribution)
      window.removeEventListener("techinn-consent-accepted", captureVisitAttribution)
    }
  }, [])

  return null
}
