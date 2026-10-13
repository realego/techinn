import type { Metadata } from "next"

import { PasswordResetForm } from "@/components/password-reset-form"

export const metadata: Metadata = {
  title: { absolute: "Reset Your Password | TechInn" },
  robots: { index: false, follow: false },
}

export default function PasswordResetPage() {
  return (
    <main className="flex min-h-svh items-center justify-center bg-muted px-4 py-10">
      <div className="w-full max-w-md">
        <PasswordResetForm />
      </div>
    </main>
  )
}
