"use client"

import { Check, ChevronDown, Copy, Globe2, Loader2, RefreshCw, ShieldCheck, X } from "lucide-react"
import Link from "next/link"
import { type ReactNode,useCallback, useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiRequest } from "@/lib/api"

type RecordRow = { type: string; name: string; content: string; priority?: number; ready?: boolean }
type Connection = {
  id: number; domain_name: string; plan: string; mode: string; services: string; status: string
  verification_name: string; verification_value: string; verified_at: string | null
  nameservers: string[]; required_records: RecordRow[]; previous_records: RecordRow[]
  review_approved_at: string | null; dns_applied_at: string | null
  checks: { ownership?: boolean; hosting?: boolean; dns?: boolean; website?: boolean | null; email?: boolean | null; https?: boolean | null; records?: RecordRow[] }
  last_error: string; last_checked_at: string | null; next_check_at: string | null
}
type Plan = { id: string; name: string; kind: string; domain: string | null }
type Payload = { connections: Connection[]; plans: Plan[] }
type Provider = { id: number; name: string; status: string; provider: string }
type Zone = { id: string; name: string }
const selectClass = "h-10 min-w-0 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs focus:outline-none focus:ring-2 focus:ring-orange-500/30"
const labels: Record<string, string> = { awaiting_ownership: "Verify ownership", awaiting_plan: "Choose plan later", preparing: "Preparing hosting", awaiting_review: "Review DNS", awaiting_dns: "Checking DNS", connected: "Connected", needs_attention: "Needs attention" }

function CopyValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  const [failed, setFailed] = useState(false)
  return <div className="flex min-w-0 items-center gap-2 rounded-md border border-orange-200 bg-orange-50/40 px-3 py-2 dark:border-orange-900 dark:bg-orange-950/15">
    <code className="min-w-0 flex-1 select-all break-all text-xs">{value}</code>
    <Button aria-label={`Copy ${value}`} className="size-7 shrink-0" size="icon" variant="ghost" onClick={() => void navigator.clipboard.writeText(value).then(() => { setCopied(true); setFailed(false); window.setTimeout(() => setCopied(false), 2000) }).catch(() => setFailed(true))}>{copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}</Button>
    {failed && <span className="text-xs text-red-600">Select text to copy</span>}
  </div>
}

function RecordTable({ records }: { records: RecordRow[] }) {
  return <div className="min-w-0 overflow-hidden rounded-md border"><Table className="w-full table-fixed">
    <TableHeader><TableRow><TableHead className="w-16">Type</TableHead><TableHead className="w-[30%]">Name</TableHead><TableHead>Value</TableHead></TableRow></TableHeader>
    <TableBody>{records.map((row, i) => <TableRow key={`${row.type}-${row.name}-${i}`}>
      <TableCell className="align-top text-xs">{row.type}{row.ready !== undefined && <span className={`mt-1 block text-[10px] ${row.ready ? "text-green-700 dark:text-green-400" : "text-muted-foreground"}`}>{row.ready ? "Ready" : "Waiting"}</span>}</TableCell>
      <TableCell className="whitespace-normal break-all align-top font-mono text-xs">{row.name}</TableCell>
      <TableCell className="whitespace-normal break-all align-top font-mono text-xs">{row.priority !== undefined && <span className="mr-1 text-muted-foreground">{row.priority}</span>}{row.content}</TableCell>
    </TableRow>)}</TableBody>
  </Table></div>
}

