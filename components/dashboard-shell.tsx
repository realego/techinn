import { AppSidebar } from "@/components/app-sidebar"
import { CustomerDashboard } from "@/components/customer-dashboard"
import { SiteHeader } from "@/components/site-header"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

export function DashboardShell({ view = "overview" }: { view?: string }) {
  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <SiteHeader />
        <CustomerDashboard view={view} />
      </SidebarInset>
    </SidebarProvider>
  )
}
