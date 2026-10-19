"use client"

import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiRequest } from "@/lib/api"

type Member = { id: number; customer_email: string; role: string }
const roles = { technical: "Technical", admin: "Administrator", billing: "Billing" }
const selectClass = "h-9 min-w-0 rounded-md border border-input bg-background px-3 text-sm"
export function ServiceTeam({ service }: { service: { uuid: string; product: string } }) {
  const [members, setMembers] = useState<Member[]>([])
  const [email, setEmail] = useState("")
  const [role, setRole] = useState("technical")
  const [busy, setBusy] = useState(false)
  const [activeAction, setActiveAction] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [removing, setRemoving] = useState<number | null>(null)
  const path = `/services/${service.uuid}/members/`
  useEffect(() => {
    let active = true
    apiRequest<Member[] | { results: Member[] }>(path).then(data => {
      if (active) { setMembers(Array.isArray(data) ? data : data.results); setLoading(false) }
    }).catch(cause => { if (active) { setError(cause.message); setLoading(false) } })
    return () => { active = false }
  }, [path])
  async function update(method: string, id?: number, nextRole?: string) {
    setActiveAction(`${method}:${id ?? "new"}`)
    setBusy(true); setError(""); setNotice("")
    try {
      const result = await apiRequest<Member>(id ? `${path}${id}/` : path, { method, ...(method === "DELETE" ? {} : { body: JSON.stringify(id ? { role: nextRole } : { email: email.trim(), role }) }) })
      setMembers(current => method === "DELETE" ? current.filter(member => member.id !== id) : id ? current.map(member => member.id === id ? result : member) : [...current, result])
      if (!id) setEmail("")
      setRemoving(null)
      setNotice(method === "DELETE" ? "Team access revoked." : id ? "Role updated." : "Team access granted.")
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not update team access.") }
    finally { setBusy(false) }
  }
  return <Card><CardHeader><CardTitle className="text-base">{service.product}</CardTitle></CardHeader><CardContent className="space-y-4">
    <p className="text-xs text-muted-foreground">Access applies only to this service. Technical: domains, DNS, hosting and email. Billing: service price and renewal dates. Administrator: all available permissions for this service. Add the same person separately to each web hosting or email service they should manage. Only you can manage the team.</p>
    <form className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_160px_auto]" onSubmit={e => { e.preventDefault(); void update("POST") }}>
      <Input aria-label="Team member email" disabled={busy} onChange={e => setEmail(e.target.value)} placeholder="team@example.com" required type="email" value={email} />
      <select aria-label="New member role" className={selectClass} disabled={busy} onChange={e => setRole(e.target.value)} value={role}>{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <Button disabled={busy} loading={busy && activeAction === "POST:new"} type="submit">Add member</Button>
    </form>
    {loading ? <p className="text-sm text-muted-foreground">Loading team…</p> : members.length ? <Table><TableHeader><TableRow><TableHead>Member</TableHead><TableHead>Role</TableHead><TableHead className="text-right">Access</TableHead></TableRow></TableHeader><TableBody>{members.map(member => <TableRow key={member.id}><TableCell className="max-w-48 truncate" title={member.customer_email}>{member.customer_email}</TableCell><TableCell><select aria-label={`Role for ${member.customer_email}`} className={selectClass} disabled={busy} value={member.role} onChange={e => void update("PATCH", member.id, e.target.value)}>{member.role === "custom" && <option value="custom">Custom</option>}{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></TableCell><TableCell className="text-right">{removing === member.id ? <div className="flex justify-end gap-2"><Button size="sm" variant="destructive" disabled={busy} loading={busy && activeAction === `DELETE:${member.id}`} onClick={() => void update("DELETE", member.id)}>Revoke access</Button><Button size="sm" variant="ghost" disabled={busy} onClick={() => setRemoving(null)}>Cancel</Button></div> : <Button size="sm" variant="outline" disabled={busy} onClick={() => setRemoving(member.id)}>Revoke</Button>}</TableCell></TableRow>)}</TableBody></Table> : <p className="text-sm text-muted-foreground">No team members for this service.</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}{notice && <p role="status" className="text-sm text-green-700 dark:text-green-400">{notice}</p>}
  </CardContent></Card>
}
