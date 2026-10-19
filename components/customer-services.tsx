"use client"

import { Bot, ExternalLink, Globe2, Search, Smartphone } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

type Service = {
  uuid: string; product: string; product_slug: string; status: string
  service_type?: string; service_type_name?: string
  billing?: { unit_price: string; currency: string; next_due_at: string | null } | null
  dashboards?: { name: string; url: string }[]
  expires_at: string | null; is_owner: boolean
  hosting: { primary_domain: string | null } | null
}
const routes: Record<string, string> = { "web-hosting": "/dashboard/web/", "email-hosting": "/dashboard/email/", "domain-registration": "/dashboard/domains/", domains: "/dashboard/domains/" }
const labels: Record<string, string> = { pending: "Awaiting setup", provisioning: "Setting up", active: "Active", failed: "Needs attention", suspended: "Suspended", expired: "Expired", cancelled: "Cancelled", terminated: "Terminated" }

const serviceTabs = [
  { value: "all", label: "All services", types: [], icon: Globe2, empty: "No services yet", href: "/shop/" },
  { value: "chatbots", label: "Chatbots", types: ["chatbot-development"], icon: Bot, empty: "No chatbot services yet", href: "/shop/?service=chatbot" },
  { value: "websites", label: "Website development", types: ["website-design", "website-development"], icon: Globe2, empty: "No website development services yet", href: "/shop/?service=website" },
  { value: "apps", label: "App development", types: ["app-development"], icon: Smartphone, empty: "No app development services yet", href: "/shop/?service=app" },
]

export function CustomerServices({ services }: { services: Service[] }) {
  const [tab, setTab] = useState("all")
  const [search, setSearch] = useState("")
  const selectedTab = serviceTabs.find(item => item.value === tab) ?? serviceTabs[0]
  const EmptyIcon = selectedTab.icon
  const visible = services.filter(service => (!selectedTab.types.length || selectedTab.types.includes(service.service_type ?? "")) && `${service.product} ${service.hosting?.primary_domain ?? ""}`.toLowerCase().includes(search.toLowerCase()))
  return <section className="min-w-0 space-y-4">
    <header className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">Your <span className="text-orange-600 dark:text-orange-400">services</span></h2><p className="mt-1 text-sm text-muted-foreground">Manage your chatbots, websites, apps and hosting in one place.</p></div><Button asChild size="sm"><Link href="/shop/">Add a service</Link></Button></header>
    <div className="min-w-0 overflow-hidden rounded-lg border">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 border-b bg-muted/30 p-3"><Tabs className="min-w-0 max-w-full" value={tab} onValueChange={setTab}><TabsList aria-label="Service categories" className="flex max-w-full gap-1 overflow-x-auto p-1 group-data-[orientation=horizontal]/tabs:h-auto">{serviceTabs.map(item => <TabsTrigger key={item.value} value={item.value} className="h-9 min-w-max shrink-0 whitespace-nowrap px-3">{item.value !== "all" && <item.icon className="size-4" />}{item.label}</TabsTrigger>)}</TabsList></Tabs><div className="relative w-full min-w-0 sm:w-64"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input aria-label="Search your services" className="h-9 pl-9" placeholder="Find a service or domain" value={search} onChange={e => setSearch(e.target.value)} /></div></div>
      <div className="divide-y">{visible.map(service => {
        const chatbot = service.service_type === "chatbot-development"
        const Icon = chatbot ? Bot : service.service_type === "app-development" ? Smartphone : Globe2
        const route = routes[service.service_type ?? ""]
        const active = service.status === "active"
        return <article key={service.uuid} className="flex min-w-0 flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-3"><span className={`shrink-0 rounded-lg p-2.5 ${chatbot ? "bg-violet-500/10 text-violet-600 dark:text-violet-300" : "bg-orange-500/10 text-orange-600 dark:text-orange-300"}`}><Icon className="size-5" /></span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="break-words text-sm font-semibold">{service.product}</h3><Badge variant={service.status === "failed" ? "destructive" : active ? "default" : "secondary"}>{labels[service.status] ?? service.status}</Badge></div><p className="mt-1 truncate text-xs text-muted-foreground">{service.hosting?.primary_domain || service.service_type_name || "TechInn service"}</p>{service.billing && <p className="mt-1 text-xs text-muted-foreground">Service price: {service.billing.currency} {service.billing.unit_price}{service.billing.next_due_at ? ` · Renewal due ${new Date(service.billing.next_due_at).toLocaleDateString()}` : ""}</p>}{service.expires_at && <p className="mt-1 text-xs text-muted-foreground">Service period ends {new Date(service.expires_at).toLocaleDateString()}</p>}</div></div>
          <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">
            {route && <Button asChild className="max-w-full" size="sm" variant="outline"><Link className="max-w-full truncate" href={route}>Manage service</Link></Button>}
            {active && service.dashboards?.map(link => <Button asChild className="max-w-full" size="sm" key={link.url}><a className="max-w-full truncate" href={link.url} target="_blank" rel="noopener noreferrer"><ExternalLink className="size-3.5 shrink-0" />{link.name}</a></Button>)}
            {!route && !service.dashboards?.length && <p className="max-w-xs text-xs text-muted-foreground">{service.status === "pending" || service.status === "provisioning" ? "Your project is awaiting setup. Dashboard access appears here when it is ready." : active ? "Dashboard access has not been assigned yet." : "Dashboard access is unavailable while this service is inactive."}</p>}
          </div>
        </article>
      })}</div>
      {!visible.length && <div className="px-4 py-10 text-center"><EmptyIcon className="mx-auto mb-3 size-7 text-orange-500" /><p className="text-sm font-medium">{search ? "No matching services" : selectedTab.empty}</p><p className="mt-1 text-xs text-muted-foreground">{search ? "Try a different name or domain." : "Your paid services will appear here, including projects that are being set up."}</p>{!search && <Button asChild className="mt-4" size="sm" variant="outline"><Link href={selectedTab.href}>Browse services</Link></Button>}</div>}
    </div>
  </section>
}