function ConnectionDetails({ item, refresh }: { item: Connection; refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const [zoneFile, setZoneFile] = useState("")
  const [filename, setFilename] = useState("")
  async function action(path: string, body: object = {}, method = "POST") {
    setBusy(true); setError(""); setMessage("")
    try {
      const result = await apiRequest<{ detail?: string }>(`/services/domain-connections/${item.id}/${path}`, { method, ...(method === "DELETE" ? {} : { body: JSON.stringify(body) }) })
      setMessage(result?.detail ?? "Connection removed.")
      await refresh()
    } catch (err) { setError(err instanceof Error ? err.message : "The request could not finish.") }
    finally { setBusy(false) }
  }
  const checks: [string, boolean | null | undefined][] = [["Ownership", Boolean(item.verified_at)], ["Hosting", item.checks.hosting], ["DNS", item.checks.dns]]
  if (item.services !== "email") checks.push(["Website", item.checks.website], ["HTTPS", item.checks.https])
  if (item.services !== "website") checks.push(["Email DNS", item.checks.email])
  return <div className="min-w-0 space-y-4 border-t p-3 sm:p-4">
    <div className="flex flex-wrap gap-x-4 gap-y-2">{checks.map(([label, ready]) => <span className={`flex items-center gap-1.5 text-xs ${ready ? "text-green-700 dark:text-green-400" : "text-muted-foreground"}`} key={label}>{ready ? <Check className="size-3.5" /> : <span className="size-3 rounded-full border" />}{label}</span>)}</div>
    {(error || item.last_error) && <div role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error || item.last_error}</div>}
    {message && <p role="status" className="text-sm text-orange-700 dark:text-orange-300">{message}</p>}
    {!item.verified_at && <div className="space-y-3">
      <p className="text-sm">Add this TXT record at your current DNS provider to prove you control <strong>{item.domain_name}</strong>.</p>
      <div className="grid gap-2 sm:grid-cols-2"><label className="grid min-w-0 gap-1 text-xs text-muted-foreground">Name<CopyValue value={item.verification_name} /></label><label className="grid min-w-0 gap-1 text-xs text-muted-foreground">TXT value<CopyValue value={item.verification_value} /></label></div>
      <p className="text-xs text-muted-foreground">Use TTL Auto or 300. Some providers want just <code>_techinn-verification</code> as the name. {item.mode === "cloudflare" && "An active zone in your authorized Cloudflare account can also verify ownership automatically."}</p>
      <p className="text-xs text-muted-foreground">Ownership is checked only when you click “Check ownership.” The result appears here immediately.</p>
    </div>}
    {!!item.verified_at && !!item.plan && !item.required_records.length && <p className="flex items-center gap-2 text-sm"><Loader2 className="size-4 animate-spin" /> Preparing your hosting account and DNS records.</p>}
    {!!item.required_records.length && <>
      <div className="space-y-2"><h3 className="text-sm font-semibold">{item.mode === "external" ? "Records to add at your DNS provider" : "Records for your selected services"}</h3><RecordTable records={item.checks.records ?? item.required_records} /></div>
      {!!item.previous_records.length && <details className="rounded-md border"><summary className="cursor-pointer px-3 py-2 text-sm">Existing records · {item.previous_records.length}</summary><div className="p-2 pt-0"><RecordTable records={item.previous_records} /></div></details>}
      {!item.review_approved_at && <div className="space-y-3 rounded-md border border-orange-200 bg-orange-50/40 p-3 dark:border-orange-900 dark:bg-orange-950/15">
        <h3 className="text-sm font-semibold">Review before switching</h3>
        <p className="text-xs text-muted-foreground">{item.services === "website" ? "Only website records will be changed. Existing email records will be kept." : item.services === "email" ? "Only email records will be changed. Your existing website records will be kept." : "Website and email routing will move to TechInn."} Existing website content and old messages need to be migrated separately.</p>
        {item.mode === "managed" && <>
          <p className="text-xs text-muted-foreground">A public scan cannot find every record. Import your current provider’s DNS zone file to preserve custom subdomains and other services.</p>
          <label className="grid gap-1 text-xs font-medium">Import DNS zone file (optional)<Input aria-label="Import DNS zone file" className="h-10 bg-background" type="file" accept=".txt,.zone,.dns" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; if (file.size > 131072) { setError("Choose a zone file under 128 KB."); return } void file.text().then(text => { setZoneFile(text); setFilename(file.name); setError("") }).catch(() => setError("The zone file could not be opened.")) }} />{filename && <span className="text-muted-foreground">{filename}</span>}</label>
        </>}
        <label className="flex items-start gap-2 text-sm"><input className="mt-1 accent-orange-600" type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /><span>I reviewed my existing records and approve the changes for my selected services.</span></label>
        <Button disabled={busy || !confirmed} loading={busy} onClick={() => void action("approve/", { confirm: true, zone_file: zoneFile })}>{item.mode === "external" ? "I’ve added the records — check connection" : "Approve and apply DNS"}</Button>
      </div>}
    </>}
    {item.mode === "managed" && item.nameservers.length > 0 && <div className="space-y-2">
      <h3 className="text-sm font-semibold">Your assigned nameservers</h3>
      <p className="text-xs text-muted-foreground">{item.dns_applied_at ? "Replace the current nameservers at your domain registrar with these." : "Wait until your DNS records are applied before changing nameservers."} If DNSSEC is enabled, remove the old DS record at your registrar before switching; enable DNSSEC again after activation.</p>
      <div className="grid gap-2 sm:grid-cols-2">{item.nameservers.map(ns => <CopyValue value={ns} key={ns} />)}</div>
    </div>}
    {item.status === "connected" && <div className="flex flex-wrap gap-2">{item.services !== "email" && <Button asChild size="sm" variant="outline"><Link href="/dashboard/web/">Manage website</Link></Button>}{item.services !== "website" && <Button asChild size="sm" variant="outline"><Link href="/dashboard/email/">Create mailboxes</Link></Button>}<Button asChild size="sm" variant="outline"><Link href="/dashboard/domains/">Manage DNS</Link></Button></div>}
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex flex-wrap gap-2">
        {item.verified_at
          ? <Button disabled={busy} loading={busy} size="sm" variant="outline" onClick={() => void action("check/")}><RefreshCw className="size-3.5" />{item.last_error ? "Retry setup" : "Check connection"}</Button>
          : <Button disabled={busy} loading={busy} size="sm" variant="outline" onClick={() => void action("verify/")}><RefreshCw className="size-3.5" />Check ownership</Button>}
        {!item.verified_at && <Button disabled={busy} size="sm" variant="ghost" onClick={() => void action("", {}, "DELETE")}><X className="size-3.5" />Remove</Button>}
      </div>
      <span className="text-xs text-muted-foreground">{item.last_checked_at ? `Last checked ${new Date(item.last_checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Not checked yet"}</span>
    </div>
  </div>
}

export function DomainConnections({ providers, advanced }: { providers: Provider[]; advanced: ReactNode }) {
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [domain, setDomain] = useState("")
  const [plan, setPlan] = useState("")
  const [mode, setMode] = useState("managed")
  const [purpose, setPurpose] = useState("both")
  const [provider, setProvider] = useState("")
  const [zones, setZones] = useState<Zone[]>([])
  const [zone, setZone] = useState("")
  const [open, setOpen] = useState<number | null>(null)
  const refresh = useCallback(async () => {
    const result = await apiRequest<Payload>("/services/domain-connections/")
    setData(result)
  }, [])
  useEffect(() => { const initial = window.setTimeout(() => { void refresh().catch(e => setError(e.message)) }, 0); const timer = window.setInterval(() => { void refresh().catch(e => setError(e.message)) }, 10000); return () => { window.clearTimeout(initial); window.clearInterval(timer) } }, [refresh])
  const selectedPlan = data?.plans.find(p => p.id === plan)
  const cloudflare = providers.filter(p => p.provider === "cloudflare" && p.status === "active")
  async function findZones(value: string) {
    setProvider(value); setZone(""); setZones([])
    if (!value) return
    setBusy(true); setError("")
    try { const result = await apiRequest<Zone[]>(`/services/provider-connections/${value}/zones/`); setZones(result) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load domain zones.") }
    finally { setBusy(false) }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("")
    try {
      const result = await apiRequest<Connection>("/services/domain-connections/", { method: "POST", body: JSON.stringify({ domain_name: domain, ...(plan ? { plan } : {}), mode, services: selectedPlan?.kind === "email-hosting" ? "email" : purpose, ...(mode === "cloudflare" ? { connection_id: Number(provider), zone_id: zone } : {}) }) })
      setOpen(result.id); setDomain(""); setPlan(""); await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start your connection.") }
    finally { setBusy(false) }
  }
  async function removeConnection(item: Connection) {
    setBusy(true); setError("")
    try {
      await apiRequest(`/services/domain-connections/${item.id}/`, { method: "DELETE" })
      setOpen(null)
      await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not remove this connection.") }
    finally { setBusy(false) }
  }
  async function selectPlan(item: Connection, selected: string) {
    setBusy(true); setError("")
    try {
      await apiRequest<Connection>(`/services/domain-connections/${item.id}/select-plan/`, { method: "POST", body: JSON.stringify({ plan: selected }) })
      setMessageForConnection(item.id, "Plan selected. Hosting and DNS preparation has started.")
      await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : "Could not assign this plan.") }
    finally { setBusy(false) }
  }
  const [selectedPlans, setSelectedPlans] = useState<Record<number, string>>({})
  const [connectionMessages, setConnectionMessages] = useState<Record<number, string>>({})
  function setMessageForConnection(id: number, message: string) {
    setConnectionMessages(current => ({ ...current, [id]: message }))
  }
  return <section className="min-w-0 space-y-4" id="connections">
    <header><h2 className="flex items-center gap-2 text-xl font-semibold"><Globe2 className="size-5 text-orange-600" />Connect your domain</h2><p className="mt-1 text-sm text-muted-foreground">Add your domain now and check ownership whenever you’re ready. No background ownership checks run; hosting and DNS setup wait until you choose a paid service.</p></header>
    <div className="overflow-hidden rounded-lg border border-orange-200 dark:border-orange-900">
      <div className="flex items-center gap-2 border-b border-orange-200 bg-orange-50/60 px-3 py-3 text-sm font-medium dark:border-orange-900 dark:bg-orange-950/20"><ShieldCheck className="size-4 text-orange-600" />Keep your domain registration where it is.</div>
      <form onSubmit={submit} className="space-y-3 p-3 sm:p-4">
        <div className="grid gap-3 sm:grid-cols-2"><label className="grid min-w-0 gap-1.5 text-sm">Hosting plan <span className="text-xs font-normal text-muted-foreground">Optional — attach an open plan now or later</span><select className={selectClass} value={plan} onChange={e => { setPlan(e.target.value); const p = data?.plans.find(p => p.id === e.target.value); if (p?.domain) setDomain(p.domain) }}><option value="">Connect now, choose a plan later</option>{data?.plans.map(p => <option key={p.id} value={p.id}>{p.name}{p.domain ? ` · ${p.domain}` : " · Available"}</option>)}</select></label><label className="grid min-w-0 gap-1.5 text-sm">Domain<Input className="h-10" placeholder="yourbusiness.co.zw" autoCapitalize="none" autoCorrect="off" value={domain} onChange={e => setDomain(e.target.value)} required /></label></div>
        {data && !data.plans.length && <p className="text-sm text-muted-foreground">You can verify your domain now and pick a plan when you’re ready. <Link className="font-medium text-orange-700 underline dark:text-orange-300" href="/shop/">Browse hosting plans</Link></p>}
        <div className="grid gap-3 sm:grid-cols-2"><label className="grid gap-1.5 text-sm">DNS management<select className={selectClass} value={mode} onChange={e => setMode(e.target.value)}><option value="managed">Use TechInn DNS — recommended</option><option value="external">Keep my existing DNS</option><option value="cloudflare">Use my Cloudflare account</option></select></label><label className="grid gap-1.5 text-sm">Connect services<select className={selectClass} disabled={selectedPlan?.kind === "email-hosting"} value={selectedPlan?.kind === "email-hosting" ? "email" : purpose} onChange={e => setPurpose(e.target.value)}><option value="both">Website and email</option><option value="website">Website only</option><option value="email">Email only</option></select></label></div>
        <p className="text-xs text-muted-foreground">{mode === "managed" ? "We prepare your DNS and give you two nameservers to set at your registrar." : mode === "external" ? "Keep your nameservers. We show the exact DNS records to add at your current provider." : "We use your authorized Cloudflare zone and keep your existing nameservers."}</p>
        {mode === "cloudflare" && <div className="grid gap-3 sm:grid-cols-2"><label className="grid gap-1.5 text-sm">Cloudflare connection<select className={selectClass} required value={provider} onChange={e => void findZones(e.target.value)}><option value="">Choose an account</option>{cloudflare.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label className="grid gap-1.5 text-sm">Domain zone<select className={selectClass} required value={zone} onChange={e => { setZone(e.target.value); setDomain(zones.find(z => z.id === e.target.value)?.name ?? "") }}><option value="">Choose a zone</option>{zones.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}</select></label>{!cloudflare.length && <p className="text-xs text-muted-foreground sm:col-span-2">Add your Cloudflare account under Advanced provider settings below.</p>}</div>}
        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/30 dark:text-red-300" role="alert">{error}</p>}
        <Button disabled={busy || !domain || (mode === "cloudflare" && (!provider || !zone))} loading={busy} type="submit">{plan ? "Connect domain and plan" : "Verify domain"}</Button>
      </form>
    </div>
    {!data && !error && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />Loading your plans and connections…</p>}
    {data?.connections.map(item => <article className="min-w-0 overflow-hidden rounded-lg border" key={item.id}>
      <button className="flex w-full min-w-0 items-center gap-3 p-3 text-left hover:bg-muted/40 sm:p-4" type="button" aria-expanded={open === item.id} onClick={() => setOpen(open === item.id ? null : item.id)}><Globe2 className="size-5 shrink-0 text-orange-600" /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{item.domain_name}</span><span className="block truncate text-xs text-muted-foreground">{item.plan || "No plan selected"} · {item.services === "both" ? "Website and email" : item.services === "email" ? "Email" : "Website"}</span></span><Badge className="shrink-0 text-[10px] sm:text-xs" variant={item.last_error ? "destructive" : item.status === "connected" ? "default" : "secondary"}>{labels[item.status] ?? item.status}</Badge><ChevronDown className={`size-4 shrink-0 transition-transform ${open === item.id ? "rotate-180" : ""}`} /></button>
      {open === item.id && <>
        {item.verified_at && !item.plan && <div className="space-y-2 border-t p-3 sm:p-4">
          <p className="text-sm">Domain ownership is verified. Attach an open plan already available in your account, or choose a paid plan when you’re ready to set up hosting and DNS.</p>
          {(data?.plans ?? []).filter(p => (!p.domain || p.domain === item.domain_name) && (p.kind !== "email-hosting" || item.services === "email")).length ? <>
            <div className="flex flex-wrap items-end gap-2">
              <label className="grid min-w-0 flex-1 gap-1 text-sm">Available plan to attach<select className={selectClass} value={selectedPlans[item.id] ?? ""} onChange={event => setSelectedPlans(current => ({ ...current, [item.id]: event.target.value }))}>
                <option value="">Select a plan</option>
                {(data?.plans ?? []).filter(p => (!p.domain || p.domain === item.domain_name) && (p.kind !== "email-hosting" || item.services === "email")).map(p => <option key={p.id} value={p.id}>{p.name}{p.domain ? ` · ${p.domain}` : ""}</option>)}
              </select></label>
              <Button disabled={busy || !selectedPlans[item.id]} loading={busy} onClick={() => void selectPlan(item, selectedPlans[item.id])} type="button">Attach selected plan</Button>
            </div>
            <p className="text-xs text-muted-foreground">Choose an available plan to attach it here, or <Link className="text-orange-700 underline dark:text-orange-300" href="/shop/">shop for a plan</Link>.</p>
          </> : <p className="text-sm text-muted-foreground">No eligible paid plan is available yet. <Link className="text-orange-700 underline dark:text-orange-300" href="/shop/">Choose a plan in the shop</Link>; return here to attach it.</p>}
          {connectionMessages[item.id] && <p role="status" className="text-sm text-orange-700 dark:text-orange-300">{connectionMessages[item.id]}</p>}
          {item.last_error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{item.last_error}</p>}
          <Button disabled={busy} size="sm" variant="ghost" onClick={() => void removeConnection(item)}>Remove domain connection</Button>
        </div>}
        <ConnectionDetails item={item} refresh={refresh} />
      </>}
    </article>)}
    <details className="rounded-lg border"><summary className="cursor-pointer p-3 text-sm font-medium">Advanced provider settings</summary><div className="min-w-0 p-3 pt-0">{advanced}</div></details>
  </section>
}
