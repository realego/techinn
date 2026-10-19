import type { Metadata } from "next"

import { DashboardShell } from "@/components/dashboard-shell"

export const metadata: Metadata = {
  title: { absolute: "Customer Dashboard | TechInn" },
  robots: { index: false, follow: false },
}

export default function Page() {
  return <DashboardShell />
}
