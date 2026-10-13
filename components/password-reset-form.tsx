"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"

import { TechInnBrand } from "@/components/logos/techinn-brand"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { confirmPasswordReset, requestPasswordReset } from "@/lib/auth"
import { safeReturnPath } from "@/lib/auth-redirect"

const authInputClassName =
  "border-black bg-background shadow-sm placeholder:text-muted-foreground/80 focus-visible:border-black focus-visible:ring-orange-500/25 dark:border-white dark:focus-visible:border-white"

function PasswordResetFormContent() {
  const searchParams = useSearchParams()
  const uid = searchParams.get("uid") ?? ""
  const token = searchParams.get("token") ?? ""
  const hasResetToken = Boolean(uid && token)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmation, setConfirmation] = useState("")
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [isWorking, setIsWorking] = useState(false)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage("")
    setError("")
    if (hasResetToken && password !== confirmation) {
      setError("Your new password and confirmation do not match.")
      return
    }
    setIsWorking(true)
    try {
      const result = hasResetToken
        ? await confirmPasswordReset({ uid, token, new_password: password })
        : await requestPasswordReset(email)
      setMessage(result.detail)
      setPassword("")
      setConfirmation("")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The password request could not be completed.")
    } finally {
      setIsWorking(false)
    }
  }

  return (
    <Card className="border-border/70 shadow-lg shadow-black/5">
      <CardHeader className="text-center">
        <TechInnBrand className="mx-auto mb-3 w-40" />
        <CardTitle className="text-2xl">{hasResetToken ? "Choose a new password" : "Reset your password"}</CardTitle>
        <CardDescription>
          {hasResetToken
            ? "Use a strong password you have not used for this account before."
            : "Enter the email address on your TechInn account and we’ll send a secure reset link."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
          {!hasResetToken ? (
            <label className="grid gap-2 text-sm font-medium">
              Account email
              <Input className={authInputClassName} autoComplete="email" onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required type="email" value={email} />
            </label>
          ) : (
            <>
              <label className="grid gap-2 text-sm font-medium">
                New password
                <Input className={authInputClassName} autoComplete="new-password" minLength={8} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Confirm new password
                <Input className={authInputClassName} autoComplete="new-password" minLength={8} onChange={(event) => setConfirmation(event.target.value)} required type="password" value={confirmation} />
              </label>
            </>
          )}
          {error && <p aria-live="polite" className="text-sm text-destructive">{error}</p>}
          {message && <p aria-live="polite" className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">{message}</p>}
          <Button className="w-full" disabled={isWorking} loading={isWorking} type="submit">
            {isWorking ? "Please wait…" : hasResetToken ? "Set new password" : "Send reset link"}
          </Button>
          <Link className="block text-center text-sm text-amber-700 underline-offset-4 hover:underline dark:text-amber-400" href={"/login/?next=" + encodeURIComponent(safeReturnPath(searchParams.get("next")))}>
            Return to sign in
          </Link>
        </form>
      </CardContent>
    </Card>
  )
}

export function PasswordResetForm() {
  return (
    <Suspense fallback={<div className="w-full max-w-md animate-pulse rounded-xl border bg-card p-12" />}>
      <PasswordResetFormContent />
    </Suspense>
  )
}
