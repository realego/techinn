"use client"

import {
  Activity,
  ArrowUpRight,
  Building2,
  CalendarClock,
  Check,
  ChevronDown,
  CircleAlert,
  CircleHelp,
  Cloud,
  CreditCard,
  Database,
  Eraser,
  ExternalLink,
  Eye,
  EyeOff,
  Globe2,
  KeyRound,
  Mail,
  Pencil,
  Plus,
  ReceiptText,
  RefreshCw,
  Save,
  Search,
  Server,
  ShieldCheck,
  ShoppingCart,
  Trash2,
  UserRound,
  X,
} from "lucide-react"
import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react"

import { MailboxPasswordDialog } from "@/components/mailbox-password-dialog"
import { CustomerServices } from "@/components/customer-services"
import { CustomerSettings } from "@/components/customer-settings"
import { DomainConnections } from "@/components/domain-connections"
import { DomainSearchPanel } from "@/components/domain-search-panel"
import { ServiceTeam } from "@/components/service-team"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ApiError, apiRequest, type CheckoutPayment, type CustomerProfile, getApiSession, pollCheckoutPayment, saveApiSession } from "@/lib/api"
import { confirmPasswordReset, requestPasswordReset, signOut, useCustomerProfile, useSignedIn } from "@/lib/auth"
import { useSignInHref } from "@/lib/auth-redirect"
import { addStorageAddonToCart } from "@/lib/cart-store"

type DNSRecord = {
  id: number
  name: string
  record_type: string
  content: string
  ttl: number
  priority: number | null
  proxied: boolean
  synced_at: string | null
}

type DashboardDomain = {
  id: number
  name: string
  status: string
  expires_at: string | null
  auto_renew: boolean
  nameservers: string[]
  registration?: { status: string; label: string; message: string }
  permissions: {
    can_manage_domains: boolean
    can_manage_dns: boolean
    can_manage_hosting: boolean
    can_manage_email: boolean
    can_view_billing: boolean
  }
  dns: null | {
    id: number
    status: string
    dnssec_enabled: boolean
    last_synced_at: string | null
    records: DNSRecord[]
  }
}

type DashboardMailbox = {
  id: number
  email_address: string
  webmail_url?: string
  quota_mb: number
  used_mb: number
  status: string
  error_message?: string | null
  pending_action?: string | null
}

type DashboardHosting = {
  id: number
  status: string
  server_name: string
  username: string
  primary_domain: string | null
  domain_status?: string
  preview_url?: string | null
  certificate_status?: "not_installed" | "pending" | "active" | "error"
  certificate_error?: string
  websites: DashboardHostedWebsite[]
  resources: { type: string; limit: string; used: string; unit: string }[]
  mailboxes: DashboardMailbox[]
} | null

type DashboardHostedWebsite = {
  id: number
  domain_name: string
  master_domain: string
  status: "pending" | "active" | "error"
  last_error: string
  certificate_status: "not_installed" | "pending" | "active" | "error"
  certificate_error: string
}

type DashboardService = {
  uuid: string
  product: string
  product_slug: string
  service_type?: string
  service_type_name?: string
  dashboards?: { name: string; url: string }[]
  renewal?: { href: string; service_uuid: string } | null
  billing?: { unit_price: string; currency: string; next_due_at: string | null; interval?: string | null } | null
  status: string
  started_at: string | null
  expires_at: string | null
  next_due_at: string | null
  auto_renew: boolean
  is_owner: boolean
  permissions: {
    can_manage_domains: boolean
    can_manage_dns: boolean
    can_manage_hosting: boolean
    can_manage_email: boolean
    can_view_billing: boolean
  }
  hosting: DashboardHosting
  domains: DashboardDomain[]
  domain_options?: { id: number; name: string; status: string; selected: boolean }[]
}

function mailboxStorage(hosting: DashboardHosting) {
  if (!hosting) return {
    limitMB: null,
    webUsedMB: 0,
    mailUsedMB: 0,
    allocatedMB: 0,
    committedMB: 0,
    actualUsedMB: 0,
    availableMB: null,
  }
  const disk = hosting.resources.find((resource) => resource.type === "disk")
  if (!disk) return {
    limitMB: null,
    webUsedMB: 0,
    mailUsedMB: 0,
    allocatedMB: 0,
    committedMB: 0,
    actualUsedMB: 0,
    availableMB: null,
  }
  const unit = disk.unit.toLowerCase()
  const factor = unit === "gb" || unit === "gib" ? 1024 : unit === "mb" || unit === "mib" ? 1 : 0
  if (!factor) return {
    limitMB: null,
    webUsedMB: 0,
    mailUsedMB: 0,
    allocatedMB: 0,
    committedMB: 0,
    actualUsedMB: 0,
    availableMB: null,
  }
  const limitMB = Math.floor(Number(disk.limit) * factor)
  const mailboxes = hosting.mailboxes.filter((mailbox) => mailbox.status !== "deleted")
  const allocatedMB = mailboxes
    .reduce((total, mailbox) => total + mailbox.quota_mb, 0)
  const webUsedMB = Math.ceil(Number(disk.used) * factor)
  const mailUsedMB = mailboxes.reduce((total, mailbox) => total + mailbox.used_mb, 0)
  const committedMB = webUsedMB + allocatedMB
  return {
    limitMB,
    webUsedMB,
    mailUsedMB,
    allocatedMB,
    committedMB,
    actualUsedMB: webUsedMB + mailUsedMB,
    availableMB: Math.max(0, limitMB - committedMB),
  }
}

function formatStorageMB(value: number) {
  return value >= 1024
    ? `${(value / 1024).toFixed(value % 1024 === 0 ? 0 : 2)} GB`
    : `${value.toLocaleString()} MB`
}

function mailboxSetupMessage(message?: string | null) {
  if (!message) return "The mail server could not finish creating this mailbox."
  if (/already exists/i.test(message)) {
    return "This mailbox was created on the mail server, but setup did not finish in the dashboard. Choose a new password below and retry to finish setup."
  }
  return message.replace(/CyberPanel/gi, "mail server")
}

function mailboxQuotaInputMax(hosting: DashboardHosting, unit: string, currentAllocationMB = 0) {
  const availableMB = mailboxStorage(hosting).availableMB
  if (availableMB === null) return undefined
  return (availableMB + currentAllocationMB) / (unit === "GB" ? 1024 : 1)
}

type ProviderConnection = {
  id: number
  provider: string
  name: string
  status: string
  last_verified_at: string | null
}

type DashboardPayload = {
  services: DashboardService[]
  provider_connections: ProviderConnection[]
}

type CloudflareZoneOption = {
  connection_id: number
  domain_id: number
  domain: string
  cloudflare_zone_id: string
  status: string
}

type CloudflareExternalZone = {
  id: string
  name: string
  status: string
}

type DashboardInvoice = {
  invoice_number: string
  status: string
  currency: string
  subtotal: string
  discount_total: string
  tax_total: string
  total: string
  amount_paid: string
  due_at: string | null
  paid_at: string | null
  created_at: string
  is_test: boolean
  payment_method: string | null
  items: { description: string; quantity: number; unit_price: string; subtotal: string }[]
}

type DashboardWallet = {
  balance: string
  currency: string
  transactions: { type: string; amount: string; description: string; is_test: boolean; created_at: string }[]
}

type ProvisioningAction = {
  id: number
  service: string
  action_type: string
  status: string
  scheduled_at: string
  completed_at: string | null
  error_message?: string
}

type ServiceActivity = {
  id: number
  event_type: string
  entity_type: string
  entity_id: string
  payload: Record<string, unknown>
  created_at: string
}

function DismissibleAlert({
  id,
  message,
  className = "",
  children,
}: {
  id: string
  message: string
  className?: string
  children?: ReactNode
}) {
  const storageKey = `techinn-dismissed-alert:${id}`
  const getSnapshot = useCallback(() => window.localStorage.getItem(storageKey), [storageKey])
  const dismissedMessage = useSyncExternalStore(subscribeToDismissedAlerts, getSnapshot, () => null)
  const dismissed = dismissedMessage === message

  if (dismissed) return null

  return (
    <div className={`flex items-start justify-between gap-2 ${className}`} role="alert">
      <div className="min-w-0 flex-1">{children ?? <p>{message}</p>}</div>
      <button
        aria-label="Dismiss error"
        className="shrink-0 rounded p-1 opacity-70 transition hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current"
        onClick={() => {
          window.localStorage.setItem(storageKey, message)
          window.dispatchEvent(new Event("techinn-dismissed-alert"))
        }}
        type="button"
      >
        <X aria-hidden="true" className="size-4" />
      </button>
    </div>
  )
}

function subscribeToDismissedAlerts(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange)
  window.addEventListener("techinn-dismissed-alert", onStoreChange)
  return () => {
    window.removeEventListener("storage", onStoreChange)
    window.removeEventListener("techinn-dismissed-alert", onStoreChange)
  }
}

type ListResponse<T> = T[] | { results: T[] }

const emptyServices: DashboardService[] = []
const depositCheckoutKeyStorage = "techinn-balance-deposit-checkout-key"
const checkoutPaymentMethods = [
  { id: "ecocash", name: "EcoCash", image: "/payment-methods/ecocash.png", width: 74, height: 22 },
  { id: "onemoney", name: "OneMoney", image: "/payment-methods/onemoney.png", width: 30, height: 22 },
  { id: "card", name: "Cards", image: "/payment-methods/cards.jpg", width: 72, height: 24 },
]
const dashboardViewTitles: Record<string, string> = {
  services: "My services",
  overview: "Dashboard overview",
  web: "Web & hosting",
  domains: "Domains & DNS",
  email: "Business email",
  analytics: "Analytics & performance",
  billing: "Billing & invoices",
  activity: "Notifications & activity",
  account: "Account & security",
  team: "Team access",
  connections: "Domain connections",
}
const dashboardViewDescriptions: Record<string, string> = {
  services: "Your chatbots, websites, apps and hosting services.",
  overview: "A focused snapshot of your TechInn services and useful next steps.",
  web: "Manage websites, hosting plans, access details and allocated resources.",
  domains: "",
  email: "",
  analytics: "Review hosting resource usage and connected performance data.",
  billing: "Review invoices, outstanding balances and upcoming renewals.",
  activity: "Track service changes, provisioning requests and account events.",
  account: "Update your contact details and secure your TechInn account.",
  team: "Manage customer access to services you own.",
  connections: "Connect your domain to your website and email hosting.",
}
const dashboardDataViews = new Set([
  "services",
  "overview",
  "web",
  "domains",
  "email",
  "analytics",
  "team",
  "connections",
])

function listItems<T>(response: ListResponse<T>) {
  return Array.isArray(response) ? response : response.results
}

function StatusBadge({ status }: { status: string }) {
  const good = status === "active" || status === "completed"
  const overdue = status === "overdue" || status === "failed" || status === "error"
  return <Badge variant={overdue ? "destructive" : good ? "default" : "secondary"} className="capitalize">{status.replaceAll("_", " ")}</Badge>
}

function formatDate(value: string | null) {
  if (!value) return "Not set"
  return new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(new Date(value))
}

function formatResource(value: string, unit: string) {
  const amount = Number(value)
  return `${Number.isFinite(amount) ? amount.toLocaleString() : value} ${unit}`
}

function formatMoney(value: number | string, currency: string) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return `${value} ${currency}`
  return new Intl.NumberFormat("en", { style: "currency", currency }).format(amount)
}

function amountDue(invoice: DashboardInvoice) {
  return Math.max(Number(invoice.total) - Number(invoice.amount_paid), 0)
}

function isOpenInvoice(invoice: DashboardInvoice) {
  return ["unpaid", "partially_paid", "overdue"].includes(invoice.status)
}

