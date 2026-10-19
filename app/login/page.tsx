import type { Metadata } from "next"
import Link from "next/link"

import { LoginForm } from "@/components/login-form"
import { TechInnBrand } from "@/components/logos/techinn-brand"
import { SelectedPlanSummary } from "@/components/selected-plan-summary"

export const metadata: Metadata = {
  title: { absolute: "Sign In or Create an Account | TechInn" },
  robots: { index: false, follow: false },
}

export default function LoginPage() {
  return (
    <main className="flex min-h-svh items-center justify-center bg-muted p-4 sm:p-8">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-2xl border bg-background shadow-2xl shadow-black/10 lg:grid-cols-[minmax(0,1fr)_minmax(390px,0.85fr)]">
        <section className="hidden flex-col justify-between bg-slate-950 p-10 text-white lg:flex">
          <Link href="/" aria-label="TechInn home" className="w-fit">
            <TechInnBrand className="w-48" />
          </Link>
          <div className="space-y-5">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-amber-400">TechInn customer portal</p>
            <h1 className="max-w-md text-4xl font-semibold leading-tight">Your domains, websites and email—together.</h1>
            <p className="max-w-md text-base leading-relaxed text-slate-300">
              Sign in to manage your hosting, domain settings, business email and account details.
            </p>
            <div className="flex flex-wrap gap-2 pt-2 text-xs">
              {["Web hosting", "Domains & DNS", "Business email"].map((service) => (
                <span className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-slate-200" key={service}>{service}</span>
              ))}
            </div>
          </div>
          <p className="text-xs text-slate-400">Secure access to your TechInn account.</p>
        </section>
        <section className="flex flex-col justify-center gap-5 p-4 sm:p-8 lg:p-10">
          <Link href="/" aria-label="TechInn home" className="mx-auto lg:hidden">
            <TechInnBrand className="w-44" />
          </Link>
          <div className="mx-auto w-full max-w-md space-y-5">
            <SelectedPlanSummary />
            <LoginForm />
          </div>
        </section>
      </div>
    </main>
  )
}
