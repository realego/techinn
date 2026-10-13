"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"

import { GoogleSignInButton } from "@/components/google-sign-in-button"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { registerCustomer, signIn } from "@/lib/auth"
import { getLoginReturnPath, useLoginReturnPath } from "@/lib/auth-redirect"

const authInputClassName =
  "border-black bg-background shadow-sm placeholder:text-muted-foreground/80 focus-visible:border-black focus-visible:ring-orange-500/25 dark:border-white dark:focus-visible:border-white"

export function LoginForm(props: React.ComponentProps<"div">) {
  const router = useRouter()
  const [isRegistering, setIsRegistering] = useState(false)
  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const returnPath = useLoginReturnPath()

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmitting(true)
    setError("")
    try {
      if (isRegistering) {
        await registerCustomer({
          first_name: firstName,
          last_name: lastName,
          email,
          password,
        })
      } else {
        await signIn(email, password)
      }
      router.replace(getLoginReturnPath())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign in. Try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6" {...props}>
      <Card>
        <CardHeader className="text-center">
          <CardTitle className="text-xl">
            {isRegistering ? "Create your TechInn account" : "Welcome back"}
          </CardTitle>
          <CardDescription>
            {isRegistering
              ? "Create an account to manage your TechInn services."
              : "Sign in to manage your domains, hosting, and email."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <GoogleSignInButton disabled={isSubmitting} />
          <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            <span>OR USE EMAIL</span>
            <span className="h-px flex-1 bg-border" />
          </div>
          <form onSubmit={submit}>
            <FieldGroup>
              {isRegistering && (
                <div className="grid grid-cols-2 gap-3">
                  <Field>
                    <FieldLabel htmlFor="first-name">First name</FieldLabel>
                    <Input
                      autoComplete="given-name"
                      className={authInputClassName}
                      id="first-name"
                      onChange={(event) => setFirstName(event.target.value)}
                      required
                      value={firstName}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="last-name">Last name</FieldLabel>
                    <Input
                      autoComplete="family-name"
                      className={authInputClassName}
                      id="last-name"
                      onChange={(event) => setLastName(event.target.value)}
                      value={lastName}
                    />
                  </Field>
                </div>
              )}
              <Field>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input
                  autoComplete="email"
                  className={authInputClassName}
                  id="email"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  required
                  type="email"
                  value={email}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <Input
                  autoComplete={isRegistering ? "new-password" : "current-password"}
                  className={authInputClassName}
                  id="password"
                  minLength={isRegistering ? 8 : undefined}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
                {isRegistering && (
                  <FieldDescription>Use at least 8 characters.</FieldDescription>
                )}
              </Field>
              {error && (
                <p aria-live="polite" className="text-sm text-destructive">
                  {error}
                </p>
              )}
              <Field>
                <Button disabled={isSubmitting} loading={isSubmitting} type="submit">
                  {isSubmitting
                    ? "Please wait…"
                    : isRegistering
                      ? "Create account"
                      : "Sign in"}
                </Button>
                {!isRegistering && (
                  <Link className="text-center text-sm text-amber-700 underline-offset-4 hover:underline dark:text-amber-400" href={"/reset-password/?next=" + encodeURIComponent(returnPath)}>
                    Forgot your password?
                  </Link>
                )}
                <FieldDescription className="text-center">
                  {isRegistering ? "Already have an account?" : "New to TechInn?"}{" "}
                  <button
                    className="font-medium text-primary underline-offset-4 hover:underline"
                    onClick={() => {
                      setIsRegistering(!isRegistering)
                      setError("")
                    }}
                    type="button"
                  >
                    {isRegistering ? "Sign in" : "Create an account"}
                  </button>
                </FieldDescription>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
