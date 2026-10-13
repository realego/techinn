"use client"

import { useEffect } from "react"

import { captureVisitAttribution } from "@/lib/attribution"

export function AttributionCapture() {
  useEffect(() => {
    captureVisitAttribution()
    window.addEventListener("popstate", captureVisitAttribution)
    return () => window.removeEventListener("popstate", captureVisitAttribution)
  }, [])

  return null
}
