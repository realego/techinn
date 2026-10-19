import type { Metadata } from "next"
import { notFound } from "next/navigation"

import { DashboardShell } from "@/components/dashboard-shell"

const sections = [
  "services",
  "web",
  "domains",
  "email",
  "analytics",
  "billing",
  "activity",
  "account",
  "team",
  "connections",
]

const titles: Record<string, string> = {
  services: "My Services",
  web: "Web & Hosting",
  domains: "Domains & DNS",
  email: "Business Email",
  analytics: "Analytics & Performance",
  billing: "Billing & Invoices",
  activity: "Notifications & Activity",
  account: "Account & Security",
  team: "Team Access",
  connections: "Provider Connections",
}

export const dynamicParams = false

export function generateStaticParams() {
  return sections.map((section) => ({ section }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ section: string }>
}): Promise<Metadata> {
  const { section } = await params
  return {
    title: { absolute: `${titles[section] ?? "Dashboard"} | TechInn` },
    robots: { index: false, follow: false },
  }
}

export default async function DashboardSectionPage({
  params,
}: {
  params: Promise<{ section: string }>
}) {
  const { section } = await params
  if (!sections.includes(section)) notFound()
  return <DashboardShell view={section} />
}
