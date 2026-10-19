"use client"

import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { apiRequest, CustomerProfile, getApiSession, saveApiSession } from "@/lib/api"

type Address = Partial<Record<"line1" | "line2" | "city" | "region" | "postal_code" | "country", string>>
type Preferences = { service_updates: boolean; billing_reminders: boolean; product_news: boolean }
const defaults: Preferences = { service_updates: true, billing_reminders: true, product_news: false }
const addressFields = { line1: "Address line 1", line2: "Address line 2", city: "City", region: "Province / region", postal_code: "Postal code", country: "Country" }

export function CustomerSettings({ mode }: { mode: "addresses" | "notifications" }) {
  const [addresses, setAddresses] = useState<{billing_address: Address; postal_address: Address}>({ billing_address: {}, postal_address: {} })
  const [preferences, setPreferences] = useState(defaults)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  useEffect(() => {
    let active = true
    apiRequest<CustomerProfile>("/auth/me/").then(profile => {
      if (!active) return
      setAddresses({ billing_address: profile.billing_address ?? {}, postal_address: profile.postal_address ?? {} })
      setPreferences({ ...defaults, ...profile.notification_preferences })
      setLoading(false)
    }).catch(cause => { if (active) setError(cause.message) })
    return () => { active = false }
  }, [])
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("")
    try {
      const profile = await apiRequest<CustomerProfile>("/auth/me/", { method: "PATCH", body: JSON.stringify(mode === "addresses" ? addresses : { notification_preferences: preferences }) })
      const session = getApiSession(); if (session) saveApiSession({ ...session, customer: profile })
      setNotice(mode === "addresses" ? "Your addresses have been saved." : "Your notification preferences have been saved.")
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save changes.") }
    finally { setBusy(false) }
  }
  return <Card><CardHeader><CardTitle className="text-base">{mode === "addresses" ? "Billing & postal addresses" : "Notification preferences"}</CardTitle></CardHeader><CardContent>
    <form className="space-y-4" onSubmit={save}>
      {mode === "addresses" ? <div className="grid gap-5 lg:grid-cols-2">{(["billing_address", "postal_address"] as const).map(kind => <fieldset key={kind} disabled={loading || busy} className="min-w-0 space-y-3"><legend className="mb-3 text-sm font-medium text-orange-600 dark:text-orange-400">{kind === "billing_address" ? "Billing address" : "Postal address"}</legend><div className="grid gap-3 sm:grid-cols-2">{Object.entries(addressFields).map(([key, label]) => <label key={key} className={`min-w-0 space-y-1 text-sm ${key.startsWith("line") ? "sm:col-span-2" : ""}`}>{label}<Input maxLength={key.startsWith("line") ? 255 : key === "postal_code" ? 30 : 100} value={addresses[kind][key as keyof Address] ?? ""} onChange={e => setAddresses(current => ({ ...current, [kind]: { ...current[kind], [key]: e.target.value } }))} /></label>)}</div></fieldset>)}</div> : <>
        {([ ["service_updates", "Service updates", "Email updates when services and mailboxes are ready."], ["billing_reminders", "Billing reminders", "Email reminders about renewals and due payments."], ["product_news", "Product news & offers", "Optional news about TechInn services."] ] as const).map(([key, title, description]) => <label key={key} className="flex items-center justify-between gap-4 border-b pb-3"><span><span className="block text-sm font-medium">{title}</span><span className="text-xs text-muted-foreground">{description}</span></span><Checkbox aria-label={title} checked={preferences[key]} disabled={loading || busy} onCheckedChange={value => setPreferences(current => ({ ...current, [key]: value === true }))} /></label>)}
        <p className="text-xs text-muted-foreground">Security and essential account messages stay enabled. Email preferences apply when email delivery is available.</p>
      </>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}{notice && <p role="status" className="text-sm text-green-700 dark:text-green-400">{notice}</p>}
      <Button disabled={loading || busy} loading={busy} type="submit">Save {mode === "addresses" ? "addresses" : "preferences"}</Button>
    </form>
  </CardContent></Card>
}