export function CustomerDashboard({ view = "overview" }: { view?: string }) {
  const router = useRouter()
  const signedIn = useSignedIn()
  const signInHref = useSignInHref()
  const customer = useCustomerProfile()
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null)
  const [invoices, setInvoices] = useState<DashboardInvoice[]>([])
  const [wallet, setWallet] = useState<DashboardWallet | null>(null)
  const [invoiceFilter, setInvoiceFilter] = useState("all")
  const [openingFiles, setOpeningFiles] = useState<number | null>(null)
  const [selectedWebsiteByAccount, setSelectedWebsiteByAccount] = useState<Record<number, string>>({})
  const [subdomainByAccount, setSubdomainByAccount] = useState<Record<number, string>>({})
  const [fileManagerError, setFileManagerError] = useState<{ id: number; message: string } | null>(null)
  const [depositAmount, setDepositAmount] = useState("10.00")
  const [depositMethod, setDepositMethod] = useState<"ecocash" | "onemoney" | "card">("ecocash")
  const [depositPhone, setDepositPhone] = useState("")
  const [depositPayment, setDepositPayment] = useState<CheckoutPayment | null>(null)
  const [depositSubmitting, setDepositSubmitting] = useState(false)
  const [depositError, setDepositError] = useState("")
  const depositCheckoutKey = useRef<string | null>(typeof window === "undefined" ? null : window.sessionStorage.getItem(depositCheckoutKeyStorage))
  const [returnedBillingPaymentUuid] = useState(() => typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("payment") ?? "")
  const [renewalServiceUuid, setRenewalServiceUuid] = useState("")
  const [renewingServiceUuid, setRenewingServiceUuid] = useState("")
  const [renewalBillingInterval, setRenewalBillingInterval] = useState<"monthly" | "yearly">("monthly")
  const [provisioningActions, setProvisioningActions] = useState<ProvisioningAction[]>([])
  const [activity, setActivity] = useState<ServiceActivity[]>([])
  const [cloudflareZones, setCloudflareZones] = useState<CloudflareZoneOption[]>([])
  const [externalCloudflareZones, setExternalCloudflareZones] = useState<CloudflareExternalZone[]>([])
  const [cloudflareConnectionId, setCloudflareConnectionId] = useState("")
  const [externalZoneId, setExternalZoneId] = useState("")
  const [externalDomainService, setExternalDomainService] = useState("")
  const [mobileTablesOpen, setMobileTablesOpen] = useState<Record<string, boolean>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [isWorking, setIsWorking] = useState(false)
  const [activeAction, setActiveAction] = useState("")
  const workingOn = (action: string) => isWorking && activeAction === action
  const [error, setError] = useState("")
  const [billingError, setBillingError] = useState("")
  const [activityError, setActivityError] = useState("")
  const [notice, setNotice] = useState("")
  const [cloudflareToken, setCloudflareToken] = useState("")
  const [mailboxName, setMailboxName] = useState("")
  const [mailboxQuota, setMailboxQuota] = useState("100")
  const [mailboxQuotaUnit, setMailboxQuotaUnit] = useState("MB")
  const [editingMailboxQuotaId, setEditingMailboxQuotaId] = useState<number | null>(null)
  const [editingMailboxQuota, setEditingMailboxQuota] = useState("100")
  const [editingMailboxQuotaUnit, setEditingMailboxQuotaUnit] = useState("MB")
  const [passwordResetMailbox, setPasswordResetMailbox] = useState<DashboardMailbox | null>(null)
  const [mailboxPassword, setMailboxPassword] = useState("")
  const [showMailboxPassword, setShowMailboxPassword] = useState(false)
  const [retryMailboxPassword, setRetryMailboxPassword] = useState("")
  const [expandedHostingServiceUuid, setExpandedHostingServiceUuid] = useState<string | null>(null)
  const [requestedSubdomainDomain] = useState(() =>
    view === "web" && typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("create_subdomain_for")?.trim().toLowerCase() ?? ""
      : "",
  )
  const focusedSubdomainDomain = useRef("")

  const domainVisitChecked = useRef(false)
  const [expandedDomainId, setExpandedDomainId] = useState<number | null>(null)

  useEffect(() => {
    setRenewalServiceUuid(new URLSearchParams(window.location.search).get("renew") ?? "")
  }, [])
  const [expandedEmailDomainId, setExpandedEmailDomainId] = useState<number | null>(null)
  const [selectedEmailDomainByRoot, setSelectedEmailDomainByRoot] = useState<Record<number, string>>({})
  const [storageBillingIntervalByService, setStorageBillingIntervalByService] = useState<Record<string, "monthly" | "yearly">>({})
  const [dnsName, setDnsName] = useState("@")
  const [dnsType, setDnsType] = useState("A")
  const [dnsContent, setDnsContent] = useState("")
  const [dnsTtl, setDnsTtl] = useState("3600")
  const [dnsPriority, setDnsPriority] = useState("")
  const [dnsProxied, setDnsProxied] = useState(false)
  const [editingDnsRecord, setEditingDnsRecord] = useState<number | null>(null)
  const [dnsSearch, setDnsSearch] = useState("")
  const [mailboxSearch, setMailboxSearch] = useState("")
  const [accessEmail, setAccessEmail] = useState("")
  const [selectedMailbox, setSelectedMailbox] = useState("")
  const [profileForm, setProfileForm] = useState<{
    first_name: string
    last_name: string
    phone: string
    company_name: string
  } | null>(null)
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [accountPasswordOtpRequested, setAccountPasswordOtpRequested] = useState(false)
  const [accountPasswordOtp, setAccountPasswordOtp] = useState("")
  const [currentTime, setCurrentTime] = useState<number | null>(null)
  const profileValues = profileForm ?? {
    first_name: customer?.first_name ?? "",
    last_name: customer?.last_name ?? "",
    phone: customer?.phone ?? "",
    company_name: customer?.company_name ?? "",
  }

  const refreshDashboard = useCallback(async (signal?: AbortSignal, options?: { silent?: boolean }) => {
    if (!signedIn) {
      setDashboard(null)
      setInvoices([])
      setWallet(null)
      setProvisioningActions([])
      setActivity([])
      setIsLoading(false)
      return
    }
    setError("")
    setBillingError("")
    setActivityError("")
    if (!options?.silent) setIsLoading(true)
    try {
      if (dashboardDataViews.has(view)) {
        const result = await apiRequest<DashboardPayload>("/services/dashboard/", { signal })
        if (signal?.aborted) return
        setDashboard(result)
      }

      if (view === "billing") {
        const [invoicesResult, walletResult, result] = await Promise.all([
          apiRequest<ListResponse<DashboardInvoice>>("/billing/invoices/", { signal }),
          apiRequest<DashboardWallet>("/billing/balance/", { signal }),
          apiRequest<DashboardPayload>("/services/dashboard/", { signal }),
        ])
        if (signal?.aborted) return
        setInvoices(listItems(invoicesResult))
        setWallet(walletResult)
        setDashboard(result)
      } else {
        setInvoices([])
        setWallet(null)
      }

      if (view === "activity" || view === "analytics") {
        const actionResult = await apiRequest<ListResponse<ProvisioningAction>>("/services/provisioning-actions/", { signal })
        if (signal?.aborted) return
        setProvisioningActions(listItems(actionResult))
        if (view === "activity") {
          const activityResult = await apiRequest<ListResponse<ServiceActivity>>("/services/audit-events/", { signal })
          if (signal?.aborted) return
          setActivity(listItems(activityResult))
        } else {
          setActivity([])
        }
      } else {
        setProvisioningActions([])
        setActivity([])
      }
      setCurrentTime(Date.now())
    } catch (cause) {
      if (signal?.aborted) return
      const message = cause instanceof Error ? cause.message : "Could not load this dashboard section."
      if (view === "billing") setBillingError(message)
      else if (view === "activity") setActivityError(message)
      else if (view !== "account") setError(message)
    } finally {
      if (!signal?.aborted && !options?.silent) setIsLoading(false)
    }
  }, [signedIn, view])

  useEffect(() => {
    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) void refreshDashboard(controller.signal)
    })
    return () => controller.abort()
  }, [refreshDashboard])

  useEffect(() => {
    if (view !== "domains" || !signedIn) {
      domainVisitChecked.current = false
      return
    }
    // Let the initial dashboard read finish before the activation command
    // performs its service/DNS updates. This avoids concurrent SQLite writes.
    if (isLoading) return
    if (domainVisitChecked.current) return
    domainVisitChecked.current = true
    void apiRequest<{ checked: boolean }>("/services/domains/check-activation/", { method: "POST" })
      .then((result) => {
        if (result.checked) void refreshDashboard(undefined, { silent: true })
      })
      .catch(() => undefined)
  }, [isLoading, refreshDashboard, signedIn, view])

  useEffect(() => {
    if (view !== "billing" || !signedIn || !returnedBillingPaymentUuid) return
    let cancelled = false
    pollCheckoutPayment(returnedBillingPaymentUuid).then((payment) => {
      if (cancelled) return
      setDepositPayment(payment)
      if (payment.status === "successful") void refreshDashboard(undefined, { silent: true })
      if (["successful", "failed", "cancelled", "expired"].includes(payment.status)) {
        depositCheckoutKey.current = null
        window.sessionStorage.removeItem(depositCheckoutKeyStorage)
      }
    }).catch((cause) => {
      if (!cancelled) setDepositError(cause instanceof Error ? cause.message : "Payment status could not be loaded.")
    })
    const url = new URL(window.location.href)
    url.searchParams.delete("payment")
    window.history.replaceState({}, "", url)
    return () => { cancelled = true }
  }, [refreshDashboard, returnedBillingPaymentUuid, signedIn, view])

  useEffect(() => {
    const paymentUuid = depositPayment?.uuid
    if (view !== "billing" || !paymentUuid || depositPayment?.status !== "processing") return
    const activePaymentUuid = paymentUuid
    let cancelled = false
    let attempts = 0
    let timer: ReturnType<typeof setTimeout>
    async function pollDeposit() {
      if (cancelled || attempts >= 36) return
      attempts += 1
      try {
        const updated = await pollCheckoutPayment(activePaymentUuid)
        if (cancelled) return
        setDepositPayment(updated)
        if (updated.status === "successful") {
          depositCheckoutKey.current = null
          window.sessionStorage.removeItem(depositCheckoutKeyStorage)
          await refreshDashboard(undefined, { silent: true })
          return
        }
        if (["failed", "cancelled", "expired"].includes(updated.status)) {
          depositCheckoutKey.current = null
          window.sessionStorage.removeItem(depositCheckoutKeyStorage)
          return
        }
      } catch {
        // Keep polling while the provider's payment status is temporarily unavailable.
      }
      timer = setTimeout(() => void pollDeposit(), 2500)
    }
    timer = setTimeout(() => void pollDeposit(), 1800)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [depositPayment?.status, depositPayment?.uuid, refreshDashboard, view])

  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(""), 6000)
    return () => window.clearTimeout(timeout)
  }, [notice])

  const services = dashboard?.services ?? emptyServices
  useEffect(() => {
    if (
      view !== "web"
      || !requestedSubdomainDomain
      || requestedSubdomainDomain === focusedSubdomainDomain.current
      || isLoading
    ) return
    const service = services.find((candidate) =>
      candidate.hosting?.primary_domain?.toLowerCase() === requestedSubdomainDomain
      && candidate.is_owner
      && candidate.permissions.can_manage_hosting
      && candidate.status === "active"
      && candidate.hosting.status === "active",
    )
    if (!service?.hosting) return
    if (expandedHostingServiceUuid !== service.uuid) {
      const frame = window.requestAnimationFrame(() => setExpandedHostingServiceUuid(service.uuid))
      return () => window.cancelAnimationFrame(frame)
    }
    const input = document.getElementById(`new-subdomain-${service.hosting.id}`)
    if (!(input instanceof HTMLInputElement)) return
    input.scrollIntoView({ behavior: "smooth", block: "center" })
    input.focus({ preventScroll: true })
    focusedSubdomainDomain.current = requestedSubdomainDomain
    const url = new URL(window.location.href)
    url.searchParams.delete("create_subdomain_for")
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`)
  }, [expandedHostingServiceUuid, isLoading, requestedSubdomainDomain, services, view])
  const domains = useMemo(() => Array.from(
    new Map(services.flatMap((service) => service.domains).map((domain) => [domain.id, domain])).values(),
  ), [services])
  const emailServices = useMemo(
    () => services.filter((service) => (service.hosting || service.service_type === "email-hosting") && service.permissions.can_manage_email),
    [services],
  )
  useEffect(() => {
    const hasPendingMailbox = services.some((service) =>
      service.hosting?.mailboxes.some((mailbox) => ["pending", "clearing", "deleting"].includes(mailbox.status) || Boolean(mailbox.pending_action)),
    )
    const hasPendingWebsite = services.some((service) =>
      service.hosting?.websites.some((website) =>
        website.status === "pending" || website.certificate_status === "pending",
      ),
    )
    if (!((view === "email" && hasPendingMailbox) || (view === "web" && hasPendingWebsite))) return
    const timer = window.setInterval(() => {
      void apiRequest<DashboardPayload>("/services/dashboard/").then(setDashboard).catch(() => undefined)
    }, 8000)
    return () => window.clearInterval(timer)
  }, [services, view])
  const cloudflareConnections = useMemo(
    () => (dashboard?.provider_connections ?? []).filter(
      (connection) => connection.provider === "cloudflare" && connection.status === "active",
    ),
    [dashboard?.provider_connections],
  )
  const domainServices = useMemo(
    () => services.filter(
      (service) => service.status === "active"
        && service.permissions.can_manage_domains
        && service.permissions.can_manage_dns,
    ),
    [services],
  )
  const selectedCloudflareConnectionId = cloudflareConnectionId
    || (cloudflareConnections.length === 1 ? String(cloudflareConnections[0].id) : "")
  const selectedDomainService = externalDomainService
    || (domainServices.length === 1 ? domainServices[0].uuid : "")
  const mailboxes = useMemo(
    () => services.flatMap((service) => service.hosting?.mailboxes ?? []),
    [services],
  )
  const storage = useMemo(
    () => services.flatMap((service) => service.hosting?.resources ?? [])
      .filter((resource) => resource.type === "disk")
      .reduce((total, resource) => {
        const value = Number(resource.limit || 0)
        const unit = resource.unit.toLowerCase()
        if (unit === "tb" || unit === "tib") return total + value * 1024
        if (unit === "mb" || unit === "mib") return total + value / 1024
        if (unit === "bytes" || unit === "b") return total + value / (1024 * 1024 * 1024)
        return total + value
      }, 0),
    [services],
  )

  const upcomingRenewals = useMemo(() => {
    if (currentTime === null) return []
    return [
      ...services
        .filter((service) => service.next_due_at)
        .map((service) => ({
          label: [service.product, service.hosting?.primary_domain].filter(Boolean).join(" · "),
          date: service.next_due_at!,
          type: `${service.billing?.interval === "yearly" ? "Yearly" : "Monthly"} service renewal`,
          href: service.renewal?.href ?? "/dashboard/billing/#billing-payment",
        })),
    ]
      .filter((item) => {
        const remaining = new Date(item.date).getTime() - currentTime
        return Number.isFinite(remaining) && remaining >= 0 && remaining <= 45 * 24 * 60 * 60 * 1000
      })
      .sort((left, right) => left.date.localeCompare(right.date))
  }, [currentTime, domains, services])

  const renewalService = useMemo(
    () => services.find((service) => service.uuid === renewalServiceUuid) ?? null,
    [renewalServiceUuid, services],
  )
  const renewalYearlyOnly = renewalService?.service_type === "domains"
    || renewalService?.billing?.interval === "yearly"
  const renewalDetailsLoading = Boolean(renewalServiceUuid && (isLoading || !renewalService))

  useEffect(() => {
    if (renewalService?.billing?.interval === "yearly" || renewalService?.service_type === "domains") {
      setRenewalBillingInterval("yearly")
    }
    if (view !== "billing" || !renewalServiceUuid || isLoading) return
    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById("billing-payment")
      target?.scrollIntoView({ behavior: "smooth", block: "start" })
      document.getElementById("deposit-amount")?.focus({ preventScroll: true })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [isLoading, renewalService, renewalServiceUuid, view])

  const outstandingInvoices = useMemo(() => invoices.filter(isOpenInvoice), [invoices])
  const outstandingTotal = useMemo(
    () => outstandingInvoices.reduce((total, invoice) => total + amountDue(invoice), 0),
    [outstandingInvoices],
  )
  const visibleInvoices = useMemo(() => {
    if (invoiceFilter === "paid") return invoices.filter((invoice) => invoice.status === "paid")
    if (invoiceFilter === "open") return invoices.filter(isOpenInvoice)
    return invoices
  }, [invoiceFilter, invoices])
  const billingReminders = useMemo(() => [
    ...outstandingInvoices.map((invoice) => ({
      label: invoice.invoice_number,
      detail: invoice.items.map((item) => item.description).join(", ") || "Invoice payment due",
      date: invoice.due_at ?? invoice.created_at,
      type: "Invoice due",
      href: "#billing-invoices",
      action: "Review invoice",
    })),
    ...upcomingRenewals.map((renewal) => ({
      label: renewal.label,
      detail: renewal.type,
      date: renewal.date,
      type: "Service renewal",
      href: renewal.href,
      action: "Renew",
    })),
  ].sort((left, right) => left.date.localeCompare(right.date)), [outstandingInvoices, upcomingRenewals])

  async function openHostingAccess(accountId: number, endpoint: string, destination: string, body: object = {}) {
    const popup = window.open("about:blank", "_blank")
    if (!popup) {
      setFileManagerError({ id: accountId, message: `Allow pop-ups to open ${destination}.` })
      return
    }
    popup.opener = null
    popup.document.title = `Opening ${destination}…`
    setOpeningFiles(accountId)
    setFileManagerError(null)
    try {
      const launch = await apiRequest<{ url: string; ticket: string }>(
        `/services/hosting-accounts/${accountId}/${endpoint}/`,
        { method: "POST", body: JSON.stringify(body) },
      )
      const form = popup.document.createElement("form")
      form.method = "POST"
      form.action = launch.url
      const ticket = popup.document.createElement("input")
      ticket.type = "hidden"
      ticket.name = "ticket"
      ticket.value = launch.ticket
      form.appendChild(ticket)
      popup.document.body.appendChild(form)
      form.submit()
    } catch (cause) {
      popup.close()
      setFileManagerError({ id: accountId, message: cause instanceof Error ? cause.message : `Could not open ${destination}.` })
    } finally {
      setOpeningFiles(null)
    }
  }

  async function openFileManager(accountId: number, websiteDomain: string) {
    return openHostingAccess(accountId, "file-manager", "File Manager", { website_domain: websiteDomain })
  }

  async function openHostingPanel(accountId: number) {
    return openHostingAccess(accountId, "panel-login", "hosting control panel")
  }

  async function submitDeposit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setDepositSubmitting(true)
    setDepositError("")
    setDepositPayment(null)
    if (!depositCheckoutKey.current) {
      depositCheckoutKey.current = crypto.randomUUID()
      window.sessionStorage.setItem(depositCheckoutKeyStorage, depositCheckoutKey.current)
    }
    try {
      const payment = await apiRequest<CheckoutPayment>("/billing/balance/top-up/", {
        method: "POST",
        body: JSON.stringify({
          checkout_key: depositCheckoutKey.current,
          amount: depositAmount,
          payment_method: depositMethod,
          payment_phone: depositPhone,
          ...(renewalServiceUuid ? { service_uuid: renewalServiceUuid, billing_interval: renewalBillingInterval } : {}),
        }),
      })
      setDepositPayment(payment)
      if (payment.status === "successful") {
        depositCheckoutKey.current = null
        window.sessionStorage.removeItem(depositCheckoutKeyStorage)
        await refreshDashboard(undefined, { silent: true })
      } else if (["failed", "cancelled", "expired"].includes(payment.status)) {
        depositCheckoutKey.current = null
        window.sessionStorage.removeItem(depositCheckoutKeyStorage)
      } else if (depositMethod === "card" && payment.redirect_url) {
        window.location.assign(payment.redirect_url)
      }
    } catch (cause) {
      if (cause instanceof ApiError) {
        depositCheckoutKey.current = null
        window.sessionStorage.removeItem(depositCheckoutKeyStorage)
      }
      setDepositError(cause instanceof Error ? cause.message : "Could not start this deposit.")
    } finally {
      setDepositSubmitting(false)
    }
  }

  async function checkDepositStatus() {
    if (!depositPayment?.uuid) return
    setDepositError("")
    try {
      const payment = await pollCheckoutPayment(depositPayment.uuid)
      setDepositPayment(payment)
      if (payment.status === "successful") {
        depositCheckoutKey.current = null
        window.sessionStorage.removeItem(depositCheckoutKeyStorage)
        await refreshDashboard(undefined, { silent: true })
      }
    } catch (cause) {
      setDepositError(cause instanceof Error ? cause.message : "Payment status could not be checked.")
    }
  }

  async function performAction(action: () => Promise<unknown>, message: string): Promise<boolean> {
    setIsWorking(true)
    setError("")
    setNotice("")
    try {
      await action()
      setNotice(message)
      await refreshDashboard(undefined, { silent: true })
      return true
    } catch (cause) {
      setError((cause instanceof Error ? cause.message : "The request could not be completed.").replace(/CyberPanel/gi, "hosting server"))
      return false
    } finally {
      setIsWorking(false)
    }
  }

  async function connectCloudflare(event: React.FormEvent<HTMLFormElement>) {
    setActiveAction("connectCloudflare")
    event.preventDefault()
    await performAction(async () => {
      const connection = await apiRequest<ProviderConnection>("/services/provider-connections/", {
        method: "POST",
        body: JSON.stringify({
          provider: "cloudflare",
          name: "My Cloudflare account",
          credentials: { api_token: cloudflareToken },
        }),
      })
      setCloudflareToken("")
      await apiRequest(`/services/provider-connections/${connection.id}/verify/`, {
        method: "POST",
        body: JSON.stringify({}),
      })
      await loadCloudflareZones()
    }, "Cloudflare connected and verified.")
  }

  async function loadCloudflareZones(interactive = false): Promise<void> {
    if (interactive) {
      setActiveAction("loadCloudflareZones")
      await performAction(() => loadCloudflareZones(), "Cloudflare domains refreshed.")
      return
    }
    const result = await apiRequest<{ zones: CloudflareZoneOption[] }>("/services/cloudflare/zones/")
    setCloudflareZones(result.zones)
    if (!result.zones.length) setNotice("No matching active TechInn domains were found in the connected Cloudflare account.")
  }

  async function loadExternalCloudflareZones() {
    setActiveAction("loadExternalCloudflareZones")
    if (!selectedCloudflareConnectionId) {
      setError("Select a verified Cloudflare connection first.")
      return
    }
    setIsWorking(true)
    setError("")
    try {
      const zones = await apiRequest<CloudflareExternalZone[]>(
        `/services/provider-connections/${selectedCloudflareConnectionId}/zones/`,
      )
      setExternalCloudflareZones(zones)
      setExternalZoneId("")
      if (!zones.length) setNotice("No Cloudflare zones are available in this account.")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Cloudflare domains could not be loaded.")
    } finally {
      setIsWorking(false)
    }
  }

  async function connectExternalDomain() {
    setActiveAction("connectExternalDomain")
    if (!selectedCloudflareConnectionId || !externalZoneId || !selectedDomainService) {
      setError("Choose a verified Cloudflare account, domain and hosting service.")
      return
    }
    await performAction(
      async () => {
        const result = await apiRequest(
          "/services/cloudflare/zones/connect/",
          {
            method: "POST",
            body: JSON.stringify({
              connection_id: Number(selectedCloudflareConnectionId),
              cloudflare_zone_id: externalZoneId,
              service_uuid: selectedDomainService,
            }),
          },
        )
        setExternalCloudflareZones((zones) => zones.filter((zone) => zone.id !== externalZoneId))
        setExternalZoneId("")
        router.push("/dashboard/connections/")
        return result
      },
      "Domain connection started. Continue setup under Connections.",
    )
  }

  async function updatePrimaryDomain(service: DashboardService, domainId: string) {
    setActiveAction(`updatePrimaryDomain:${service.uuid}`)
    if (!service.hosting || !domainId) return
    await performAction(
      () => apiRequest(
        `/services/hosting-accounts/${service.hosting!.id}/primary-domain/`,
        {
          method: "PATCH",
          body: JSON.stringify({ domain_id: Number(domainId) }),
        },
      ),
      "Website domain updated.",
    )
  }

  async function selectServiceDomain(service: DashboardService, domainName: string) {
    setActiveAction(`selectServiceDomain:${service.uuid}`)
    const normalized = domainName.trim().toLowerCase()
    if (!normalized) return
    await performAction(
      () => apiRequest(`/services/${service.uuid}/select-domain/`, {
        method: "POST",
        body: JSON.stringify({ domain_name: normalized }),
      }),
      "Domain assigned. Website setup can begin now; email requires an active domain.",
    )
  }

  async function createSubdomainWebsite(event: React.FormEvent<HTMLFormElement>, service: DashboardService) {
    event.preventDefault()
    const hosting = service.hosting
    if (!hosting?.primary_domain) return
    const subdomain = subdomainByAccount[hosting.id]?.trim()
    if (!subdomain) return
    await requestSubdomainWebsite(hosting.id, subdomain, `${subdomain}.${hosting.primary_domain}`)
  }

  async function requestSubdomainWebsite(accountId: number, subdomain: string, domain: string) {
    setActiveAction(`requestSubdomainWebsite:${accountId}`)
    const completed = await performAction(
      () => apiRequest<DashboardHostedWebsite>(
        `/services/hosting-accounts/${accountId}/websites/`,
        { method: "POST", body: JSON.stringify({ subdomain }) },
      ),
      `Subdomain setup requested for ${domain}. It will appear in the website selector when ready.`,
    )
    if (completed) {
      setSubdomainByAccount((current) => ({ ...current, [accountId]: "" }))
    }
  }

  async function installWebsiteCertificate(accountId: number, website: DashboardHostedWebsite) {
    setActiveAction(`installWebsiteCertificate:${website.id}`)
    await performAction(
      () => apiRequest<DashboardHostedWebsite>(
        `/services/hosting-accounts/${accountId}/websites/${website.id}/certificate/`,
        { method: "POST", body: JSON.stringify({}) },
      ),
      `Certificate installation requested for ${website.domain_name}.`,
    )
  }

  async function installPrimaryCertificate(accountId: number, domain: string) {
    setActiveAction(`installPrimaryCertificate:${accountId}`)
    await performAction(
      () => apiRequest(`/services/hosting-accounts/${accountId}/certificate/`, { method: "POST", body: JSON.stringify({}) }),
      `Certificate installation requested for ${domain}.`,
    )
  }

  async function revokeCloudflare(connectionId: number) {
    setActiveAction(`revokeCloudflare:${connectionId}`)
    await performAction(
      () => apiRequest(`/services/provider-connections/${connectionId}/`, { method: "DELETE" }),
      "Cloudflare connection revoked.",
    )
    setCloudflareZones([])
  }

  async function linkCloudflareZone(zone: CloudflareZoneOption) {
    setActiveAction(`linkCloudflareZone:${zone.connection_id}:${zone.cloudflare_zone_id}`)
    await performAction(
      () => apiRequest("/services/cloudflare/zones/link/", {
        method: "POST",
        body: JSON.stringify({
          domain_id: zone.domain_id,
          connection_id: zone.connection_id,
          cloudflare_zone_id: zone.cloudflare_zone_id,
        }),
      }),
      `${zone.domain} is linked to Cloudflare.`,
    )
    await loadCloudflareZones()
  }

  async function syncDns(zoneId: number) {
    setActiveAction(`syncDns:${zoneId}`)
    await performAction(
      () => apiRequest(`/services/dns-zones/${zoneId}/sync/`, { method: "POST", body: JSON.stringify({}) }),
      "DNS records synchronized from Cloudflare.",
    )
  }

  async function addDnsRecord(event: React.FormEvent<HTMLFormElement>, zone: DashboardDomain["dns"]) {
    setActiveAction(`addDnsRecord:${zone?.id}`)
    event.preventDefault()
    if (!zone) return
    await performAction(
      () => apiRequest("/services/dns-records/", {
        method: "POST",
        body: JSON.stringify({
          zone: zone.id,
          name: dnsName.trim(),
          record_type: dnsType,
          content: dnsContent.trim(),
          ttl: Number(dnsTtl),
          priority: dnsPriority ? Number(dnsPriority) : null,
          proxied: dnsProxied,
        }),
      }),
      "DNS change queued. It will be applied when the DNS worker runs.",
    )
    setDnsContent("")
    setDnsPriority("")
  }

  function beginDnsEdit(record: DNSRecord) {
    setEditingDnsRecord(record.id)
    setDnsName(record.name)
    setDnsType(record.record_type)
    setDnsContent(record.content)
    setDnsTtl(String(record.ttl))
    setDnsPriority(record.priority === null ? "" : String(record.priority))
    setDnsProxied(record.proxied)
  }

  async function saveDnsRecord(record: DNSRecord) {
    setActiveAction(`saveDnsRecord:${record.id}`)
    await performAction(
      () => apiRequest(`/services/dns-records/${record.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          name: dnsName.trim(),
          record_type: dnsType,
          content: dnsContent.trim(),
          ttl: Number(dnsTtl),
          priority: dnsPriority ? Number(dnsPriority) : null,
          proxied: dnsProxied,
        }),
      }),
      "DNS change queued. It will be applied when the DNS worker runs.",
    )
    setEditingDnsRecord(null)
  }

  async function deleteDnsRecord(record: DNSRecord) {
    setActiveAction(`deleteDnsRecord:${record.id}`)
    if (!window.confirm(`Delete the ${record.record_type} record for ${record.name}?`)) return
    await performAction(
      () => apiRequest(`/services/dns-records/${record.id}/`, { method: "DELETE" }),
      "DNS record removal queued.",
    )
  }

  async function createMailbox(
    event: React.FormEvent<HTMLFormElement>,
    service: DashboardService,
    domain: DashboardDomain,
    emailDomain: string,
  ) {
    setActiveAction(`createMailbox:${service.uuid}:${emailDomain}`)
    event.preventDefault()
    if (!service.hosting) return
    const requestedMB = Math.round(Number(mailboxQuota) * (mailboxQuotaUnit === "GB" ? 1024 : 1))
    const availableMB = mailboxStorage(service.hosting).availableMB
    if (availableMB !== null && requestedMB > availableMB) {
      setError(`Only ${availableMB.toLocaleString()} MB of this hosting plan's disk allocation is available for new mailboxes.`)
      return
    }
    const succeeded = await performAction(
      () => apiRequest("/services/mailboxes/", {
        method: "POST",
        body: JSON.stringify({
          hosting_account_id: service.hosting?.id,
          domain_id: domain.id,
          email_domain: emailDomain,
          local_part: mailboxName.trim(),
          quota_mb: requestedMB,
          password: mailboxPassword,
        }),
      }),
      `Mailbox setup queued for ${mailboxName.trim()}@${emailDomain}.`,
    )
    if (succeeded) {
      setMailboxName("")
      setMailboxPassword("")
    }
  }

  async function retryMailboxSetup(event: React.FormEvent<HTMLFormElement>, mailbox: DashboardMailbox) {
    setActiveAction(`retryMailboxSetup:${mailbox.id}`)
    event.preventDefault()
    const succeeded = await performAction(
      () => apiRequest(`/services/mailboxes/${mailbox.id}/retry/`, {
        method: "POST",
        body: JSON.stringify({ password: retryMailboxPassword }),
      }),
      `Mailbox setup retry queued for ${mailbox.email_address}.`,
    )
    if (succeeded) setRetryMailboxPassword("")
  }

  function beginMailboxQuotaEdit(mailbox: DashboardMailbox) {
    setEditingMailboxQuotaId(mailbox.id)
    setEditingMailboxQuota(String(mailbox.quota_mb))
    setEditingMailboxQuotaUnit("MB")
  }

  async function updateMailboxQuota(event: React.FormEvent<HTMLFormElement>, mailbox: DashboardMailbox) {
    setActiveAction(`updateMailboxQuota:${mailbox.id}`)
    event.preventDefault()
    const requestedMB = Math.round(Number(editingMailboxQuota) * (editingMailboxQuotaUnit === "GB" ? 1024 : 1))
    if (requestedMB < mailbox.used_mb) {
      setError(`This mailbox already uses ${mailbox.used_mb.toLocaleString()} MB. Choose at least that much storage.`)
      return
    }
    const succeeded = await performAction(
      () => apiRequest(`/services/mailboxes/${mailbox.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ quota_mb: requestedMB }),
      }),
      `Storage allocation change queued for ${mailbox.email_address}.`,
    )
    if (succeeded) setEditingMailboxQuotaId(null)
  }

  async function clearMailboxStorage(mailbox: DashboardMailbox) {
    setActiveAction(`clearMailboxStorage:${mailbox.id}`)
    if (!window.confirm(`Permanently delete all messages stored in ${mailbox.email_address}? This cannot be undone. The mailbox and its login will remain.`)) return
    await performAction(
      () => apiRequest(`/services/mailboxes/${mailbox.id}/clear-storage/`, {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      }),
      `Mailbox storage clear queued for ${mailbox.email_address}.`,
    )
  }

  async function deleteMailbox(mailbox: DashboardMailbox) {
    setActiveAction(`deleteMailbox:${mailbox.id}`)
    if (!window.confirm(`Permanently remove ${mailbox.email_address} and its mailbox data?`)) return
    await performAction(
      () => apiRequest(`/services/mailboxes/${mailbox.id}/`, { method: "DELETE" }),
      `Mailbox removal queued for ${mailbox.email_address}.`,
    )
  }

  async function grantMailboxAccess(event: React.FormEvent<HTMLFormElement>, serviceId: string) {
    setActiveAction(`grantMailboxAccess:${serviceId}`)
    event.preventDefault()
    if (!selectedMailbox) return
    await performAction(
      () => apiRequest(`/services/mailboxes/${selectedMailbox}/access/`, {
        method: "POST",
        body: JSON.stringify({ email: accessEmail.trim(), role: "user", can_manage: false }),
      }),
      "Mailbox access granted.",
    )
    setAccessEmail("")
  }

  async function updateProfile(event: React.FormEvent<HTMLFormElement>) {
    setActiveAction("updateProfile")
    event.preventDefault()
    setIsWorking(true)
    setError("")
    setNotice("")
    try {
      const updated = await apiRequest<CustomerProfile>("/auth/me/", {
        method: "PATCH",
        body: JSON.stringify(profileValues),
      })
      const session = getApiSession()
      if (session) saveApiSession({ ...session, customer: updated })
      setProfileForm({
        first_name: updated.first_name,
        last_name: updated.last_name,
        phone: updated.phone,
        company_name: updated.company_name,
      })
      setNotice("Your personal and business details have been updated.")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your account details could not be updated.")
    } finally {
      setIsWorking(false)
    }
  }

  async function changePassword(event: React.FormEvent<HTMLFormElement>) {
    setActiveAction("changePassword")
    event.preventDefault()
    if (!accountPasswordOtpRequested) {
      setIsWorking(true)
      setError("")
      setNotice("")
      try {
        await requestPasswordReset(customer?.email ?? "")
        setAccountPasswordOtpRequested(true)
        setNotice("A one-time verification code was sent to your account email.")
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "The verification code could not be sent.")
      } finally {
        setIsWorking(false)
      }
      return
    }
    if (!/^\d{6}$/.test(accountPasswordOtp)) {
      setError("Enter the 6-digit verification code from your email.")
      setNotice("")
      return
    }
    if (newPassword !== confirmPassword) {
      setError("The new password and confirmation do not match.")
      setNotice("")
      return
    }
    setIsWorking(true)
    setError("")
    setNotice("")
    try {
      await confirmPasswordReset({
        email: customer?.email ?? "",
        otp: accountPasswordOtp,
        new_password: newPassword,
      })
      setAccountPasswordOtp("")
      setAccountPasswordOtpRequested(false)
      setNewPassword("")
      setConfirmPassword("")
      setNotice("Your password has been changed. Sign in again with the new password.")
      signOut()
      router.replace("/login/?next=/dashboard/account/")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your password could not be changed.")
    } finally {
      setIsWorking(false)
    }
  }

  if (!signedIn) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col items-start gap-4 px-4 py-12 lg:px-6">
        <h2 className="text-2xl font-semibold">Sign in to your TechInn account</h2>
        <p className="text-muted-foreground">Manage your websites, hosting, domains, business email and account details from one place.</p>
        <Button asChild><a href={signInHref}>Sign in or create an account</a></Button>
      </div>
    )
  }

  return (
    <div className="customer-dashboard flex min-w-0 flex-1 flex-col gap-6 px-2 py-4 sm:px-4 sm:py-6 lg:px-6">
      {passwordResetMailbox && <MailboxPasswordDialog mailbox={passwordResetMailbox} onClose={() => setPasswordResetMailbox(null)} onComplete={() => { setPasswordResetMailbox(null); setNotice("Your mailbox password change is queued. Check its progress in the mailbox list."); void refreshDashboard(undefined, { silent: true }) }} />}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{view === "overview" ? `Welcome${customer?.first_name ? `, ${customer.first_name}` : ""}` : dashboardViewTitles[view] ?? "Customer portal"}</h2>
          {dashboardViewDescriptions[view] && <p className="text-sm text-muted-foreground">{dashboardViewDescriptions[view]}</p>}
        </div>
        <Button variant="outline" disabled={isLoading || view === "account"} loading={isLoading} onClick={() => void refreshDashboard()}>
          <RefreshCw className="size-4" /> Refresh
        </Button>
      </div>

      {error && <DismissibleAlert className="fixed bottom-4 left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 rounded-lg border border-orange-300 bg-orange-50 p-3 text-sm text-orange-900 shadow-lg dark:border-white/80 dark:bg-zinc-950 dark:text-orange-200" id={`dashboard:${view}`} message={error} />}
      {notice && <p role="status" className="fixed bottom-4 left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 rounded-lg border border-orange-400/60 bg-background p-3 text-sm shadow-lg">{notice}</p>}

      {isLoading ? (
        <DashboardLoadingSkeleton view={view} />
      ) : (
        <>
          {view === "overview" && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCard image="/dashboard-cards/hosting.jpg" icon={<Server />} label="Hosting services" value={services.length} />
            <SummaryCard image="/dashboard-cards/domains.jpg" icon={<Globe2 />} label="Domains" value={domains.length} />
            <SummaryCard image="/dashboard-cards/email.jpg" icon={<Mail />} label="Mailboxes" value={mailboxes.length} />
            <SummaryCard image="/dashboard-cards/storage.webp" icon={<Database />} label="Allocated storage" value={`${storage.toLocaleString()} GB`} />
          </div>}

          {view === "overview" && <section className="space-y-4" id="create">
            <SectionHeading title="Quick actions" description="Jump straight to the things you can create and manage." />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <QuickAction href="/shop/?service=web" icon={<Plus />} title="Add hosting" description="Choose a hosting or website plan." />
              <QuickAction href="/dashboard/email/" icon={<Mail />} title="Create an email" description="Set up an address on your domain." />
              <QuickAction href="/dashboard/domains/" icon={<Globe2 />} title="Manage a domain" description="Review domains, nameservers and DNS." />
              <QuickAction href="/domains/" icon={<ArrowUpRight />} title="Find a domain" description="Search for a new domain name." />
            </div>
          </section>}

          {view === "services" && <CustomerServices services={services} />}

          {view === "web" && <section className="space-y-4" id="web">
            <SectionHeading image="/dashboard-icons/hosting.webp" title="Websites & hosting" description="Choose a domain for your website." />
            {services.filter((service) => service.service_type === "web-hosting").length ? services.filter((service) => service.service_type === "web-hosting").map((service) => {
              const isHostingService = service.service_type === "web-hosting"
              const domainOptions = service.domain_options ?? []
              const storageSummary = mailboxStorage(service.hosting)
              const storagePercentage = storageSummary.limitMB
                ? Math.min((storageSummary.committedMB / storageSummary.limitMB) * 100, 100)
                : 0
              const storageOverLimit = storageSummary.limitMB !== null
                && (
                  storageSummary.committedMB > storageSummary.limitMB
                  || storageSummary.actualUsedMB > storageSummary.limitMB
                )
              const hostedWebsites = service.hosting?.primary_domain
                ? [
                    service.hosting.primary_domain,
                    ...service.hosting.websites
                      .filter((website) => website.status === "active")
                      .map((website) => website.domain_name),
                  ]
                : []
              const selectedWebsite = hostedWebsites.includes(
                selectedWebsiteByAccount[service.hosting?.id ?? -1] ?? "",
              )
                ? selectedWebsiteByAccount[service.hosting?.id ?? -1]
                : service.hosting?.primary_domain ?? ""
              const selectedChildWebsite = service.hosting?.websites.find(
                (website) => website.domain_name === selectedWebsite && website.status === "active",
              )
              return <Card key={service.uuid}>
                <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 px-0 py-3 md:px-6 md:py-6">
                  <div className="min-w-0 flex-1">
                    <button
                      aria-controls={`hosting-details-${service.uuid}`}
                      aria-expanded={expandedHostingServiceUuid === service.uuid}
                      className="flex w-full min-w-0 items-center justify-between gap-3 rounded-md text-left"
                      onClick={() => setExpandedHostingServiceUuid((current) => current === service.uuid ? null : service.uuid)}
                      type="button"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-base font-semibold">{service.product}</span>
                        <span className="mt-1 block truncate text-sm text-muted-foreground">
                          {service.hosting?.primary_domain ?? "Hosting service"}{service.next_due_at ? ` · Next due ${formatDate(service.next_due_at)}` : ""}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        <StatusBadge status={service.status} />
                        <ChevronDown className={`size-4 transition-transform ${expandedHostingServiceUuid === service.uuid ? "rotate-180" : ""}`} />
                      </span>
                    </button>
                    <Button
                      aria-controls={`hosting-details-${service.uuid}`}
                      aria-expanded={expandedHostingServiceUuid === service.uuid}
                      className="mt-1 h-6 gap-1 px-1 text-[11px] text-muted-foreground"
                      onClick={() => setExpandedHostingServiceUuid((current) => current === service.uuid ? null : service.uuid)}
                      type="button"
                      variant="ghost"
                    >
                      {expandedHostingServiceUuid === service.uuid ? "Click to hide hosting details" : "Click to view hosting details"}
                      <ChevronDown className={`size-3 transition-transform ${expandedHostingServiceUuid === service.uuid ? "rotate-180" : ""}`} />
                    </Button>
                  </div>
                </CardHeader>
                {isHostingService && !service.hosting && (
                  <CardContent className="space-y-3 pt-0">
                    <div className="rounded-lg border border-orange-300 bg-orange-50/60 p-4 text-sm dark:border-orange-900 dark:bg-orange-950/20">
                      <p className="font-medium">Choose the domain for this website</p>
                      <p className="mt-1 text-muted-foreground">Your hosting is paid. Choose a purchased or connected domain to start preparing your website, even while registration is processing.</p>
                      <div className="mt-3 flex gap-2">
                        <select aria-label={`Domain for ${service.product}`} className="h-10 min-w-0 flex-1 rounded-md border border-orange-400 bg-background px-3 text-sm" disabled={!service.permissions.can_manage_hosting || isWorking} onChange={(event) => void selectServiceDomain(service, event.target.value)} value={domainOptions.find((domain) => domain.selected)?.name ?? ""}>
                          <option value="">Select a domain</option>
                          {domainOptions.map((domain) => <option key={domain.id} value={domain.name}>{domain.name}{domain.status !== "active" ? ` · ${domain.status}` : ""}</option>)}
                        </select>
                      </div>
                      {!domainOptions.some((domain) => domain.status === "active") && <p className="mt-2 text-xs text-muted-foreground">You can select a processing domain now. Hosting will be ready when registration or connection completes.</p>}
                    </div>
                  </CardContent>
                )}
                {service.hosting && expandedHostingServiceUuid === service.uuid && (
                  <CardContent className="space-y-4" id={`hosting-details-${service.uuid}`}>
                    <div className="max-w-xl space-y-2">
                      <label className="flex items-center gap-2 text-sm font-medium" htmlFor={`primary-domain-${service.uuid}`}>
                        <Globe2 className="size-4 text-orange-600 dark:text-orange-400" /> Website domain
                      </label>
                      {service.hosting.primary_domain && service.hosting.domain_status !== "active" ? (
                        <div className="space-y-2 rounded-lg border border-orange-300 bg-orange-50/70 p-3 text-sm dark:border-orange-800 dark:bg-orange-950/25">
                          <p className="break-all font-medium">{service.hosting.primary_domain} · Processing</p>
                          <p className="text-xs text-muted-foreground">Your website space is ready. Upload files and use Preview website while domain registration finishes. Email will be available after the domain is active.</p>
                        </div>
                      ) : service.domains.some((domain) => domain.status === "active" && domain.permissions.can_manage_domains) ? (
                        <select
                          aria-label={`Website domain for ${service.product}`}
                          className="h-10 w-full rounded-md border border-black bg-orange-50/70 px-3 text-sm shadow-sm focus-visible:border-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/30 dark:border-white dark:bg-orange-950/25 dark:focus-visible:border-white"
                          disabled={!service.permissions.can_manage_hosting || isWorking}
                          id={`primary-domain-${service.uuid}`}
                          onChange={(event) => void updatePrimaryDomain(service, event.target.value)}
                          value={service.domains.find((domain) => domain.name === service.hosting?.primary_domain)?.id.toString() ?? ""}
                        >
                          <option value="">Select a connected domain</option>
                          {service.domains.filter((domain) => domain.status === "active" && domain.permissions.can_manage_domains).map((domain) => (
                            <option key={domain.id} value={domain.id}>{domain.name}</option>
                          ))}
                        </select>
                      ) : (
                        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-orange-300 bg-orange-50/70 p-3 text-sm dark:border-orange-800 dark:bg-orange-950/25">
                          <Globe2 className="size-4 text-orange-600 dark:text-orange-400" />
                          <span className="text-muted-foreground">No domain connected.</span>
                          <Button asChild className="h-auto px-1 text-orange-700 dark:text-orange-300" size="sm" variant="link"><Link href="/dashboard/domains/">Connect domain <ArrowUpRight className="size-3.5" /></Link></Button>
                        </div>
                      )}
                      {!service.permissions.can_manage_hosting && <p className="text-xs text-muted-foreground">Ask the service owner to change the website domain.</p>}
                    </div>
                    {service.hosting.primary_domain && (
                      <div className="grid gap-4 lg:grid-cols-2">
                        <div className="space-y-3 rounded-lg border p-4">
                          <div>
                            <p className="text-sm font-medium">Website files</p>
                            <p className="text-xs text-muted-foreground">Choose which website to manage or open.</p>
                          </div>
                          <label className="grid gap-1.5 text-sm font-medium" htmlFor={`file-manager-website-${service.hosting.id}`}>
                            Website
                          <select
                            className="h-10 w-full rounded-md border border-black bg-orange-50/70 px-3 text-sm shadow-sm focus-visible:border-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/30 dark:border-white dark:bg-orange-950/25 dark:focus-visible:border-white"
                            disabled={!service.is_owner || !service.permissions.can_manage_hosting || isWorking}
                            id={`file-manager-website-${service.hosting.id}`}
                            onChange={(event) => setSelectedWebsiteByAccount((current) => ({
                              ...current,
                              [service.hosting!.id]: event.target.value,
                            }))}
                            value={selectedWebsite}
                          >
                            {hostedWebsites.map((website) => <option key={website} value={website}>{website}</option>)}
                          </select>
                          </label>
                        </div>
                        {service.permissions.can_manage_hosting && ["active", "provisioning"].includes(service.status) && service.hosting.status === "active" && (
                          <form className="space-y-3 rounded-lg border p-4" onSubmit={(event) => void createSubdomainWebsite(event, service)}>
                            <div>
                              <p className="text-sm font-medium">Add a subdomain website</p>
                              <p className="text-xs text-muted-foreground">Create a separate website under {service.hosting.primary_domain}.</p>
                            </div>
                            <label className="grid gap-1.5 text-sm font-medium" htmlFor={`new-subdomain-${service.hosting.id}`}>
                              Subdomain
                              <span className="flex h-10 min-w-0 overflow-hidden rounded-md border border-orange-300 bg-background focus-within:border-orange-500 focus-within:ring-2 focus-within:ring-orange-500/20 dark:border-orange-800">
                                <Input
                                  aria-label="Subdomain name"
                                  autoComplete="off"
                                  className="h-full min-w-0 flex-1 rounded-none border-0 px-3 focus-visible:ring-0"
                                  id={`new-subdomain-${service.hosting.id}`}
                                  onChange={(event) => setSubdomainByAccount((current) => ({
                                    ...current,
                                    [service.hosting!.id]: event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""),
                                  }))}
                                  pattern="[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                                  placeholder="e.g. blog"
                                  required
                                  title="Enter one subdomain label, such as blog"
                                  value={subdomainByAccount[service.hosting.id] ?? ""}
                                />
                                <span className="flex shrink-0 items-center border-l border-orange-300 bg-orange-50/70 px-2.5 text-xs font-normal text-muted-foreground dark:border-orange-800 dark:bg-orange-950/25">
                                  .{service.hosting.primary_domain}
                                </span>
                              </span>
                            </label>
                            <div className="flex flex-wrap items-center gap-3">
                              <Button className="h-9 bg-orange-600 bg-none text-white hover:bg-orange-700 dark:text-white" disabled={isWorking} loading={workingOn(`requestSubdomainWebsite:${service.hosting!.id}`)} type="submit">
                                <Plus className="size-4" />Create website
                              </Button>
                              <p className="text-xs text-muted-foreground">Point its DNS to your hosting server before installing a certificate.</p>
                            </div>
                          </form>
                        )}
                      </div>
                    )}
                    {service.is_owner && service.permissions.can_manage_hosting && service.hosting.primary_domain && ["active", "provisioning"].includes(service.status) && service.hosting.status === "active" && (
                      <div className="flex flex-wrap items-center gap-2">
                        <Button className="bg-orange-600 bg-none text-white hover:bg-orange-700 dark:text-white" disabled={openingFiles !== null} loading={openingFiles === service.hosting.id} onClick={() => void openFileManager(service.hosting!.id, selectedWebsite)} type="button"><ExternalLink className="size-4" />Open File Manager</Button>
                        <Button
                          disabled={isWorking || service.hosting.certificate_status === "pending"}
                          loading={workingOn(`installPrimaryCertificate:${service.hosting!.id}`)}
                          onClick={() => void installPrimaryCertificate(service.hosting!.id, service.hosting!.primary_domain!)}
                          type="button"
                          variant="outline"
                        >
                          <ShieldCheck className="size-4" />
                          {service.hosting.certificate_status === "active" ? "Renew domain certificate" : service.hosting.certificate_status === "pending" ? "Installing certificate" : "Install domain certificate"}
                        </Button>
                        {selectedChildWebsite && (
                          <Button
                            disabled={isWorking || selectedChildWebsite.certificate_status === "pending"}
                            loading={workingOn(`installWebsiteCertificate:${selectedChildWebsite.id}`)}
                            onClick={() => void installWebsiteCertificate(service.hosting!.id, selectedChildWebsite)}
                            type="button"
                            variant="outline"
                          >
                            <ShieldCheck className="size-4" />
                            {selectedChildWebsite.certificate_status === "active" ? "Renew certificate" : selectedChildWebsite.certificate_status === "pending" ? "Installing certificate" : "Install certificate"}
                          </Button>
                        )}
                        {fileManagerError?.id === service.hosting.id && <DismissibleAlert className="text-sm text-destructive" id={`file-manager:${service.hosting.id}`} message={fileManagerError.message} />}
                        {selectedChildWebsite?.certificate_status === "error" && (
                          <DismissibleAlert
                            className="w-full text-sm text-destructive"
                            id={`certificate:${selectedChildWebsite.id}`}
                            message={selectedChildWebsite.certificate_error.replace(/CyberPanel/gi, "hosting server") || "Certificate installation failed. Confirm DNS points to this server and retry."}
                          />
                        )}
                        {service.hosting.certificate_status === "error" && (
                          <DismissibleAlert
                            className="w-full text-sm text-destructive"
                            id={`primary-certificate:${service.hosting.id}`}
                            message={service.hosting.certificate_error?.replace(/CyberPanel/gi, "hosting server") || "Certificate installation failed. Confirm DNS points to this server and retry."}
                          />
                        )}
                      </div>
                    )}
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {service.hosting.resources.filter((resource) => resource.type !== "disk" && resource.type !== "email_accounts").map((resource) => (
                      <div className="rounded-lg border p-3" key={resource.type}>
                        <p className="text-xs capitalize text-muted-foreground">{resource.type.replaceAll("_", " ")}</p>
                        <p className="mt-1 font-medium">
                          {formatResource(resource.used, resource.unit)} used of {formatResource(resource.limit, resource.unit)}
                        </p>
                      </div>
                    ))}
                    </div>
                  </CardContent>
                )}
                {service.hosting && service.hosting.websites.filter((website) => website.status !== "active").map((website) => (
                  website.status === "error" ? <DismissibleAlert
                    className="mx-3 mb-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive md:mx-6"
                    id={`website-setup:${website.id}`}
                    key={website.id}
                    message={`${website.domain_name}: ${website.last_error}`}
                  >
                    <div>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="font-medium">{website.domain_name} · Setup failed</p>
                        {service.is_owner && service.permissions.can_manage_hosting && (
                          <Button
                            className="h-8"
                            disabled={isWorking}
                            onClick={() => {
                              const parent = service.hosting?.primary_domain
                              const suffix = parent ? `.${parent}` : ""
                              if (service.hosting && suffix && website.domain_name.endsWith(suffix)) {
                                const label = website.domain_name.slice(0, -suffix.length)
                                void requestSubdomainWebsite(service.hosting.id, label, website.domain_name)
                              }
                            }}
                            size="sm"
                            type="button"
                            variant="outline"
                          >
                            Retry setup
                          </Button>
                        )}
                      </div>
                      <p className="mt-1 text-xs">{website.last_error.replace(/CyberPanel/gi, "hosting server") || "The website could not be created. Check your plan and try again."}</p>
                    </div>
                  </DismissibleAlert> : <div
                    className="mx-3 mb-3 rounded-md border border-orange-300 bg-orange-50/60 p-3 text-sm md:mx-6 dark:border-orange-900 dark:bg-orange-950/20"
                    key={website.id}
                    role="status"
                  >
                    <p className="font-medium">{website.domain_name} · Setting up</p>
                  </div>
                ))}
                {service.hosting && (
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t px-3 py-2.5 text-xs md:px-6">
                    {service.hosting.preview_url && service.hosting.domain_status !== "active" && (
                      <a className="inline-flex items-center gap-1.5 text-orange-700 underline dark:text-orange-300" href={service.hosting.preview_url} target="_blank" rel="noreferrer">Preview website<ExternalLink className="size-3" /></a>
                    )}
                    {service.hosting.primary_domain && service.hosting.domain_status === "active" && (
                      <a
                        className="inline-flex items-center gap-1.5 text-emerald-700 underline-offset-4 hover:underline dark:text-emerald-300"
                        href={`https://${service.hosting.primary_domain}`}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <Globe2 className="size-3.5" />Open live website<ExternalLink className="size-3" />
                      </a>
                    )}
                    {service.hosting.resources.filter((resource) => resource.type === "email_accounts").map((resource) => (
                      <Link
                        className="inline-flex items-center gap-1.5 text-blue-700 underline-offset-4 hover:underline dark:text-blue-300"
                        href="/dashboard/email/"
                        key={resource.type}
                      >
                        <Mail className="size-3.5" />
                        {Number.isFinite(Number(resource.used)) ? Number(resource.used).toLocaleString() : resource.used} mailboxes used of {Number.isFinite(Number(resource.limit)) ? Number(resource.limit).toLocaleString() : resource.limit} mailboxes
                      </Link>
                    ))}
                    {service.hosting.username && service.is_owner && service.permissions.can_manage_hosting && ["active", "provisioning"].includes(service.status) && service.hosting.status === "active" && (
                      <button
                        className="inline-flex items-center gap-1.5 text-violet-700 underline-offset-4 hover:underline dark:text-violet-300"
                        onClick={() => void openHostingPanel(service.hosting!.id)}
                        type="button"
                      >
                        <UserRound className="size-3.5" />Hosting login · {service.hosting.username}
                      </button>
                    )}
                  </div>
                )}
                {service.hosting && storageSummary.limitMB !== null && (
                  <div className="border-t px-3 py-2.5 md:px-6">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
                      <Database className={`size-4 shrink-0 ${storageOverLimit ? "text-destructive" : "text-orange-600 dark:text-orange-400"}`} />
                      <span className="font-medium">Storage</span>
                      <span className={storageOverLimit ? "font-medium text-destructive" : "text-muted-foreground"}>
                        {formatStorageMB(storageSummary.actualUsedMB)} used of {formatStorageMB(storageSummary.limitMB)} · {formatStorageMB(storageSummary.availableMB ?? 0)} unallocated · {formatStorageMB(storageSummary.allocatedMB)} reserved for email
                      </span>
                      <div
                        aria-label={`Committed shared storage ${Math.round(storagePercentage)} percent`}
                        className="h-1.5 min-w-16 flex-1 overflow-hidden rounded-full bg-muted"
                        role="meter"
                        aria-valuemax={100}
                        aria-valuemin={0}
                        aria-valuenow={Math.round(storagePercentage)}
                      >
                        <div
                          className={`h-full transition-[width] ${storageOverLimit ? "bg-red-600" : storagePercentage >= 80 ? "bg-amber-500" : "bg-emerald-500"}`}
                          style={{ width: `${storagePercentage}%` }}
                        />
                      </div>
                      {["active", "provisioning"].includes(service.status) && service.hosting.status === "active" && service.is_owner && service.permissions.can_manage_hosting && service.product_slug.startsWith("web-") && service.hosting.primary_domain && (
                        <div className="flex shrink-0 items-center gap-2">
                          <label className="sr-only" htmlFor={`storage-interval-${service.uuid}`}>Storage extension billing interval</label>
                          <select
                            className="h-8 rounded-md border bg-background px-2 text-xs"
                            id={`storage-interval-${service.uuid}`}
                            onChange={(event) => setStorageBillingIntervalByService((current) => ({
                              ...current,
                              [service.uuid]: event.target.value as "monthly" | "yearly",
                            }))}
                            value={storageBillingIntervalByService[service.uuid] ?? "monthly"}
                          >
                            <option value="monthly">+5 GB · $2 / month</option>
                            <option value="yearly">+5 GB · $21.60 / year · save 10%</option>
                          </select>
                          <Button
                            className="h-8 px-2.5"
                            onClick={() => {
                              const yearly = storageBillingIntervalByService[service.uuid] === "yearly"
                              addStorageAddonToCart(service.uuid, service.hosting!.primary_domain!, yearly)
                              router.push("/checkout/")
                            }}
                            size="sm"
                            type="button"
                            variant="outline"
                          >
                            <ShoppingCart className="size-3.5" /> Checkout
                          </Button>
                        </div>
                      )}
                    </div>
                    {storageOverLimit && (
                      <DismissibleAlert className="mt-1 text-xs font-medium text-destructive" id={`storage-over-limit:${service.uuid}`} message="Current files and mailbox allocations exceed this service’s storage limit." />
                    )}
                  </div>
                )}
              </Card>
            }) : (
              <EmptyCard message="There are no services on this account yet." href="/shop/" action="Browse services" />
            )}
          </section>}

          {view === "analytics" && <section className="space-y-4" id="analytics">
            <SectionHeading title="Analytics & performance" description="See available hosting usage and understand what still needs to be connected." />
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base"><Database className="size-4 text-amber-600 dark:text-amber-400" />Hosting resource usage</CardTitle>
                  <CardDescription>Latest resource totals reported by your hosting service.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 px-0 pb-4 md:px-6 md:pb-6">
                  {services.flatMap((service) => service.hosting?.resources.map((resource) => ({
                    ...resource,
                    key: `${service.uuid}-${resource.type}`,
                    serviceName: service.hosting?.primary_domain ?? service.product,
                  })) ?? []).map((resource) => {
                    const used = Number(resource.used)
                    const limit = Number(resource.limit)
                    const percentage = Number.isFinite(used) && Number.isFinite(limit) && limit > 0
                      ? Math.min(Math.max((used / limit) * 100, 0), 100)
                      : 0
                    return (
                      <div className="space-y-1.5" key={resource.key}>
                        <div className="flex justify-between gap-2 text-sm">
                          <span className="capitalize">{resource.serviceName} · {resource.type.replaceAll("_", " ")}</span>
                          <span className="text-muted-foreground">{formatResource(resource.used, resource.unit)} / {formatResource(resource.limit, resource.unit)}</span>
                        </div>
                        <div aria-label={`${resource.type} usage ${Math.round(percentage)} percent`} className="h-2 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-amber-500" style={{ width: `${percentage}%` }} />
                        </div>
                      </div>
                    )
                  })}
                  {!services.some((service) => service.hosting?.resources.length) && (
                    <p className="text-sm text-muted-foreground">Usage will appear when your hosting account reports resource limits.</p>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base"><Activity className="size-4 text-amber-600 dark:text-amber-400" />Website traffic</CardTitle>
                  <CardDescription>Visits, page views and uptime monitoring.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Traffic analytics are not connected to this account yet. No visitor counts are shown until a real analytics source is configured.
                  </p>
                  <Button asChild size="sm" variant="outline"><Link href="/how-to/">Explore setup guides <ArrowUpRight className="size-4" /></Link></Button>
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Provisioning error log</CardTitle>
                <CardDescription>Download a plain-text log of failed service requests. It includes error details, not request payloads or credentials.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  {provisioningActions.filter((action) => action.status === "failed" && action.error_message).length
                    ? `${provisioningActions.filter((action) => action.status === "failed" && action.error_message).length} failed request(s) are available.`
                    : "No failed provisioning requests have been recorded."}
                </p>
                <Button
                  onClick={() => {
                    const failedActions = provisioningActions.filter((action) => action.status === "failed" && action.error_message)
                    const lines = failedActions.map((action) => [
                      `Request #${action.id}`,
                      `Type: ${action.action_type.replaceAll("_", " ")}`,
                      `Scheduled: ${action.scheduled_at}`,
                      `Completed: ${action.completed_at ?? "not completed"}`,
                      `Error: ${(action.error_message ?? "").replace(/\s+/g, " ").trim()}`,
                      "",
                    ].join("\n"))
                    const log = new Blob(
                      [lines.length ? lines.join("\n") : "No failed provisioning requests have been recorded.\n"],
                      { type: "text/plain;charset=utf-8" },
                    )
                    const url = URL.createObjectURL(log)
                    const link = document.createElement("a")
                    link.href = url
                    link.download = `techinn-provisioning-errors-${new Date().toISOString().slice(0, 10)}.txt`
                    link.click()
                    window.setTimeout(() => URL.revokeObjectURL(url), 0)
                  }}
                  size="sm"
                  type="button"
                  variant="outline"
                >
                  Download .txt log
                </Button>
              </CardContent>
            </Card>
          </section>}

          {view === "domains" && <section className="min-w-0 space-y-4" id="domains">
            <SectionHeading image="/dashboard-icons/domain.webp" helpHref="/how-to/dashboard-domain-email/" title="Domains & DNS" />
            <DomainSearchPanel compact />
            <Card className="overflow-hidden border-orange-200 dark:border-orange-900">
              <CardHeader className="flex flex-row items-center gap-3 border-b border-orange-100 bg-orange-50/60 py-3 dark:border-orange-950 dark:bg-orange-950/20">
                <span className="rounded-lg bg-orange-500/15 p-2 text-orange-700 dark:text-orange-300"><Cloud className="size-5" /></span>
                <div>
                  <CardTitle className="text-base">Connect an existing domain</CardTitle>
                  <CardDescription><Link href="/dashboard/connections/" className="text-orange-700 underline dark:text-orange-300">Use TechInn DNS, keep your DNS, or connect Cloudflare</Link></CardDescription>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 p-4">
                {!cloudflareConnections.length ? (
                  <form className="grid gap-2 sm:grid-cols-[1fr_auto]" onSubmit={(event) => void connectCloudflare(event)}>
                    <Input
                      aria-label="Cloudflare API token"
                      autoComplete="off"
                      className="h-10 border-black bg-orange-50/70 focus-visible:border-black focus-visible:ring-orange-500/30 dark:border-white dark:bg-orange-950/25 dark:focus-visible:border-white"
                      onChange={(event) => setCloudflareToken(event.target.value)}
                      placeholder="Paste Cloudflare API token"
                      required
                      type="password"
                      value={cloudflareToken}
                    />
                    <Button className="h-10" disabled={isWorking} loading={workingOn("connectCloudflare")} type="submit">
                      <Cloud className="size-4" /> Connect Cloudflare
                    </Button>
                  </form>
                ) : (
                  <>
                    <div className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
                      <label className="grid gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        <span className="flex items-center gap-1.5"><Cloud className="size-3.5 text-orange-600" /> Account</span>
                        <select
                          className="h-10 rounded-md border border-black bg-orange-50/70 px-3 text-sm font-normal normal-case tracking-normal text-foreground shadow-sm focus-visible:border-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/30 dark:border-white dark:bg-orange-950/25 dark:focus-visible:border-white"
                          onChange={(event) => {
                            setCloudflareConnectionId(event.target.value)
                            setExternalCloudflareZones([])
                            setExternalZoneId("")
                          }}
                          value={selectedCloudflareConnectionId}
                        >
                          <option value="">Choose account</option>
                          {cloudflareConnections.map((connection) => <option key={connection.id} value={connection.id}>{connection.name}</option>)}
                        </select>
                      </label>
                      <label className="grid gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        <span className="flex items-center gap-1.5"><Server className="size-3.5 text-orange-600" /> Service</span>
                        <select
                          className="h-10 rounded-md border border-black bg-orange-50/70 px-3 text-sm font-normal normal-case tracking-normal text-foreground shadow-sm focus-visible:border-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/30 dark:border-white dark:bg-orange-950/25 dark:focus-visible:border-white"
                          onChange={(event) => setExternalDomainService(event.target.value)}
                          value={selectedDomainService}
                        >
                          <option value="">Choose service</option>
                          {domainServices.map((service) => (
                            <option key={service.uuid} value={service.uuid}>{service.product}</option>
                          ))}
                        </select>
                      </label>
                      <Button className="h-10" disabled={isWorking || !selectedCloudflareConnectionId} loading={workingOn("loadExternalCloudflareZones")} onClick={() => void loadExternalCloudflareZones()} type="button">
                        <RefreshCw className="size-4" /> Find domains
                      </Button>
                    </div>
                    {externalCloudflareZones.length > 0 && (
                      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                        <label className="grid gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          <span className="flex items-center gap-1.5"><Globe2 className="size-3.5 text-orange-600" /> Domain</span>
                          <select
                            className="h-10 rounded-md border border-black bg-orange-50/70 px-3 text-sm font-normal normal-case tracking-normal text-foreground shadow-sm focus-visible:border-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500/30 dark:border-white dark:bg-orange-950/25 dark:focus-visible:border-white"
                            onChange={(event) => setExternalZoneId(event.target.value)}
                            value={externalZoneId}
                          >
                            <option value="">Choose domain</option>
                            {externalCloudflareZones.map((zone) => <option key={zone.id} value={zone.id}>{zone.name}</option>)}
                          </select>
                        </label>
                        <Button className="h-10 sm:self-end" disabled={isWorking || !externalZoneId || !selectedDomainService} loading={workingOn("connectExternalDomain")} onClick={() => void connectExternalDomain()} type="button">
                          <Plus className="size-4" /> Connect domain
                        </Button>
                      </div>
                    )}
                    {!domainServices.length && (
                      <Button asChild className="text-orange-700 dark:text-orange-300" size="sm" variant="outline"><Link href="/shop/">Add a service <ArrowUpRight className="size-4" /></Link></Button>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
            <div className="space-y-4" id="domain-list">
            {domains.length ? domains.map((domain) => (
              <Card className="border-0 shadow-none md:border md:shadow-sm" key={domain.id}>
                <CardHeader className="p-0">
                  <button
                    aria-expanded={expandedDomainId === domain.id}
                    className="flex w-full min-w-0 items-center justify-between gap-3 rounded-lg p-3 text-left transition-colors hover:bg-muted/40 md:p-4"
                    onClick={() => setExpandedDomainId((current) => current === domain.id ? null : domain.id)}
                    type="button"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <Globe2 className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{domain.name}</span>
                        <span className="mt-1 block truncate text-xs text-muted-foreground">
                          Expires {formatDate(domain.expires_at)} · {domain.dns ? `${domain.dns.records.length} DNS records` : "DNS not connected"}
                        </span>
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <StatusBadge status={domain.status} />
                      <ChevronDown className={`size-4 transition-transform ${expandedDomainId === domain.id ? "rotate-180" : ""}`} />
                    </span>
                  </button>
                </CardHeader>
                {expandedDomainId === domain.id && <CardContent className="space-y-4 pt-3">
                  {domain.registration && domain.status !== "active" && (
                    <div className="rounded-md border border-orange-500/20 bg-orange-500/5 p-3" role="status">
                      <p className="text-sm font-medium text-orange-700 dark:text-orange-300">{domain.registration.label}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{domain.registration.message}</p>
                    </div>
                  )}
                  <div className="overflow-hidden border-y bg-card md:rounded-xl md:border">
                    <div className="flex items-center justify-between px-0 py-3 md:border-b md:bg-muted/30 md:px-4">
                      <div>
                        <p className="text-sm font-semibold">Nameservers</p>
                        <p className="text-xs text-muted-foreground">Nameservers assigned for this domain</p>
                      </div>
                      <span className="text-xs text-muted-foreground">{domain.nameservers.length} active</span>
                    </div>
                    <Button className="mb-2 h-8 md:hidden" onClick={() => setMobileTablesOpen((state) => ({ ...state, [`ns-${domain.id}`]: !state[`ns-${domain.id}`] }))} size="sm" variant="outline">
                      {mobileTablesOpen[`ns-${domain.id}`] ? "Hide nameservers" : "Show nameservers"}<ChevronDown className={`ml-1 size-4 transition-transform ${mobileTablesOpen[`ns-${domain.id}`] ? "rotate-180" : ""}`} />
                    </Button>
                    <div className={`overflow-x-auto ${mobileTablesOpen[`ns-${domain.id}`] ? "block" : "hidden md:block"}`}>
                    <Table className="min-w-[480px]">
                      <TableHeader className="bg-muted/20">
                        <TableRow>
                          <TableHead>Nameserver</TableHead>
                          <TableHead className="text-right">Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {domain.nameservers.map((nameserver) => (
                          <TableRow key={nameserver}>
                            <TableCell className="font-mono text-xs sm:text-sm">{nameserver}</TableCell>
                            <TableCell className="text-right"><Badge variant="secondary">Assigned</Badge></TableCell>
                          </TableRow>
                        ))}
                        {!domain.nameservers.length && <TableRow><TableCell className="text-muted-foreground" colSpan={2}>Nameservers have not been set.</TableCell></TableRow>}
                      </TableBody>
                    </Table>
                    </div>
                  </div>
                  {domain.dns ? (
                    <>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2 text-sm">
                          <span className="flex items-center gap-2">
                            <Image alt="" className="size-6 rounded bg-white object-contain" height={24} src="/dashboard-icons/dns.jpg" width={24} />
                            DNS zone
                          </span><StatusBadge status={domain.dns.status} />
                          {domain.dns.dnssec_enabled && <Badge variant="outline">DNSSEC enabled</Badge>}
                        </div>
                        {domain.permissions.can_manage_dns && (
                          <Button disabled={isWorking} loading={workingOn(`syncDns:${domain.dns!.id}`)} size="sm" variant="outline" onClick={() => void syncDns(domain.dns!.id)}>
                            <RefreshCw className="size-4" /> Sync DNS
                          </Button>
                        )}
                      </div>
                      <div className="overflow-hidden border-y bg-card md:rounded-xl md:border">
                        <div className="flex flex-wrap items-center justify-between gap-3 py-3 md:border-b md:bg-muted/30 md:px-4">
                          <div>
                            <p className="text-sm font-semibold">DNS records</p>
                            <p className="text-xs text-muted-foreground">A, AAAA, CNAME, MX, TXT, NS, SRV and CAA records</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <div className="relative w-full sm:w-56"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input aria-label={`Search ${domain.name} DNS records`} className="h-9 pl-9" onChange={(event) => setDnsSearch(event.target.value)} placeholder="Filter records" value={dnsSearch} /></div>
                            <span className="text-xs text-muted-foreground">{domain.dns.records.length} records</span>
                          </div>
                        </div>
                        <Button className="mb-2 h-8 md:hidden" onClick={() => setMobileTablesOpen((state) => ({ ...state, [`dns-${domain.id}`]: !state[`dns-${domain.id}`] }))} size="sm" variant="outline">
                          {mobileTablesOpen[`dns-${domain.id}`] ? "Hide DNS records" : "Show DNS records"}<ChevronDown className={`ml-1 size-4 transition-transform ${mobileTablesOpen[`dns-${domain.id}`] ? "rotate-180" : ""}`} />
                        </Button>
                        <div className={`overflow-x-auto ${mobileTablesOpen[`dns-${domain.id}`] ? "block" : "hidden md:block"}`}>
                        <Table className="min-w-[960px]">
                          <TableHeader className="bg-muted/20">
                            <TableRow>
                              <TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead>Content</TableHead>
                              <TableHead>TTL</TableHead><TableHead>Proxy / Sync</TableHead>
                              {domain.permissions.can_manage_dns && <TableHead className="text-right">Actions</TableHead>}
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {domain.dns.records.filter((record) => `${record.name} ${record.record_type} ${record.content}`.toLowerCase().includes(dnsSearch.toLowerCase())).map((record) => editingDnsRecord === record.id ? (
                              <TableRow key={record.id} className="bg-orange-500/5 align-top">
                                <TableCell><Input aria-label="Edit DNS record name" className="min-w-32" onChange={(event) => setDnsName(event.target.value)} value={dnsName} /></TableCell>
                                <TableCell>
                                  <select aria-label="Edit DNS record type" className="h-9 rounded-md border bg-background px-2 text-sm" onChange={(event) => setDnsType(event.target.value)} value={dnsType}>
                                    {["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA"].map((type) => <option key={type} value={type}>{type}</option>)}
                                  </select>
                                </TableCell>
                                <TableCell><Input aria-label="Edit DNS record content" className="min-w-48" onChange={(event) => setDnsContent(event.target.value)} value={dnsContent} /></TableCell>
                                <TableCell><Input aria-label="Edit DNS record TTL" className="w-24" min={1} onChange={(event) => setDnsTtl(event.target.value)} type="number" value={dnsTtl} /></TableCell>
                                <TableCell className="space-y-2">
                                  {(dnsType === "MX" || dnsType === "SRV") && <Input aria-label="DNS priority" className="w-24" min={0} onChange={(event) => setDnsPriority(event.target.value)} placeholder="Priority" type="number" value={dnsPriority} />}
                                  {["A", "AAAA", "CNAME"].includes(dnsType) && <label className="flex items-center gap-2 text-xs"><input checked={dnsProxied} onChange={(event) => setDnsProxied(event.target.checked)} type="checkbox" /> Proxied</label>}
                                </TableCell>
                                <TableCell className="text-right">
                                  <div className="flex justify-end gap-1">
                                    <Button aria-label="Save DNS record" disabled={isWorking} loading={workingOn(`saveDnsRecord:${record.id}`)} onClick={() => void saveDnsRecord(record)} size="icon" variant="ghost"><Save className="size-4" /></Button>
                                    <Button aria-label="Cancel DNS edit" disabled={isWorking} onClick={() => setEditingDnsRecord(null)} size="icon" variant="ghost"><X className="size-4" /></Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ) : (
                              <TableRow key={record.id}>
                                <TableCell className="max-w-48 truncate font-medium" title={record.name}>{record.name}</TableCell>
                                <TableCell><Badge variant="outline">{record.record_type}</Badge></TableCell>
                                <TableCell className="max-w-72 truncate font-mono text-xs" title={record.content}>{record.content}</TableCell>
                                <TableCell>{record.ttl === 1 ? "Auto" : `${record.ttl}s`}</TableCell>
                                <TableCell><div className="flex items-center gap-2">{record.proxied && <Badge variant="secondary">Proxied</Badge>}<StatusBadge status={record.synced_at ? "synced" : "pending"} /></div></TableCell>
                                {domain.permissions.can_manage_dns && <TableCell className="text-right">
                                  <div className="flex justify-end gap-1">
                                    <Button aria-label={`Edit ${record.name} ${record.record_type} record`} disabled={isWorking} onClick={() => beginDnsEdit(record)} size="icon" variant="ghost"><Pencil className="size-4" /></Button>
                                    <Button aria-label={`Delete ${record.name} ${record.record_type} record`} disabled={isWorking} loading={workingOn(`deleteDnsRecord:${record.id}`)} size="icon" variant="ghost" onClick={() => void deleteDnsRecord(record)}><Trash2 className="size-4" /></Button>
                                  </div>
                                </TableCell>}
                              </TableRow>
                            ))}
                            {!domain.dns.records.length && <TableRow><TableCell className="py-8 text-center text-muted-foreground" colSpan={domain.permissions.can_manage_dns ? 6 : 5}>No DNS records yet. Add your first record below.</TableCell></TableRow>}
                          </TableBody>
                        </Table>
                        </div>
                      </div>
                      {domain.permissions.can_manage_dns && <form className="space-y-3 rounded-xl border border-orange-200 bg-orange-50/40 p-3 dark:border-orange-900 dark:bg-orange-950/10 [&_input]:border-orange-300 [&_select]:border-orange-300 [&_input]:bg-background [&_select]:bg-background dark:[&_input]:border-orange-800 dark:[&_select]:border-orange-800" onSubmit={(event) => void addDnsRecord(event, domain.dns)}>
                        <div className="flex items-center gap-2 text-sm font-semibold"><Plus className="size-4 text-orange-600" /> Add DNS record</div>
                        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                          <Input aria-label="DNS record name" onChange={(event) => setDnsName(event.target.value)} placeholder="@ or www" value={dnsName} />
                          <select aria-label="DNS record type" className="h-9 rounded-md border border-input bg-background px-3 text-sm" onChange={(event) => setDnsType(event.target.value)} value={dnsType}>
                            {["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA"].map((type) => <option key={type} value={type}>{type}</option>)}
                          </select>
                          <Input aria-label="DNS record value" onChange={(event) => setDnsContent(event.target.value)} placeholder="Record content" required value={dnsContent} />
                          <Input aria-label="DNS record TTL" min={1} onChange={(event) => setDnsTtl(event.target.value)} type="number" value={dnsTtl} />
                          <Button className="bg-orange-500 text-white hover:bg-orange-600 dark:text-white" disabled={isWorking} loading={workingOn(`addDnsRecord:${domain.dns!.id}`)} type="submit"><Plus className="size-4" /> Add record</Button>
                        </div>
                        {(dnsType === "MX" || dnsType === "SRV" || ["A", "AAAA", "CNAME"].includes(dnsType)) && <div className="flex flex-wrap items-center gap-4">
                          {(dnsType === "MX" || dnsType === "SRV") && <Input aria-label="DNS record priority" className="w-32" min={0} onChange={(event) => setDnsPriority(event.target.value)} placeholder="Priority" type="number" value={dnsPriority} />}
                          {["A", "AAAA", "CNAME"].includes(dnsType) && <label className="flex items-center gap-2 text-sm"><input checked={dnsProxied} onChange={(event) => setDnsProxied(event.target.checked)} type="checkbox" /> Proxy through Cloudflare</label>}
                        </div>}
                      </form>}
                    </>
                  ) : (
                  <div className="space-y-3 border-y border-dashed py-4 md:rounded-lg md:border md:px-4">
                      <Button disabled={isWorking} loading={workingOn("loadCloudflareZones")} onClick={() => void loadCloudflareZones(true)} size="sm" type="button" variant="outline">
                        <RefreshCw className="size-4" /> Find Cloudflare zone
                      </Button>
                      {cloudflareZones.filter((zone) => zone.domain_id === domain.id).map((zone) => (
                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/40 p-3" key={`${zone.connection_id}-${zone.cloudflare_zone_id}`}>
                          <p className="text-sm">{zone.domain}</p>
                          <Button disabled={isWorking} loading={workingOn(`linkCloudflareZone:${zone.connection_id}:${zone.cloudflare_zone_id}`)} onClick={() => void linkCloudflareZone(zone)} size="sm" type="button">
                            Link zone
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>}
              </Card>
            )) : <EmptyAction href="/domains/" action="Search domains" />}
            </div>
          </section>}

          {view === "email" && <section className="min-w-0 space-y-4" id="email">
            <SectionHeading image="/dashboard-icons/email.webp" helpHref="/how-to/dashboard-domain-email/" title="Business email" />
            {emailServices.filter((service) => !service.hosting).map((service) => {
              const domainOptions = service.domain_options ?? []
              return (
                <Card key={`pending-${service.uuid}`}>
                  <CardHeader>
                    <CardTitle className="text-base">Choose the domain for {service.product}</CardTitle>
                    <CardDescription>Your email plan is paid and waiting. Select an active domain and we will create the mail service after it is ready.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-2">
                      <select aria-label={`Domain for ${service.product}`} className="h-10 min-w-0 flex-1 rounded-md border border-orange-400 bg-background px-3 text-sm" disabled={!service.permissions.can_manage_email || isWorking} onChange={(event) => void selectServiceDomain(service, event.target.value)} value={domainOptions.find((domain) => domain.selected)?.name ?? ""}>
                        <option value="">Select a domain</option>
                        {domainOptions.map((domain) => <option key={domain.id} value={domain.name}>{domain.name}{domain.status !== "active" ? ` · ${domain.status}` : ""}</option>)}
                      </select>
                    </div>
                    {!domainOptions.some((domain) => domain.status === "active") && <p className="mt-2 text-xs text-muted-foreground">You can select a processing domain now. Email will start working when registration or connection completes.</p>}
                  </CardContent>
                </Card>
              )
            })}
            {emailServices.map((service) => {
              const eligibleDomains = service.domains.filter((domain) =>
                domain.status === "active"
                && domain.permissions.can_manage_email,
              )
              const emailStorage = mailboxStorage(service.hosting)
              return (
              <div className="space-y-3" key={service.uuid}>
                {eligibleDomains.map((domain) => {
                  const emailDomainOptions = Array.from(new Set([
                    domain.name,
                    ...services.flatMap((websiteService) => {
                      if (
                        websiteService.status !== "active"
                        || websiteService.hosting?.status !== "active"
                      ) return []
                      return (websiteService.hosting?.websites ?? [])
                        .filter((website) => (
                          website.status === "active"
                          && website.master_domain.toLowerCase() === domain.name.toLowerCase()
                        ))
                        .map((website) => website.domain_name)
                    }),
                  ]))
                  const requestedEmailDomain = selectedEmailDomainByRoot[domain.id] ?? domain.name
                  const selectedEmailDomain = emailDomainOptions.includes(requestedEmailDomain)
                    ? requestedEmailDomain
                    : domain.name
                  const domainMailboxes = (service.hosting?.mailboxes ?? []).filter((mailbox) =>
                    mailbox.email_address.toLowerCase().endsWith(`@${selectedEmailDomain.toLowerCase()}`)
                      && mailbox.email_address.toLowerCase().includes(mailboxSearch.toLowerCase()),
                  )
                  const domainMailUsedMB = domainMailboxes.reduce((total, mailbox) => total + mailbox.used_mb, 0)
                  const domainMailAllocatedMB = domainMailboxes.reduce((total, mailbox) => total + mailbox.quota_mb, 0)
                  const expanded = expandedEmailDomainId === domain.id
                  return (
              <Card className="border-0 shadow-none md:border md:shadow-sm" key={`${service.uuid}-${domain.id}`}>
                <CardHeader className="p-0">
                  <button
                    aria-expanded={expanded}
                    className="flex w-full min-w-0 items-center justify-between gap-3 rounded-lg p-3 text-left transition-colors hover:bg-muted/40 md:p-4"
                    onClick={() => setExpandedEmailDomainId((current) => current === domain.id ? null : domain.id)}
                    type="button"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <Mail className="size-4 shrink-0 text-orange-600 dark:text-orange-400" />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{domain.name}</span>
                        <span className="mt-1 block truncate text-xs text-muted-foreground">{service.product} · {domainMailboxes.length} email accounts</span>
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <StatusBadge status={domain.status} />
                      <ChevronDown className={`size-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
                    </span>
                  </button>
                </CardHeader>
                {expanded && <CardContent className="space-y-3 px-0 pb-4 pt-3 md:px-6 md:pb-6">
                  <div className="overflow-hidden border-y bg-card md:rounded-xl md:border">
                    <div className="flex flex-wrap items-center justify-between gap-3 py-3 md:border-b md:bg-muted/30 md:px-4">
                      <div>
                        <p className="text-sm font-semibold">Email accounts · {selectedEmailDomain}</p>
                        <p className="text-xs text-muted-foreground">
                          {domainMailboxes.length} accounts · {formatStorageMB(domainMailUsedMB)} used / {formatStorageMB(domainMailAllocatedMB)} allocated
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="sr-only" htmlFor={`email-domain-${service.uuid}-${domain.id}`}>Email domain</label>
                        <select
                          aria-label={`Email domain for ${domain.name}`}
                          className="h-9 min-w-0 max-w-56 rounded-md border bg-background px-2 text-xs"
                          id={`email-domain-${service.uuid}-${domain.id}`}
                          onChange={(event) => setSelectedEmailDomainByRoot((current) => ({
                            ...current,
                            [domain.id]: event.target.value,
                          }))}
                          value={selectedEmailDomain}
                        >
                          {emailDomainOptions.map((emailDomain) => <option key={emailDomain} value={emailDomain}>{emailDomain}</option>)}
                        </select>
                        <div className="relative w-full sm:w-56"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input aria-label="Filter email accounts" className="h-9 pl-9" onChange={(event) => setMailboxSearch(event.target.value)} placeholder="Filter accounts" value={mailboxSearch} /></div>
                        <span className="text-xs text-muted-foreground">{domainMailboxes.length} accounts</span>
                      </div>
                    </div>
                    <Button className="mb-2 h-8 md:hidden" onClick={() => setMobileTablesOpen((state) => ({ ...state, [`mail-${service.uuid}-${domain.id}`]: state[`mail-${service.uuid}-${domain.id}`] === false }))} size="sm" variant="outline">
                      {mobileTablesOpen[`mail-${service.uuid}-${domain.id}`] === false ? "Show email accounts" : "Hide email accounts"}<ChevronDown className={`ml-1 size-4 transition-transform ${mobileTablesOpen[`mail-${service.uuid}-${domain.id}`] === false ? "" : "rotate-180"}`} />
                    </Button>
                    <div className={`overflow-x-auto ${mobileTablesOpen[`mail-${service.uuid}-${domain.id}`] === false ? "hidden md:block" : "block"}`}>
                    <Table className="min-w-[820px]">
                      <TableHeader className="bg-muted/20">
                        <TableRow>
                          <TableHead>Email address</TableHead><TableHead>Storage used</TableHead><TableHead>Status</TableHead>
                          <TableHead>Login</TableHead>{service.permissions.can_manage_email && <TableHead className="text-right">Actions</TableHead>}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {domainMailboxes.map((mailbox) => (
                          <Fragment key={mailbox.id}>
                          <TableRow>
                            <TableCell className="font-medium">
                              <div className="flex items-center gap-2">
                                <span>{mailbox.email_address}</span>
                                {(mailbox.error_message || mailbox.status === "error") && service.permissions.can_manage_email && (
                                  <DismissibleAlert
                                    className="relative !flex-none"
                                    id={`mailbox:${mailbox.id}`}
                                    message={mailbox.error_message ?? mailbox.status}
                                  >
                                    <details className="relative">
                                      <summary aria-label={`View mailbox issue for ${mailbox.email_address}`} className="list-none cursor-pointer rounded-full text-red-600 outline-none transition hover:text-red-700 focus-visible:ring-2 focus-visible:ring-red-500 dark:text-red-400 [&::-webkit-details-marker]:hidden">
                                        <CircleAlert aria-hidden="true" className="size-4" />
                                      </summary>
                                      <div className="absolute left-0 top-full z-50 mt-2 w-[min(20rem,80vw)] rounded-lg border border-red-200 bg-background p-3 text-left font-normal shadow-lg dark:border-red-900">
                                        <p className="text-sm font-semibold text-red-700 dark:text-red-300">{mailbox.status === "error" ? "Mailbox setup failed" : "Mailbox action failed"}</p>
                                        <p className="mt-1 text-xs text-red-700/90 dark:text-red-300/90">{mailbox.error_message ? mailbox.status === "error" ? mailboxSetupMessage(mailbox.error_message) : mailbox.error_message.replace(/CyberPanel/gi, "mail server") : "Mailbox setup needs attention. Retry setup to link the existing mailbox or remove this dashboard entry."}</p>
                                        {mailbox.status === "error" && (
                                          <form className="mt-3 grid gap-2" onSubmit={(event) => void retryMailboxSetup(event, mailbox)}>
                                            <Input aria-label={`New password for ${mailbox.email_address}`} autoComplete="new-password" className="h-9 border-orange-300 bg-background focus-visible:border-orange-500 focus-visible:ring-orange-500/20 dark:border-orange-800 dark:focus-visible:border-orange-400" minLength={8} onChange={(event) => setRetryMailboxPassword(event.target.value)} placeholder="New password (8+ chars)" required type="password" value={retryMailboxPassword} />
                                            <Button className="h-9" disabled={isWorking} loading={workingOn(`retryMailboxSetup:${mailbox.id}`)} type="submit" variant="destructive">Retry setup</Button>
                                          </form>
                                        )}
                                      </div>
                                    </details>
                                  </DismissibleAlert>
                                )}
                              </div>
                            </TableCell>
                            <TableCell>{mailbox.used_mb.toLocaleString()} MB <span className="text-muted-foreground">used / {mailbox.quota_mb.toLocaleString()} MB allocated</span></TableCell>
                            <TableCell><StatusBadge status={mailbox.pending_action === "mailbox_update" ? "updating" : mailbox.pending_action === "mailbox_pw_reset" ? "updating" : mailbox.status} /></TableCell>
                            <TableCell>
                              <Button asChild className="h-8" size="sm" variant="outline">
                                <a href={mailbox.webmail_url ?? `https://${mailbox.email_address.split("@")[1]}/webmail`} rel="noreferrer" target="_blank"><ExternalLink className="size-3.5" /> Webmail</a>
                              </Button>
                            </TableCell>
                            {service.permissions.can_manage_email && <TableCell className="text-right">
                              <div className="flex justify-end gap-1">
                                <Button aria-label={`Change storage allocation for ${mailbox.email_address}`} className="h-8" disabled={isWorking || Boolean(mailbox.pending_action) || mailbox.status !== "active"} onClick={() => beginMailboxQuotaEdit(mailbox)} size="sm" variant="outline">
                                  <Pencil className="size-3.5" /><span className="hidden sm:inline">Storage</span>
                                </Button>
                                <Button aria-label={`Reset password for ${mailbox.email_address}`} className="h-8" disabled={isWorking || Boolean(mailbox.pending_action) || mailbox.status !== "active"} onClick={() => setPasswordResetMailbox(mailbox)} size="sm" variant="outline">
                                  <KeyRound className="size-3.5" /><span className="hidden sm:inline">Reset password</span>
                                </Button>
                                <Button aria-label={`Clear stored messages for ${mailbox.email_address}`} className="h-8" disabled={isWorking || Boolean(mailbox.pending_action) || mailbox.status !== "active"} loading={workingOn(`clearMailboxStorage:${mailbox.id}`)} onClick={() => void clearMailboxStorage(mailbox)} size="sm" variant="outline">
                                  <Eraser className="size-3.5" /><span className="hidden sm:inline">Clear storage</span>
                                </Button>
                                <Button aria-label={`Delete ${mailbox.email_address}`} disabled={isWorking || Boolean(mailbox.pending_action) || mailbox.status === "pending" || mailbox.status === "clearing" || mailbox.status === "deleting" || mailbox.status === "deleted"} loading={workingOn(`deleteMailbox:${mailbox.id}`)} onClick={() => void deleteMailbox(mailbox)} size="icon" variant="ghost">
                                  <Trash2 className="size-4" />
                                </Button>
                              </div>
                            </TableCell>}
                          </TableRow>
                          {editingMailboxQuotaId === mailbox.id && service.permissions.can_manage_email && service.hosting && (
                            <TableRow>
                              <TableCell className="bg-orange-50/60 py-3 dark:bg-orange-950/10" colSpan={service.permissions.can_manage_email ? 5 : 4}>
                                <form className="grid items-end gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]" onSubmit={(event) => void updateMailboxQuota(event, mailbox)}>
                                  <label className="grid min-w-0 gap-1.5 text-sm font-medium">
                                    <span>Size</span>
                                    <span className="flex h-10 min-w-0 overflow-hidden rounded-md border border-orange-300 bg-background dark:border-orange-800">
                                      <Input aria-label={`New storage allocation for ${mailbox.email_address}`} className="h-full min-w-0 flex-1 rounded-none border-0 px-3 focus-visible:ring-0" max={mailboxQuotaInputMax(service.hosting, editingMailboxQuotaUnit, mailbox.quota_mb)} min={mailbox.used_mb} onChange={(event) => setEditingMailboxQuota(event.target.value)} step={editingMailboxQuotaUnit === "GB" ? "0.1" : "1"} type="number" value={editingMailboxQuota} />
                                      <select aria-label="Storage allocation unit" className="h-full shrink-0 border-l border-orange-300 bg-orange-50/70 px-3 text-sm dark:border-orange-800 dark:bg-orange-950/25" onChange={(event) => setEditingMailboxQuotaUnit(event.target.value)} value={editingMailboxQuotaUnit}>
                                        <option value="MB">MB</option><option value="GB">GB</option>
                                      </select>
                                    </span>
                                  </label>
                                  <p className="pb-2 text-xs text-muted-foreground">Currently used: {mailbox.used_mb.toLocaleString()} MB. You can reduce or increase the allocation within your hosting storage.</p>
                                  <div className="flex gap-2">
                                    <Button className="h-10" disabled={isWorking} loading={workingOn(`updateMailboxQuota:${mailbox.id}`)} type="submit">Save allocation</Button>
                                    <Button className="h-10" disabled={isWorking} onClick={() => setEditingMailboxQuotaId(null)} type="button" variant="outline">Cancel</Button>
                                  </div>
                                </form>
                              </TableCell>
                            </TableRow>
                          )}
                          </Fragment>
                        ))}
                        {!domainMailboxes.length && <TableRow><TableCell className="py-8 text-center text-muted-foreground" colSpan={service.permissions.can_manage_email ? 5 : 4}>No email accounts for this domain yet.</TableCell></TableRow>}
                      </TableBody>
                    </Table>
                    </div>
                  </div>
                  {service.status === "active" && service.hosting?.status === "active" && (
                    <form className="grid min-w-0 grid-cols-1 gap-3 rounded-xl border border-orange-200 bg-orange-50/40 p-3 sm:grid-cols-2 xl:grid-cols-12 dark:border-orange-900 dark:bg-orange-950/10" onSubmit={(event) => {
                      event.preventDefault()
                      void createMailbox(event, service, domain, selectedEmailDomain)
                    }}>
                      <label className="grid min-w-0 gap-1.5 text-sm font-medium sm:col-span-2 xl:col-span-4">
                        <span>Mailbox username</span>
                        <span className="flex h-10 min-w-0 overflow-hidden rounded-md border border-orange-300 bg-background focus-within:border-orange-500 focus-within:ring-2 focus-within:ring-orange-500/20 dark:border-orange-800 dark:focus-within:border-orange-500">
                          <Input aria-label="Mailbox username" className="h-full min-w-0 flex-1 rounded-none border-0 px-3 focus-visible:ring-0" onChange={(event) => setMailboxName(event.target.value)} placeholder="e.g. info" required value={mailboxName} />
                          <span className="flex h-full max-w-[55%] min-w-0 shrink-0 items-center border-l border-orange-300 bg-orange-50/70 px-2.5 text-sm font-normal text-muted-foreground dark:border-orange-800 dark:bg-orange-950/25" title={`@${selectedEmailDomain}`}>
                            <span className="truncate">@{selectedEmailDomain}</span>
                          </span>
                        </span>
                      </label>
                      <label className="grid min-w-0 gap-1.5 text-sm font-medium xl:col-span-2">
                        <span>Size</span>
                        <span className="flex h-10 min-w-0 overflow-hidden rounded-md border border-orange-300 bg-background focus-within:border-orange-500 focus-within:ring-2 focus-within:ring-orange-500/20 dark:border-orange-800 dark:focus-within:border-orange-500">
                          <Input aria-label={`Mailbox disk allocation in ${mailboxQuotaUnit}`} className="h-full min-w-0 flex-1 rounded-none border-0 px-3 focus-visible:ring-0" max={mailboxQuotaInputMax(service.hosting, mailboxQuotaUnit)} min={1} onChange={(event) => setMailboxQuota(event.target.value)} step={mailboxQuotaUnit === "GB" ? "0.1" : "1"} type="number" value={mailboxQuota} />
                          <select aria-label="Mailbox disk allocation unit" className="h-full shrink-0 border-l border-orange-300 bg-orange-50/70 px-3 text-sm font-medium outline-none dark:border-orange-800 dark:bg-orange-950/25" onChange={(event) => setMailboxQuotaUnit(event.target.value)} value={mailboxQuotaUnit}>
                            <option value="MB">MB</option><option value="GB">GB</option>
                          </select>
                        </span>
                      </label>
                      <label className="grid min-w-0 gap-1.5 text-sm font-medium sm:col-span-2 xl:col-span-3">
                        <span>Password</span>
                        <span className="relative block min-w-0">
                          <Input aria-label="Mailbox password" autoComplete="new-password" className="h-10 border-orange-300 bg-background pr-10 focus-visible:border-orange-500 focus-visible:ring-orange-500/20 dark:border-orange-800 dark:focus-visible:border-orange-400" minLength={8} onChange={(event) => setMailboxPassword(event.target.value)} placeholder="At least 8 characters" required type={showMailboxPassword ? "text" : "password"} value={mailboxPassword} />
                          <Button aria-label={showMailboxPassword ? "Hide password" : "Show password"} className="absolute right-0 top-0 size-10 text-muted-foreground hover:bg-transparent" onClick={() => setShowMailboxPassword((show) => !show)} size="icon" type="button" variant="ghost">{showMailboxPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</Button>
                        </span>
                      </label>
                      <div className="flex min-w-0 items-end sm:col-span-2 xl:col-span-3">
                        <Button className="h-10 w-full border border-orange-600 bg-orange-600 bg-none text-white hover:bg-orange-700 dark:border-orange-500 dark:bg-orange-600 dark:bg-none dark:text-white dark:hover:bg-orange-700" disabled={isWorking} loading={workingOn(`createMailbox:${service.uuid}:${selectedEmailDomain}`)} type="submit"><Plus className="size-4" /> Create mailbox</Button>
                      </div>
                    </form>
                  )}
                  {service.permissions.can_manage_email && service.hosting && (
                    <p className="text-xs text-muted-foreground">
                      {emailStorage.availableMB === null
                        ? "Mailbox disk allocation is checked against your hosting plan."
                        : `${formatStorageMB(emailStorage.availableMB)} unallocated after ${formatStorageMB(emailStorage.webUsedMB)} of website files and ${formatStorageMB(emailStorage.allocatedMB)} reserved for mailboxes · ${formatStorageMB(emailStorage.limitMB ?? 0)} total`}
                    </p>
                  )}
                  {service.permissions.can_manage_email && <p className="text-xs text-muted-foreground">Choose a password of at least 8 characters to sign in to webmail.</p>}
                  {service.permissions.can_manage_email && service.hosting?.mailboxes.length ? (
                    <form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => void grantMailboxAccess(event, service.uuid)}>
                      <select aria-label="Mailbox to share" className="h-9 rounded-md border border-black bg-background px-3 text-sm dark:border-white" onChange={(event) => setSelectedMailbox(event.target.value)} value={selectedMailbox}>
                        <option value="">Select mailbox</option>
                        {service.hosting.mailboxes.map((mailbox) => <option key={mailbox.id} value={mailbox.id}>{mailbox.email_address}</option>)}
                      </select>
                      <Input aria-label="Customer email to grant access" onChange={(event) => setAccessEmail(event.target.value)} placeholder="team@example.com" required type="email" value={accessEmail} />
                      <Button disabled={isWorking || !selectedMailbox} loading={workingOn(`grantMailboxAccess:${service.uuid}`)} type="submit">Grant mailbox access</Button>
                    </form>
                  ) : null}
                  {(service.status !== "active" || service.hosting?.status !== "active") && (
                    <Button asChild size="sm" variant="outline"><Link href="/shop/?service=email">Browse email plans <ArrowUpRight className="size-4" /></Link></Button>
                  )}
                </CardContent>}
              </Card>
                  )
                })}
                {!eligibleDomains.length && <Card><CardContent className="flex flex-wrap items-center gap-2 p-4 text-sm text-muted-foreground"><Globe2 className="size-4 text-orange-600" />{service.hosting?.primary_domain ? <>Your domain <strong className="text-foreground">{service.hosting.primary_domain}</strong> is assigned to email hosting. It is still processing; wait for it to go live before creating email accounts.</> : <>Select a domain to manage its email accounts.</>}<Button asChild className="h-auto px-1 text-orange-700 dark:text-orange-300" size="sm" variant="link"><Link href="/dashboard/domains/">Select domain <ArrowUpRight className="size-3.5" /></Link></Button></CardContent></Card>}
              </div>
              )
            })}
            {!emailServices.length && <EmptyAction href="/shop/?service=email" action="Browse email plans" />}
          </section>}

          {view === "billing" && <section className="space-y-4" id="billing">
            <SectionHeading title="Billing & invoices" />
            <div className="grid items-start gap-3 lg:grid-cols-[320px_minmax(0,1fr)]">
              <div className="relative isolate h-[202px] w-full max-w-[320px] overflow-hidden rounded-xl border border-white/15 bg-gradient-to-br from-zinc-950 via-slate-900 to-orange-950 p-4 text-white shadow-sm">
                <span aria-hidden="true" className="pointer-events-none absolute -right-12 -top-20 size-64 rounded-full border border-white/10" />
                <span aria-hidden="true" className="pointer-events-none absolute -right-2 -top-10 size-44 rounded-full border border-white/10" />
                <span aria-hidden="true" className="pointer-events-none absolute -bottom-24 left-1/3 size-56 rounded-full bg-orange-500/10 blur-2xl" />
                <div className="relative flex h-full min-w-0 flex-col justify-between gap-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="grid size-7 shrink-0 grid-cols-2 overflow-hidden rounded-lg border border-amber-100/50 bg-gradient-to-br from-amber-200 to-orange-500 p-1 shadow-sm">
                        <span className="rounded-tl border-r border-b border-orange-950/25" /><span className="rounded-tr border-b border-orange-950/25" />
                        <span className="rounded-bl border-r border-orange-950/25" /><span className="rounded-br" />
                      </span>
                      <div><p className="text-xs font-bold tracking-[0.18em]">TECHINN</p><p className="text-[8px] font-medium tracking-[0.16em] text-white/65">ACCOUNT BALANCE</p></div>
                    </div>
                    <span className="rounded-full border border-white/20 bg-white/10 px-2.5 py-1 text-[10px] font-semibold tracking-wider text-white/90">{wallet?.currency ?? "USD"}</span>
                  </div>
                  <div>
                    <p className="text-xs text-white/65">Available balance</p>
                    <p className="mt-0.5 text-3xl font-semibold tracking-tight tabular-nums">{formatMoney(wallet?.balance ?? "0.00", wallet?.currency ?? "USD")}</p>
                    {wallet?.transactions.some((transaction) => transaction.is_test) && <Badge className="mt-1 h-4 border-white/25 bg-white/10 px-1.5 text-[9px] text-white" variant="outline">Includes test funds</Badge>}
                  </div>
                  <div className="flex items-end justify-between gap-3 border-t border-white/15 pt-2">
                    <div className="min-w-0"><p className="text-[9px] font-semibold tracking-[0.18em] text-white/55">ACCOUNT HOLDER</p><p className="mt-0.5 truncate text-xs font-medium">{[customer?.first_name, customer?.last_name].filter(Boolean).join(" ") || customer?.email}</p></div>
                    <div className="shrink-0 text-right"><p className="text-[9px] font-semibold tracking-[0.18em] text-white/55">ACTIVE SERVICES</p><p className="mt-0.5 text-xs font-medium">{services.filter((service) => service.status === "active").length}</p></div>
                  </div>
                </div>
              </div>

              <div className="min-w-0 max-w-2xl space-y-3" id="billing-payment">
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b pb-2 text-xs">
                  <p className="text-muted-foreground">Outstanding <span className="ml-1 font-semibold tabular-nums text-foreground">{formatMoney(outstandingTotal, wallet?.currency ?? "USD")}</span></p>
                  <p className="text-muted-foreground">Reminders <span className="ml-1 font-semibold tabular-nums text-foreground">{billingReminders.length}</span></p>
                </div>
                <div>
                  <h3 className="mb-2 text-sm font-semibold">{renewalServiceUuid ? "Renew this service" : "Add balance"}</h3>
                  {renewalServiceUuid && !renewalDetailsLoading && <p className="mb-2 rounded-md border-2 border-orange-400 bg-orange-50 px-2.5 py-2 text-xs text-orange-950 dark:border-orange-700 dark:bg-orange-950/30 dark:text-orange-100"><strong>Renewal deposit for {renewalService?.product ?? "the selected service"}{renewalService?.hosting?.primary_domain ? ` · ${renewalService.hosting.primary_domain}` : ""}.</strong> This payment is reserved for this renewal and will not be added to your general balance.</p>}
                  {renewalServiceUuid && <label className="mb-2 grid max-w-xs gap-1 text-xs font-medium">Renewal period<select aria-label="Renewal period" className="h-9 rounded-md border bg-background px-2 text-sm" onChange={(event) => setRenewalBillingInterval(event.target.value as "monthly" | "yearly")} value={renewalBillingInterval}><>{!renewalYearlyOnly && <option value="monthly">Monthly</option>}</><option value="yearly">Yearly · save 10%</option></select></label>}
                    <form className="grid gap-2 sm:grid-cols-2" onSubmit={(event) => void submitDeposit(event)}>
                      <label className="grid min-w-0 gap-1 text-xs font-medium" htmlFor="deposit-amount">Deposit amount ({wallet?.currency ?? "USD"})
                        <span className="flex h-9 items-center rounded-md border border-orange-300 bg-background px-3 focus-within:border-orange-500 focus-within:ring-2 focus-within:ring-orange-500/20 dark:border-orange-900"><span className="mr-2 text-muted-foreground">$</span><Input aria-label="Deposit amount" className="h-full border-0 px-0 shadow-none focus-visible:ring-0" id="deposit-amount" max="10000" min="0.01" onChange={(event) => setDepositAmount(event.target.value)} required step="0.01" type="number" value={depositAmount} /></span>
                      </label>
                      <fieldset className="grid grid-cols-3 gap-1.5">
                        <legend className="mb-1 text-xs font-medium">Pay with</legend>
                        {checkoutPaymentMethods.map((method) => <label className={`flex h-9 cursor-pointer items-center justify-center rounded-md border bg-background px-1 transition-colors ${depositMethod === method.id ? "border-orange-500 bg-orange-500/5 ring-1 ring-orange-500/30" : "hover:border-orange-400/60"}`} key={method.id}>
                          <input checked={depositMethod === method.id} className="sr-only" name="deposit-payment-method" onChange={() => setDepositMethod(method.id as typeof depositMethod)} type="radio" value={method.id} />
                          <Image alt={method.name} className="max-h-6 w-auto max-w-full object-contain" height={method.height} src={method.image} unoptimized width={method.width} />
                        </label>)}
                      </fieldset>
                      {depositMethod !== "card" && <label className="grid gap-1 text-xs font-medium" htmlFor="deposit-phone">{depositMethod === "ecocash" ? "EcoCash number" : "OneMoney number"}<Input autoComplete="tel" className="h-9" id="deposit-phone" inputMode="tel" onChange={(event) => setDepositPhone(event.target.value)} required type="tel" value={depositPhone} /></label>}
                      <Button aria-label={renewalServiceUuid ? "Deposit for this service renewal only" : "Deposit to account balance"} className="h-9 w-full self-end bg-orange-600 bg-none text-white hover:bg-orange-700 dark:bg-orange-600 dark:text-white dark:hover:bg-orange-700" disabled={depositSubmitting || depositPayment?.status === "processing"} id="deposit-submit" loading={depositSubmitting} type="submit"><CreditCard className="size-4" />{renewalServiceUuid ? "Pay renewal" : "Deposit"} {formatMoney(depositAmount, wallet?.currency ?? "USD")}</Button>
                    </form>
                    {depositError && <DismissibleAlert className="mt-2 text-xs text-destructive" id="deposit" message={depositError} />}
                    {depositPayment && (() => {
                      const paymentFailed = ["failed", "cancelled", "expired"].includes(depositPayment.status)
                      const message = depositPayment.status === "successful"
                        ? `${formatMoney(depositPayment.amount, depositPayment.currency)} was added to your balance.`
                        : depositPayment.status === "processing"
                          ? "Approve the payment request. We’ll update the balance as soon as Paynow confirms it."
                          : depositPayment.message
                      const content = (
                        <div className={`mt-3 rounded-md border p-2.5 text-xs ${depositPayment.status === "successful" ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-800 dark:text-emerald-300" : paymentFailed ? "border-destructive/30 bg-destructive/5 text-destructive" : "border-orange-500/30 bg-orange-500/5 text-foreground"}`} role="status">
                          <p className="font-semibold capitalize">{depositPayment.status === "successful" ? "Deposit confirmed" : depositPayment.status === "processing" ? "Waiting for payment confirmation" : `Deposit ${depositPayment.status}`}</p>
                          <p className="mt-1">{message}</p>
                          {depositPayment.status === "processing" && <Button className="mt-2 h-7 px-2 text-xs" onClick={() => void checkDepositStatus()} size="sm" type="button" variant="outline"><RefreshCw className="size-3" />Check status</Button>}
                        </div>
                      )
                      return paymentFailed
                        ? <DismissibleAlert className="text-destructive" id={`deposit-payment:${depositPayment.uuid}`} message={message}>{content}</DismissibleAlert>
                        : content
                    })()}
                </div>
              </div>
            </div>

            {billingError && <DismissibleAlert className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive" id="billing" message={`Billing details are temporarily unavailable: ${billingError}`} />}

            <div className="min-w-0 space-y-3">
              <div className="min-w-0 overflow-hidden border-y bg-card md:rounded-xl md:border" id="billing-invoices">
                <Tabs className="gap-0" onValueChange={setInvoiceFilter} value={invoiceFilter}>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/30 py-2 md:px-4">
                    <h3 className="text-sm font-semibold">Invoices</h3>
                    <TabsList className="grid w-full grid-cols-3 sm:w-auto">
                      <TabsTrigger value="all">All <span className="ml-1 text-xs text-muted-foreground">{invoices.length}</span></TabsTrigger>
                      <TabsTrigger value="open">Due <span className="ml-1 text-xs text-muted-foreground">{outstandingInvoices.length}</span></TabsTrigger>
                      <TabsTrigger value="paid">Paid</TabsTrigger>
                    </TabsList>
                  </div>
                  <div className="min-w-0 overflow-x-auto">
                    <TabsContent className="mt-0" value={invoiceFilter}>
                  {visibleInvoices.length ? (
                    <Table className="min-w-[640px]">
                      <TableHeader className="bg-muted/20"><TableRow><TableHead>Invoice</TableHead><TableHead>Issued</TableHead><TableHead>Payment</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Amount</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {visibleInvoices.map((invoice) => {
                          const method = invoice.payment_method
                          const methodLabel = method === "ecocash" ? "EcoCash" : method === "onemoney" ? "OneMoney" : method === "card" ? "Cards" : method === "test" || invoice.is_test ? "Test payment" : "—"
                          return <TableRow key={invoice.invoice_number}>
                            <TableCell className="max-w-64"><p className="truncate font-medium" title={invoice.invoice_number}>{invoice.invoice_number}</p><p className="mt-1 truncate text-xs text-muted-foreground" title={invoice.items.map((item) => item.description).join(", ")}>{invoice.items.map((item) => item.description).join(", ") || "TechInn services"}</p>{invoice.is_test && <Badge className="mt-1" variant="outline">Test</Badge>}</TableCell>
                            <TableCell>{formatDate(invoice.paid_at ?? invoice.created_at)}</TableCell>
                            <TableCell><span className="inline-flex items-center gap-2 text-xs">{method === "ecocash" || method === "onemoney" || method === "card" ? <Image alt="" height={20} src={checkoutPaymentMethods.find((option) => option.id === method)?.image ?? "/payment-methods/local-payment-options.svg"} unoptimized width={method === "onemoney" ? 28 : 52} /> : null}{methodLabel}</span></TableCell>
                            <TableCell><StatusBadge status={invoice.status} /></TableCell>
                            <TableCell className="text-right font-semibold tabular-nums">{formatMoney(isOpenInvoice(invoice) ? amountDue(invoice) : invoice.total, invoice.currency)}</TableCell>
                          </TableRow>
                        })}
                      </TableBody>
                    </Table>
                  ) : <p className="p-4 text-sm text-muted-foreground">{billingError ? "Invoice history could not be loaded." : invoiceFilter === "all" ? "No invoices yet." : invoiceFilter === "open" ? "No outstanding invoices." : "No paid invoices yet."}</p>}
                    </TabsContent>
                  </div>
                </Tabs>
              </div>

              <div className="min-w-0 overflow-hidden border-y bg-card md:rounded-xl md:border">
                <div className="flex items-center justify-between gap-2 border-b bg-muted/30 py-3 md:px-4">
                  <h3 className="text-sm font-semibold">Balance records</h3>
                  <span className="text-xs text-muted-foreground">{wallet?.transactions.length ?? 0} records</span>
                </div>
                <Table className="min-w-[580px]">
                  <TableHeader className="bg-muted/20"><TableRow><TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Amount</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {wallet?.transactions.map((transaction, index) => <TableRow key={`${transaction.created_at}-${index}`}>
                      <TableCell>{formatDate(transaction.created_at)}</TableCell>
                      <TableCell className="max-w-80"><div className="flex items-center gap-2"><span className="truncate font-medium" title={transaction.description}>{transaction.description}</span>{transaction.is_test && <Badge variant="outline">Test</Badge>}</div></TableCell>
                      <TableCell><Badge variant="secondary">{transaction.type === "credit" ? "Credit" : "Debit"}</Badge></TableCell>
                      <TableCell className={`text-right font-semibold tabular-nums ${transaction.type === "credit" ? "text-emerald-700 dark:text-emerald-400" : "text-foreground"}`}>{transaction.type === "credit" ? "+" : "−"}{formatMoney(transaction.amount, wallet.currency)}</TableCell>
                    </TableRow>)}
                    {!wallet?.transactions.length && <TableRow><TableCell className="text-muted-foreground" colSpan={4}>No balance records yet.</TableCell></TableRow>}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="min-w-0 overflow-hidden border-y bg-card md:rounded-xl md:border" id="billing-services">
              <div className="border-b bg-muted/30 py-3 md:px-4"><h3 className="text-sm font-semibold">Services available for renewal</h3></div>
              <div className="divide-y">
                {services.filter((service) => service.renewal && service.expires_at).map((service) => (
                  <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3 md:px-4" key={service.uuid}>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{service.product}{service.hosting?.primary_domain ? ` · ${service.hosting.primary_domain}` : ""}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{service.billing?.interval === "yearly" ? "Yearly" : "Monthly"} renewal · Due {formatDate(service.next_due_at ?? service.expires_at)}</p>
                    </div>
                    <Button asChild disabled={renewingServiceUuid === service.uuid} loading={renewingServiceUuid === service.uuid} onClick={() => setRenewingServiceUuid(service.uuid)} size="sm" variant="outline"><Link href={service.renewal!.href}>Renew <ArrowUpRight className="size-3.5" /></Link></Button>
                  </div>
                ))}
                {!services.some((service) => service.renewal && service.expires_at) && <p className="p-3 text-sm text-muted-foreground">No renewable services yet.</p>}
              </div>
            </div>

            <div className="min-w-0 overflow-hidden border-y bg-card md:rounded-xl md:border">
              <div className="border-b bg-muted/30 py-3 md:px-4"><h3 className="text-sm font-semibold">Billing reminders</h3></div>
              <div className="divide-y">
                {billingReminders.map((reminder, index) => {
                  const isPastDue = currentTime !== null && new Date(reminder.date).getTime() < currentTime && reminder.type === "Invoice due"
                  return <div className="flex flex-wrap items-center justify-between gap-3 py-2.5 md:px-4" key={`${reminder.type}-${reminder.label}-${index}`}>
                    <div className="flex min-w-0 items-start gap-3"><span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${isPastDue ? "bg-destructive/10 text-destructive" : "bg-orange-500/10 text-orange-700 dark:text-orange-300"}`}>{reminder.type === "Invoice due" ? <ReceiptText className="size-4" /> : <CalendarClock className="size-4" />}</span><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-medium">{reminder.label}</p>{isPastDue && <Badge variant="destructive">Past due</Badge>}</div><p className="mt-1 truncate text-xs text-muted-foreground" title={reminder.detail}>{reminder.detail}</p></div></div>
                    <div className="flex w-full items-center justify-between gap-3 sm:w-auto sm:justify-end"><span className="text-xs text-muted-foreground">{formatDate(reminder.date)}</span><Button asChild size="sm" variant="outline"><Link href={reminder.href}>{reminder.action}<ArrowUpRight className="size-3.5" /></Link></Button></div>
                  </div>
                })}
                {!billingReminders.length && <p className="p-3 text-sm text-muted-foreground">No upcoming reminders.</p>}
              </div>
            </div>
          </section>}

          {view === "activity" && <section className="space-y-4" id="activity">
            <SectionHeading title="Notifications & activity" description="Follow recent service changes and provisioning requests." />
            <CustomerSettings mode="notifications" />
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Provisioning reminders</CardTitle>
                  <CardDescription>Recent requests to create or update hosting, mailboxes and DNS.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {activityError && <DismissibleAlert className="text-sm text-destructive" id="activity-reminders" message={`Some activity could not be loaded: ${activityError}`} />}
                  {provisioningActions.slice(0, 6).map((action) => (
                    <div className="flex items-center justify-between gap-3 border-b pb-3 last:border-0 last:pb-0" key={action.id}>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{action.action_type.replaceAll("_", " ")}</p>
                        <p className="text-xs text-muted-foreground">{formatDate(action.scheduled_at)}</p>
                      </div>
                      <StatusBadge status={action.status} />
                    </div>
                  ))}
                  {!provisioningActions.length && !activityError && <p className="text-sm text-muted-foreground">No provisioning requests have been recorded.</p>}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Recent account activity</CardTitle>
                  <CardDescription>Changes recorded for services you can access.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {activityError && <DismissibleAlert className="text-sm text-destructive" id="activity-history" message={`Some activity could not be loaded: ${activityError}`} />}
                  {activity.slice(0, 6).map((event) => (
                    <div className="border-b pb-3 last:border-0 last:pb-0" key={event.id}>
                      <p className="text-sm font-medium">{event.event_type.replaceAll(".", " ").replaceAll("_", " ")}</p>
                      <p className="text-xs text-muted-foreground">{event.entity_type} · {formatDate(event.created_at)}</p>
                    </div>
                  ))}
                  {!activity.length && !activityError && <p className="text-sm text-muted-foreground">No recent service activity has been recorded.</p>}
                </CardContent>
              </Card>
            </div>
          </section>}

          {view === "account" && <section className="space-y-4" id="account">
            <SectionHeading title="Personal details & business" description="Keep the contact details on your TechInn account up to date." />
            <div className="grid gap-4 xl:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base"><UserRound className="size-4 text-amber-600 dark:text-amber-400" />Personal and business details</CardTitle>
                  <CardDescription>These details are used to identify your account and contact you about services.</CardDescription>
                </CardHeader>
                <CardContent>
                  <form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => void updateProfile(event)}>
                    <label className="space-y-1 text-sm">First name<Input autoComplete="given-name" onChange={(event) => setProfileForm({ ...profileValues, first_name: event.target.value })} required value={profileValues.first_name} /></label>
                    <label className="space-y-1 text-sm">Last name<Input autoComplete="family-name" onChange={(event) => setProfileForm({ ...profileValues, last_name: event.target.value })} value={profileValues.last_name} /></label>
                    <label className="space-y-1 text-sm sm:col-span-2">Account email<Input autoComplete="email" disabled value={customer?.email ?? ""} /></label>
                    <label className="space-y-1 text-sm">Phone<Input autoComplete="tel" onChange={(event) => setProfileForm({ ...profileValues, phone: event.target.value })} value={profileValues.phone} /></label>
                    <label className="space-y-1 text-sm">Business name<Input autoComplete="organization" onChange={(event) => setProfileForm({ ...profileValues, company_name: event.target.value })} value={profileValues.company_name} /></label>
                    <Button className="sm:col-span-2 sm:justify-self-start" disabled={isWorking} loading={workingOn("updateProfile")} type="submit"><Building2 className="size-4" /> Save account details</Button>
                  </form>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="size-4 text-amber-600 dark:text-amber-400" />Password & security</CardTitle>
                  <CardDescription>Request a one-time code, then choose a strong, unique password. The code is sent to {customer?.email ?? "your account email"}.</CardDescription>
                </CardHeader>
                <CardContent>
                  <form className="space-y-3" onSubmit={(event) => void changePassword(event)}>
                    {!accountPasswordOtpRequested ? <p className="rounded-md border border-orange-200 bg-orange-50/60 p-3 text-sm text-muted-foreground dark:border-orange-900 dark:bg-orange-950/20">We will email a 6-digit code before showing the password fields.</p> : <>
                      <label className="block space-y-1 text-sm">Verification code<Input autoFocus autoComplete="one-time-code" inputMode="numeric" maxLength={6} onChange={(event) => setAccountPasswordOtp(event.target.value.replace(/\D/g, ""))} required value={accountPasswordOtp} /></label>
                      <label className="block space-y-1 text-sm">New password<Input autoComplete="new-password" minLength={8} onChange={(event) => setNewPassword(event.target.value)} required type="password" value={newPassword} /></label>
                      <label className="block space-y-1 text-sm">Confirm new password<Input autoComplete="new-password" onChange={(event) => setConfirmPassword(event.target.value)} required type="password" value={confirmPassword} /></label>
                    </>}
                    <Button disabled={isWorking} loading={workingOn("changePassword")} type="submit"><KeyRound className="size-4" /> {accountPasswordOtpRequested ? "Set new password" : "Email verification code"}</Button>
                    {accountPasswordOtpRequested && <Button className="w-full" disabled={isWorking} onClick={() => { setAccountPasswordOtpRequested(false); setAccountPasswordOtp(""); setNewPassword(""); setConfirmPassword("") }} type="button" variant="outline">Start over</Button>}
                    <p className="text-xs text-muted-foreground">Other signed-in sessions are revoked when your password changes.</p>
                  </form>
                </CardContent>
              </Card>
            </div>
            <CustomerSettings mode="addresses" />
          </section>}

          {view === "connections" && <DomainConnections providers={dashboard?.provider_connections ?? []} advanced={
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base"><Cloud className="size-4 text-amber-600 dark:text-amber-400" /> Cloudflare</CardTitle>
                <CardDescription>Your API token is encrypted by the backend and is never sent back to the browser.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  {(dashboard?.provider_connections ?? []).filter((connection) => connection.provider === "cloudflare").map((connection) => (
                    <div className="flex items-center justify-between gap-3 rounded-md border p-3" key={connection.id}>
                      <div><p className="font-medium">{connection.name}</p><p className="text-xs text-muted-foreground">Verified {formatDate(connection.last_verified_at)}</p></div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={connection.status} />
                      <Button aria-label={`Revoke ${connection.name}`} disabled={isWorking} loading={workingOn(`revokeCloudflare:${connection.id}`)} onClick={() => void revokeCloudflare(connection.id)} size="sm" variant="outline">Revoke</Button>
                    </div>
                    </div>
                  ))}
                </div>
                <form className="grid gap-2 sm:grid-cols-[1fr_auto]" onSubmit={(event) => void connectCloudflare(event)}>
                  <Input autoComplete="off" onChange={(event) => setCloudflareToken(event.target.value)} placeholder="Cloudflare API token" required type="password" value={cloudflareToken} />
                  <Button disabled={isWorking} loading={workingOn("connectCloudflare")} type="submit">Connect and verify</Button>
                </form>
                <div className="flex flex-wrap items-center gap-2">
                  <Button disabled={isWorking} loading={workingOn("loadCloudflareZones")} onClick={() => void loadCloudflareZones(true)} type="button" variant="outline">
                    <RefreshCw className="size-4" /> Find my domain zones
                  </Button>
                  {cloudflareZones.map((zone) => (
                    <Button disabled={isWorking} loading={workingOn(`linkCloudflareZone:${zone.connection_id}:${zone.cloudflare_zone_id}`)} key={`${zone.connection_id}-${zone.cloudflare_zone_id}`} onClick={() => void linkCloudflareZone(zone)} size="sm" variant="secondary">
                      Link {zone.domain} <ArrowUpRight className="size-3" />
                    </Button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  Use a restricted Cloudflare token with Zone Read and DNS Edit permissions. DNS changes stay queued until the DNS worker processes them.
                </p>
              </CardContent>
            </Card>
          } />}

          {view === "team" && <section className="space-y-4" id="team">
            <SectionHeading title="Service team" description="Grant another registered TechInn customer access to a service." />
            {services.filter((service) => service.is_owner).map((service) => (
              <ServiceTeam key={service.uuid} service={service} />
            ))}
            {!services.some((service) => service.is_owner) && <p className="text-sm text-muted-foreground">Only the service owner can manage team access.</p>}
          </section>}
        </>
      )}
    </div>
  )
}

function SummaryCard({
  image,
  icon,
  label,
  value,
}: {
  image: string
  icon: React.ReactNode
  label: string
  value: string | number
}) {
  return (
    <Card className="group relative min-h-36 overflow-hidden border-0 bg-slate-950 text-white shadow-md transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-lg">
      <Image
        alt=""
        className="object-cover object-center opacity-85 transition-transform duration-500 group-hover:scale-105"
        fill
        sizes="(min-width: 1280px) 25vw, (min-width: 640px) 50vw, 100vw"
        src={image}
      />
      <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-r from-slate-950/90 via-slate-950/60 to-slate-950/10" />
      <CardContent className="relative flex min-h-36 items-end justify-between gap-3 p-4 sm:p-5">
        <div>
          <p className="text-sm font-medium text-white/85">{label}</p>
          <p className="mt-1 text-3xl font-semibold tracking-tight text-white">{value}</p>
        </div>
        <span className="mb-1 rounded-xl border border-white/25 bg-white/15 p-2.5 text-white shadow-sm backdrop-blur-sm">{icon}</span>
      </CardContent>
    </Card>
  )
}

function DashboardLoadingSkeleton({ view }: { view: string }) {
  return (
    <div aria-label={`Loading ${dashboardViewTitles[view]?.toLowerCase() ?? "dashboard"}`} aria-live="polite" className="min-w-0 space-y-6" role="status">
      {view === "overview" && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, index) => (
              <Card className="min-h-36 overflow-hidden" key={index}>
                <CardContent className="flex min-h-36 items-end justify-between p-4 sm:p-5">
                  <div className="space-y-2"><Skeleton className="h-4 w-28" /><Skeleton className="h-8 w-16" /></div>
                  <Skeleton className="mb-1 size-10 rounded-xl" />
                </CardContent>
              </Card>
            ))}
          </div>
          <LoadingSection title="Quick actions" description="Jump straight to the things you can create and manage.">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }, (_, index) => (
                <Card key={index}><CardContent className="flex min-h-28 items-start gap-3 p-4">
                  <Skeleton className="size-9 shrink-0 rounded-lg" />
                  <div className="min-w-0 flex-1 space-y-2"><Skeleton className="h-5 w-28 max-w-full" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-2/3" /></div>
                </CardContent></Card>
              ))}
            </div>
          </LoadingSection>
        </>
      )}

      {view === "web" && (
        <LoadingSection image="/dashboard-icons/hosting.webp" title="Websites & hosting" description="Choose a domain for your website.">
          <Card><CardHeader className="space-y-3"><Skeleton className="h-6 w-48" /><Skeleton className="h-4 w-56 max-w-full" /></CardHeader>
            <CardContent className="space-y-5">
              <div className="max-w-xl space-y-2"><Skeleton className="h-4 w-32" /><Skeleton className="h-10 w-full" /></div>
              <Skeleton className="h-10 w-40 rounded-md" />
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {Array.from({ length: 4 }, (_, index) => <div className="space-y-2 rounded-lg border p-3" key={index}><Skeleton className="h-4 w-24" /><Skeleton className="h-5 w-32 max-w-full" /></div>)}
              </div>
            </CardContent>
          </Card>
        </LoadingSection>
      )}

      {view === "analytics" && (
        <LoadingSection title="Analytics & performance" description="See available hosting usage and understand what still needs to be connected.">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader><Skeleton className="h-5 w-48" /><Skeleton className="h-4 w-64 max-w-full" /></CardHeader><CardContent className="space-y-5">
              {Array.from({ length: 4 }, (_, index) => <div className="space-y-2" key={index}><div className="flex justify-between gap-3"><Skeleton className="h-4 w-40 max-w-[60%]" /><Skeleton className="h-4 w-24 max-w-[35%]" /></div><Skeleton className="h-2 w-full rounded-full" /></div>)}
            </CardContent></Card>
            <Card><CardHeader><Skeleton className="h-5 w-40" /><Skeleton className="h-4 w-48 max-w-full" /></CardHeader><CardContent className="space-y-3"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-9 w-36 rounded-md" /></CardContent></Card>
          </div>
        </LoadingSection>
      )}

      {view === "domains" && (
        <LoadingSection image="/dashboard-icons/domain.webp" title="Domains & DNS">
          <Card><CardContent className="space-y-3 p-4"><Skeleton className="h-5 w-44" /><div className="flex flex-col gap-2 sm:flex-row"><Skeleton className="h-10 min-w-0 flex-1" /><Skeleton className="h-10 w-28" /></div></CardContent></Card>
          <Card className="overflow-hidden border-orange-200 dark:border-orange-900">
            <CardHeader className="flex flex-row items-center gap-3 border-b border-orange-100 bg-orange-50/60 py-3 dark:border-orange-950 dark:bg-orange-950/20"><Skeleton className="size-9 rounded-lg" /><div className="space-y-2"><Skeleton className="h-5 w-48" /><Skeleton className="h-4 w-24" /></div></CardHeader>
            <CardContent className="space-y-3 p-4"><Skeleton className="h-10 w-full" /><div className="flex flex-wrap gap-2"><Skeleton className="h-9 w-32" /><Skeleton className="h-9 w-32" /></div></CardContent>
          </Card>
          <Card><CardHeader className="flex flex-row items-center justify-between"><div className="space-y-2"><Skeleton className="h-5 w-40" /><Skeleton className="h-4 w-56 max-w-full" /></div><Skeleton className="h-9 w-24" /></CardHeader><CardContent><LoadingTable columns={["w-32", "w-16", "w-40", "w-24"]} /></CardContent></Card>
        </LoadingSection>
      )}

      {view === "email" && (
        <LoadingSection image="/dashboard-icons/email.webp" title="Business email">
          {Array.from({ length: 2 }, (_, index) => (
            <Card className="overflow-hidden border-0 shadow-none md:border md:shadow-sm" key={index}>
              <CardHeader className="flex flex-row items-center justify-between p-3 md:p-4"><div className="flex min-w-0 items-center gap-3"><Skeleton className="size-5 shrink-0 rounded" /><div className="space-y-2"><Skeleton className="h-5 w-40 max-w-full" /><Skeleton className="h-4 w-48 max-w-full" /></div></div><Skeleton className="h-6 w-20 rounded-full" /></CardHeader>
              {index === 0 && <CardContent className="space-y-4 px-0 pb-4 pt-3 md:px-6 md:pb-6">
                <div className="overflow-hidden border-y bg-card md:rounded-xl md:border"><div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/30 py-3 md:px-4"><div className="space-y-2"><Skeleton className="h-4 w-44" /><Skeleton className="h-3 w-56 max-w-full" /></div><Skeleton className="h-9 w-48 max-w-full" /></div><LoadingTable columns={["w-40", "w-32", "w-20", "w-24", "w-28"]} /></div>
                <Card className="border-orange-200 bg-orange-50/40 dark:border-orange-900 dark:bg-orange-950/10"><CardContent className="grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }, (_, field) => <Skeleton className="h-10 w-full" key={field} />)}</CardContent></Card>
              </CardContent>}
            </Card>
          ))}
        </LoadingSection>
      )}

      {view === "billing" && (
        <LoadingSection title="Billing & invoices">
          <div className="grid items-start gap-3 lg:grid-cols-[320px_minmax(0,1fr)]">
            <Skeleton className="h-[202px] w-full max-w-[320px] rounded-xl" />
            <Card className="max-w-2xl"><CardContent className="space-y-4 p-4"><Skeleton className="h-5 w-48" /><div className="grid gap-2 sm:grid-cols-2"><Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-full" /></div></CardContent></Card>
          </div>
          <Card><CardHeader className="flex flex-row items-center justify-between"><Skeleton className="h-5 w-24" /><Skeleton className="h-9 w-48 max-w-full" /></CardHeader><CardContent className="px-0"><LoadingTable columns={["w-32", "w-24", "w-20", "w-20", "w-24"]} /></CardContent></Card>
          <Card><CardHeader><Skeleton className="h-5 w-36" /></CardHeader><CardContent><LoadingTable columns={["w-24", "w-40", "w-20", "w-24"]} /></CardContent></Card>
          <Card><CardHeader><Skeleton className="h-5 w-40" /></CardHeader><CardContent className="space-y-3">{Array.from({ length: 2 }, (_, index) => <div className="flex items-center gap-3" key={index}><Skeleton className="size-8 rounded-lg" /><Skeleton className="h-10 flex-1" /><Skeleton className="h-8 w-24" /></div>)}</CardContent></Card>
        </LoadingSection>
      )}

      {view === "activity" && (
        <LoadingSection title="Notifications & activity" description="Follow recent service changes and provisioning requests.">
          <div className="grid gap-4 lg:grid-cols-2">
            {["w-44", "w-48"].map((title, index) => <Card key={index}><CardHeader><Skeleton className={`h-5 ${title}`} /><Skeleton className="h-4 w-64 max-w-full" /></CardHeader><CardContent className="space-y-4">{Array.from({ length: 4 }, (_, row) => <div className="flex items-center justify-between gap-3 border-b pb-3" key={row}><div className="flex-1 space-y-2"><Skeleton className="h-4 w-40 max-w-full" /><Skeleton className="h-3 w-28" /></div><Skeleton className="h-6 w-20 rounded-full" /></div>)}</CardContent></Card>)}
          </div>
        </LoadingSection>
      )}

      {view === "account" && (
        <LoadingSection title="Personal details & business" description="Keep the contact details on your TechInn account up to date.">
          <div className="grid gap-4 xl:grid-cols-2">
            <Card><CardHeader><Skeleton className="h-5 w-52 max-w-full" /><Skeleton className="h-4 w-full" /></CardHeader><CardContent className="grid gap-4 sm:grid-cols-2">{Array.from({ length: 5 }, (_, index) => <Skeleton className={`h-10 w-full ${index === 2 ? "sm:col-span-2" : ""}`} key={index} />)}<Skeleton className="h-10 w-36 sm:col-span-2" /></CardContent></Card>
            <Card><CardHeader><Skeleton className="h-5 w-40" /><Skeleton className="h-4 w-full" /></CardHeader><CardContent className="space-y-4">{Array.from({ length: 3 }, (_, index) => <Skeleton className="h-10 w-full" key={index} />)}<Skeleton className="h-10 w-36" /></CardContent></Card>
          </div>
        </LoadingSection>
      )}

      {view === "services" && (
        <LoadingSection title="My services"><Skeleton className="h-64 w-full rounded-lg" /></LoadingSection>
      )}

      {view === "connections" && (
        <LoadingSection title="Provider connections" description="Connect your Cloudflare account or use a TechInn-managed connection when available.">
          <Card><CardHeader><Skeleton className="h-5 w-32" /><Skeleton className="h-4 w-full" /></CardHeader><CardContent className="space-y-4"><div className="flex gap-3"><Skeleton className="h-10 flex-1" /><Skeleton className="h-10 w-36" /></div><Skeleton className="h-9 w-48" /><Skeleton className="h-4 w-full" /></CardContent></Card>
        </LoadingSection>
      )}

      {view === "team" && (
        <LoadingSection title="Service team" description="Grant another registered TechInn customer access to a service.">
          {Array.from({ length: 2 }, (_, index) => <Card key={index}><CardHeader><Skeleton className="h-5 w-40" /></CardHeader><CardContent className="grid gap-2 sm:grid-cols-[1fr_180px_auto]"><Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-36" /></CardContent></Card>)}
        </LoadingSection>
      )}

      {!["services", "overview", "web", "analytics", "domains", "email", "billing", "activity", "account", "connections", "team"].includes(view) && (
        <LoadingSection title="Customer portal"><div className="grid gap-4 sm:grid-cols-2"><Skeleton className="h-32 w-full" /><Skeleton className="h-32 w-full" /></div></LoadingSection>
      )}
    </div>
  )
}

function LoadingSection({
  children,
  description,
  image,
  title,
}: {
  children: React.ReactNode
  description?: string
  image?: string
  title: string
}) {
  return (
    <section className="min-w-0 space-y-4">
      <SectionHeading description={description} image={image} title={title} />
      {children}
    </section>
  )
}

function LoadingTable({ columns }: { columns: string[] }) {
  return (
    <div aria-hidden="true" className="min-w-0 overflow-x-auto">
      <div className="min-w-[580px]">
        <div className="flex gap-4 border-b bg-muted/20 px-4 py-3">
          {columns.map((width, index) => <Skeleton className={`h-4 ${width} ${index === columns.length - 1 ? "ml-auto" : ""}`} key={index} />)}
        </div>
        {Array.from({ length: 3 }, (_, row) => <div className="flex items-center gap-4 border-b px-4 py-4 last:border-0" key={row}>
          {columns.map((width, index) => <Skeleton className={`h-4 ${index === 0 ? width : index === columns.length - 1 ? "ml-auto h-6 w-16" : width}`} key={index} />)}
        </div>)}
      </div>
    </div>
  )
}

function SectionHeading({
  title,
  description,
  image,
  helpHref,
}: {
  title: string
  description?: string
  image?: string
  helpHref?: string
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3">
        {image && (
          <span className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-orange-200 bg-white p-1.5 dark:border-orange-900">
            <Image alt="" className="size-full object-contain" height={48} src={image} width={48} />
          </span>
        )}
        <div>
          <h3 className="text-lg font-semibold">{title}</h3>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      {helpHref && (
        <Button asChild aria-label={`How-to guide for ${title}`} className="shrink-0 text-orange-700 dark:text-orange-300" size="sm" variant="ghost">
          <Link href={helpHref}><CircleHelp className="size-4" /><span className="hidden sm:inline">How-to</span></Link>
        </Button>
      )}
    </div>
  )
}

function EmptyAction({ href, action }: { href: string; action: string }) {
  return (
    <div className="flex flex-wrap justify-end">
      <Button asChild variant="outline"><Link href={href}><ArrowUpRight className="size-4" />{action}</Link></Button>
    </div>
  )
}

function EmptyCard({ message, href, action }: { message: string; href: string; action: string }) {
  return (
    <Card><CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
      <p className="text-sm text-muted-foreground">{message}</p>
      <Button asChild variant="outline"><a href={href}><Check className="size-4" />{action}</a></Button>
    </CardContent></Card>
  )
}

function QuickAction({
  href,
  icon,
  title,
  description,
}: {
  href: string
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <a
      className="group flex items-start gap-3 rounded-lg border p-4 transition-colors hover:border-amber-500/40 hover:bg-amber-500/5"
      href={href}
    >
      <span className="rounded-md bg-amber-500/10 p-2 text-amber-700 dark:text-amber-400">{icon}</span>
      <span className="space-y-1">
        <span className="block font-medium group-hover:text-amber-700 dark:group-hover:text-amber-400">{title}</span>
        <span className="block text-sm text-muted-foreground">{description}</span>
      </span>
    </a>
  )
}
