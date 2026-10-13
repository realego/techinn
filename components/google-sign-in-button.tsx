"use client"

import { useRouter } from "next/navigation"
import Script from "next/script"
import { useCallback, useRef, useState } from "react"

import { ApiError } from "@/lib/api"
import { signInWithGoogle } from "@/lib/auth"
import { getLoginReturnPath } from "@/lib/auth-redirect"

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string
            callback: (response: { credential?: string }) => void
          }) => void
          renderButton: (
            element: HTMLElement,
            options: {
              theme: "outline" | "filled_black"
              size: "large"
              text: "continue_with"
              shape: "rectangular"
              width: number
            },
          ) => void
        }
      }
    }
  }
}

const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID

export function GoogleSignInButton({ disabled = false }: { disabled?: boolean }) {
  const router = useRouter()
  const buttonRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState("")
  const [isWorking, setIsWorking] = useState(false)

  const handleGoogleResponse = useCallback(async (response: { credential?: string }) => {
    if (!response.credential) {
      setError("Google did not return a sign-in credential. Please try again.")
      return
    }
    setIsWorking(true)
    setError("")
    try {
      await signInWithGoogle(response.credential)
      router.replace(getLoginReturnPath())
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) {
        setError("The TechInn sign-in service is temporarily unavailable. Please try email sign-in instead.")
      } else {
        setError(cause instanceof Error ? cause.message : "Google sign-in could not be completed.")
      }
    } finally {
      setIsWorking(false)
    }
  }, [router])

  const renderGoogleButton = useCallback(() => {
    const element = buttonRef.current
    const google = window.google
    if (!googleClientId || !element || !google) return
    element.replaceChildren()
    google.accounts.id.initialize({
      client_id: googleClientId,
      callback: (response) => void handleGoogleResponse(response),
    })
    google.accounts.id.renderButton(element, {
      theme: document.documentElement.classList.contains("dark") ? "filled_black" : "outline",
      size: "large",
      text: "continue_with",
      shape: "rectangular",
      width: Math.max(200, Math.min(element.clientWidth, 360)),
    })
  }, [handleGoogleResponse])

  return (
    <div className="space-y-2 rounded-xl border border-orange-200/80 bg-gradient-to-br from-orange-50/90 via-background to-background p-3 shadow-sm dark:border-orange-900/70 dark:from-orange-950/30">
      {googleClientId ? (
        <>
          <p className="text-center text-xs font-medium text-muted-foreground">
            Sign in securely with your Google account
          </p>
          <Script
            onLoad={renderGoogleButton}
            src="https://accounts.google.com/gsi/client"
            strategy="afterInteractive"
          />
          <div className="flex min-h-11 items-center justify-center overflow-hidden rounded-lg bg-background">
            <div aria-label="Continue with Google" className={`w-full ${disabled || isWorking ? "pointer-events-none opacity-60" : ""}`} ref={buttonRef} />
          </div>
          {isWorking && <p className="text-center text-sm text-muted-foreground">Signing in with Google…</p>}
        </>
      ) : (
        <>
          <button
            className="flex h-10 w-full items-center justify-center gap-2 rounded-md border bg-background text-sm font-medium text-muted-foreground"
            disabled
            type="button"
          >
            <GoogleMark />
            Continue with Google
          </button>
          <p className="text-center text-xs text-muted-foreground">Google sign-in is not configured yet. Please use email sign-in.</p>
        </>
      )}
      {error && <p aria-live="polite" className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

function GoogleMark() {
  return (
    <svg aria-hidden="true" className="size-4" viewBox="0 0 48 48">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.9c-.58 2.96-2.26 5.48-4.76 7.18l7.73 6C44.38 38.05 46.98 31.9 46.98 24.55Z" />
      <path fill="#FBBC05" d="M10.53 28.59A14.5 14.5 0 0 1 9.75 24c0-1.59.27-3.12.76-4.59l-7.98-6.19A23.93 23.93 0 0 0 0 24c0 3.87.93 7.54 2.56 10.78l7.97-6.19Z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.9-5.8l-7.73-6c-2.15 1.45-4.92 2.3-8.17 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z" />
    </svg>
  )
}
