"use client"

import { useEffect, useMemo, useState } from "react"
import { MessageCircle, Send, Plus, Paperclip } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { apiRequest } from "@/lib/api"

type ServiceOption = { uuid: string; product: string; service_type?: string; status: string }
type TicketMessage = { id: number; body: string; author_name: string; is_staff: boolean; created_at: string }
type Ticket = {
  id: number; ticket_number: string; subject: string; category: string; status: string; priority: string
  service_uuid?: string | null; service_label?: string | null; messages: TicketMessage[]; updated_at: string
}

const statusLabel: Record<string, string> = {
  open: "Open", pending_support: "With support", pending_customer: "Your reply needed", resolved: "Resolved", closed: "Closed",
}

export function SupportTickets({ services }: { services: ServiceOption[] }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [subject, setSubject] = useState("")
  const [message, setMessage] = useState("")
  const [category, setCategory] = useState("service")
  const [priority, setPriority] = useState("normal")
  const [service, setService] = useState(() => typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("service") ?? "")
  const [isNew, setIsNew] = useState(() => typeof window !== "undefined" && Boolean(new URLSearchParams(window.location.search).get("service")))
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")
  const selected = useMemo(() => tickets.find((ticket) => ticket.id === selectedId) ?? null, [selectedId, tickets])

  async function load() {
    const response = await apiRequest<Ticket[] | { results: Ticket[] }>("/services/tickets/")
    const next = Array.isArray(response) ? response : response.results
    setTickets(next)
    setSelectedId((current) => current && next.some((ticket) => ticket.id === current) ? current : next[0]?.id ?? null)
  }

  useEffect(() => { void load().catch((cause) => setError(cause instanceof Error ? cause.message : "Tickets could not be loaded.")) }, [])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!subject.trim() || !message.trim()) return
    setSending(true); setError("")
    try {
      const created = await apiRequest<Ticket>("/services/tickets/", {
        method: "POST", body: JSON.stringify({ subject: subject.trim(), message: message.trim(), category, priority, service: service || null }),
      })
      setTickets((current) => [created, ...current]); setSelectedId(created.id); setSubject(""); setMessage(""); setIsNew(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The ticket could not be sent.") }
    finally { setSending(false) }
  }

  async function reply(event: React.FormEvent) {
    event.preventDefault()
    if (!selected || !message.trim()) return
    setSending(true); setError("")
    try {
      const updated = await apiRequest<Ticket>(`/services/tickets/${selected.id}/`, { method: "POST", body: JSON.stringify({ body: message.trim() }) })
      setTickets((current) => current.map((ticket) => ticket.id === updated.id ? updated : ticket)); setMessage("")
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Your reply could not be sent.") }
    finally { setSending(false) }
  }

  return <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(240px,0.35fr)_minmax(0,1fr)]">
    <Card className="min-w-0">
      <CardHeader className="flex flex-row items-center justify-between gap-3 border-b px-4 py-3">
        <CardTitle className="text-base">Your tickets</CardTitle>
        <Button className="h-8" onClick={() => { setIsNew(true); setSelectedId(null); setMessage("") }} size="sm"><Plus className="size-3.5" /> New ticket</Button>
      </CardHeader>
      <CardContent className="p-2">
        {!tickets.length && <p className="p-4 text-sm text-muted-foreground">No support conversations yet.</p>}
        {tickets.map((ticket) => <button className={`w-full rounded-lg p-3 text-left transition-colors hover:bg-muted/60 ${selectedId === ticket.id ? "bg-orange-50 dark:bg-orange-950/20" : ""}`} key={ticket.id} onClick={() => { setSelectedId(ticket.id); setIsNew(false) }} type="button">
          <div className="flex items-center justify-between gap-2"><span className="text-xs font-medium text-muted-foreground">{ticket.ticket_number}</span><Badge variant="outline">{statusLabel[ticket.status] ?? ticket.status}</Badge></div>
          <p className="mt-1 truncate text-sm font-medium">{ticket.subject}</p><p className="mt-1 truncate text-xs text-muted-foreground">{ticket.service_label ?? "General support"}</p>
        </button>)}
      </CardContent>
    </Card>
    <Card className="min-w-0">
      <CardHeader className="border-b px-4 py-3"><CardTitle className="flex items-center gap-2 text-base"><MessageCircle className="size-4 text-orange-500" />{isNew ? "Open a support ticket" : selected ? `${selected.ticket_number} · ${selected.subject}` : "Select a ticket"}</CardTitle></CardHeader>
      <CardContent className="p-4">
        {error && <p className="mb-3 rounded-md border border-orange-300 bg-orange-50 p-3 text-sm text-orange-800 dark:border-orange-800 dark:bg-orange-950/30 dark:text-orange-200">{error}</p>}
        {isNew && <form className="grid gap-3" onSubmit={submit}>
          <Input onChange={(event) => setSubject(event.target.value)} placeholder="Subject" value={subject} />
          <div className="grid gap-3 sm:grid-cols-3"><select className="h-10 rounded-md border bg-background px-3 text-sm" onChange={(event) => setCategory(event.target.value)} value={category}><option value="service">Service</option><option value="billing">Billing</option><option value="domain">Domain</option><option value="account">Account</option><option value="other">Other</option></select><select className="h-10 rounded-md border bg-background px-3 text-sm" onChange={(event) => setPriority(event.target.value)} value={priority}><option value="normal">Normal priority</option><option value="high">High priority</option><option value="urgent">Urgent</option></select><select className="h-10 min-w-0 rounded-md border bg-background px-3 text-sm" onChange={(event) => setService(event.target.value)} value={service}><option value="">No service attached</option>{services.map((item) => <option key={item.uuid} value={item.uuid}>{item.product}</option>)}</select></div>
          <textarea className="min-h-32 rounded-md border bg-background p-3 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-orange-500/30" onChange={(event) => setMessage(event.target.value)} placeholder="Describe what you need help with" value={message} />
          <div className="flex justify-end gap-2"><Button onClick={() => setIsNew(false)} type="button" variant="outline">Cancel</Button><Button disabled={sending || !subject.trim() || !message.trim()} loading={sending} type="submit"><Send className="size-3.5" /> Send ticket</Button></div>
        </form>}
        {!isNew && selected && <><div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1">{selected.messages.map((item) => <div className={`flex ${item.is_staff ? "justify-start" : "justify-end"}`} key={item.id}><div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${item.is_staff ? "border bg-muted" : "bg-orange-500 text-white"}`}><p className="mb-1 text-[11px] opacity-70">{item.author_name} · {new Date(item.created_at).toLocaleString()}</p><p className="whitespace-pre-wrap">{item.body}</p></div></div>)}</div><form className="mt-4 flex items-end gap-2 border-t pt-3" onSubmit={reply}><textarea className="min-h-12 flex-1 resize-y rounded-md border bg-background p-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-orange-500/30" onChange={(event) => setMessage(event.target.value)} placeholder="Write a reply" value={message} /><Button aria-label="Send reply" disabled={sending || !message.trim()} loading={sending} size="icon" type="submit"><Send className="size-4" /></Button></form></>}
        {!isNew && !selected && <div className="grid min-h-64 place-items-center text-center text-sm text-muted-foreground"><div><Paperclip className="mx-auto mb-2 size-7" /><p>Choose a ticket or open a new conversation.</p></div></div>}
      </CardContent>
    </Card>
  </div>
}
