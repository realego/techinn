"use client"

import {
  IconChartBar,
  IconCreditCard,
  IconDashboard,
  IconHelp,
  IconHistory,
  IconListDetails,
  IconMail,
  IconSettings,
  IconUsers,
  IconWorld,
  IconWorldWww,
} from "@tabler/icons-react"
import Link from "next/link"
import * as React from "react"

import { TechInnBrand } from "@/components/logos/techinn-brand"
import { NavMain } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { useCustomerProfile } from "@/lib/auth"

const navMain = [
  { title: "Overview", url: "/dashboard/", icon: IconDashboard },
  { title: "Web & hosting", url: "/dashboard/web/", icon: IconWorldWww },
  { title: "Domains & DNS", url: "/dashboard/domains/", icon: IconWorld },
  { title: "Email", url: "/dashboard/email/", icon: IconMail },
  { title: "Analytics", url: "/dashboard/analytics/", icon: IconChartBar },
  { title: "Billing", url: "/dashboard/billing/", icon: IconCreditCard },
  { title: "Activity", url: "/dashboard/activity/", icon: IconHistory },
  { title: "Account & security", url: "/dashboard/account/", icon: IconSettings },
  { title: "Team access", url: "/dashboard/team/", icon: IconUsers },
  { title: "Connections", url: "/dashboard/connections/", icon: IconListDetails },
]

const navSecondary = [
  { title: "Add a service", url: "/shop/", icon: IconWorld },
  { title: "How-to guides", url: "/how-to/", icon: IconHelp },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const customer = useCustomerProfile()
  const name = [customer?.first_name, customer?.last_name].filter(Boolean).join(" ") || "TechInn customer"

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="data-[slot=sidebar-menu-button]:p-1.5!">
              <Link href="/">
                <TechInnBrand className="w-24" />
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navMain} />
        <NavSecondary items={navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser
          user={{
            name,
            email: customer?.email ?? "",
            avatar: "",
          }}
        />
      </SidebarFooter>
    </Sidebar>
  )
}
