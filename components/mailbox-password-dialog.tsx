"use client"

import * as Dialog from "@radix-ui/react-dialog"
import { Eye, EyeOff, X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { apiRequest } from "@/lib/api"

export function MailboxPasswordDialog({ mailbox, onClose, onComplete }: {
  mailbox: { id: number; email_address: string }
  onClose: () => void
  onComplete: () => void
}) {
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [visible, setVisible] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  useEffect(() => {
    if (!cooldown) return
    const timer = window.setTimeout(() => setCooldown(cooldown - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])
  const [busy, setBusy] = useState(false)
  const [activeAction, setActiveAction] = useState<"send" | "verify" | null>(null)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const lock = useRef(false)
  const codeInput = useRef<HTMLInputElement>(null)
  const field = "h-10 border-orange-300 focus-visible:border-orange-500 focus-visible:ring-orange-500/20 dark:border-orange-400/60"

  async function sendCode() {
    if (lock.current) return
    if (cooldown > 0) return
    setActiveAction("send")
    setCooldown(120)
    lock.current = true; setBusy(true); setError(""); setMessage("")
    try {
      await apiRequest(`/services/mailboxes/${mailbox.id}/request-password-reset/`, { method: "POST" })
      setMessage("Code sent to your TechInn account email. It expires in 10 minutes. Wait two minutes before requesting another.")
      codeInput.current?.focus()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not request a code.") }
    finally { lock.current = false; setBusy(false) }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (lock.current) return
    setError("")
    if (!/^\d{6}$/.test(code)) { setError("Enter the six-digit code from your email."); return }
    if (password.length < 8 || password !== confirmation) { setError("Use at least 8 characters and enter the same password twice."); return }
    setActiveAction("verify")
    lock.current = true; setBusy(true)
    try {
      await apiRequest(`/services/mailboxes/${mailbox.id}/reset-password/`, { method: "POST", body: JSON.stringify({ otp: code, password }) })
      onComplete()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not reset this password.") }
    finally { lock.current = false; setBusy(false) }
  }

  return <Dialog.Root open onOpenChange={(open) => { if (!open && !busy) onClose() }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[80] bg-black/60 backdrop-blur-sm" />
      <Dialog.Content className="fixed left-1/2 top-1/2 z-[81] max-h-[90dvh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-orange-300 bg-background p-5 shadow-xl dark:border-orange-400/60" onOpenAutoFocus={(event) => { event.preventDefault(); codeInput.current?.focus() }}>
        <Dialog.Title className="pr-8 text-lg font-semibold">Reset mailbox password</Dialog.Title>
        <Dialog.Description className="mt-2 break-all text-sm text-muted-foreground">{mailbox.email_address}. Request a code to your TechInn account email, then choose your new mailbox password.</Dialog.Description>
        <Dialog.Close asChild><Button aria-label="Close password reset" className="absolute right-3 top-3" size="icon" variant="ghost" disabled={busy}><X className="size-4" /></Button></Dialog.Close>
        <form onSubmit={(event) => void submit(event)} className="mt-5 grid gap-4">
          {error && <p role="alert" className="rounded-md border border-orange-300 bg-orange-50 p-3 text-sm text-orange-900 dark:border-white/80 dark:bg-orange-500/10 dark:text-orange-200">{error}</p>}
          {message && <p role="status" className="text-sm text-orange-700 dark:text-orange-300">{message}</p>}
          <Button type="button" variant="outline" loading={busy && activeAction === "send"} disabled={busy || cooldown > 0} onClick={() => void sendCode()}>{cooldown > 0 ? `Request another code in ${cooldown}s` : "Send verification code"}</Button>
          <label className="grid gap-1.5 text-sm font-medium">Verification code<Input ref={codeInput} className={field} autoComplete="one-time-code" inputMode="numeric" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="6-digit code" /></label>
          <label className="grid gap-1.5 text-sm font-medium">New password<Input className={field} autoComplete="new-password" type={visible ? "text" : "password"} minLength={8} maxLength={128} required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" /></label>
          <label className="grid gap-1.5 text-sm font-medium">Confirm password<Input className={field} autoComplete="new-password" type={visible ? "text" : "password"} minLength={8} maxLength={128} required value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder="Enter it again" /></label>
          <Button type="button" variant="ghost" className="justify-self-start" onClick={() => setVisible(!visible)}>{visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}{visible ? "Hide passwords" : "Show passwords"}</Button>
          <Button type="submit" disabled={busy} loading={busy && activeAction === "verify"}>Verify and set password</Button>
        </form>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
