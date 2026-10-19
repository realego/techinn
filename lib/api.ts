const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1").replace(/\/$/, "")
const sessionKey = "techinn-api-session"
const authChangedEvent = "techinn-api-auth-change"
export const sessionIdleMs = 6 * 60 * 60 * 1000

export interface CustomerProfile {
  uuid: string
  first_name: string
  last_name: string
  email: string
  phone: string
  company_name: string
  billing_address?: Partial<Record<"line1" | "line2" | "city" | "region" | "postal_code" | "country", string>>
  postal_address?: Partial<Record<"line1" | "line2" | "city" | "region" | "postal_code" | "country", string>>
  notification_preferences?: { service_updates?: boolean; billing_reminders?: boolean; product_news?: boolean }
  test_checkout_enabled: boolean
  has_usable_password?: boolean
}

export interface ApiSession {
  lastActiveAt?: number
  access: string
  refresh: string
  customer: CustomerProfile
}

export interface CheckoutPayment {
  uuid: string
  status: "pending" | "processing" | "successful" | "failed" | "cancelled" | "expired" | "refunded"
  message: string
  amount: string
  currency: string
  order_uuid: string | null
  order_number: string | null
  redirect_url: string
}

export interface CheckoutPayload {
  checkout_key: string
  payment_method: "ecocash" | "onemoney" | "card"
  displayed_total: string
  phone: string
  payment_phone: string
  items: {
    product_id: string
    quantity: number
    options: Record<string, string>
    domain_name?: string
  }[]
  details: Record<string, string>
  attribution: Record<string, string>
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

function readSession(): ApiSession | null {
  if (typeof window === "undefined") return null
  const raw = window.localStorage.getItem(sessionKey) ?? window.sessionStorage.getItem(sessionKey)
  if (!raw) return null
  try {
    const session = JSON.parse(raw) as ApiSession
    session.lastActiveAt ??= Date.now()
    if (Date.now() - session.lastActiveAt >= sessionIdleMs) {
      window.localStorage.removeItem(sessionKey)
      window.sessionStorage.removeItem(sessionKey)
      queueMicrotask(() => window.dispatchEvent(new Event(authChangedEvent)))
      return null
    }
    if (!window.localStorage.getItem(sessionKey)) {
      window.localStorage.setItem(sessionKey, JSON.stringify(session))
      window.sessionStorage.removeItem(sessionKey)
    }
    return session
  } catch {
    window.localStorage.removeItem(sessionKey)
    window.sessionStorage.removeItem(sessionKey)
    return null
  }
}

export function getAccessToken() {
  return readSession()?.access ?? null
}

export function getApiSession() {
  return readSession()
}

export function saveApiSession(session: ApiSession) {
  window.localStorage.setItem(sessionKey, JSON.stringify({ ...session, lastActiveAt: session.lastActiveAt ?? Date.now() }))
  window.sessionStorage.removeItem(sessionKey)
  window.dispatchEvent(new Event(authChangedEvent))
}

export function touchApiSession() {
  const session = readSession()
  if (!session) return false
  window.localStorage.setItem(sessionKey, JSON.stringify({ ...session, lastActiveAt: Date.now() }))
  return true
}

export function clearApiSession() {
  window.localStorage.removeItem(sessionKey)
  window.sessionStorage.removeItem(sessionKey)
  window.dispatchEvent(new Event(authChangedEvent))
}

async function responseError(response: Response) {
  const data = await response.json().catch(() => null)
  if (data && typeof data === "object") {
    const detail = "detail" in data ? data.detail : null
    if (typeof detail === "string") return detail
    const messages = Object.values(data)
      .flatMap((value) => Array.isArray(value) ? value : [value])
      .filter((value): value is string => typeof value === "string")
    if (messages.length) return messages.join(" ")
  }
  return `The request failed (${response.status}).`
}

let pendingRefresh: Promise<boolean> | null = null

async function refreshAccessToken() {
  if (!pendingRefresh) pendingRefresh = performTokenRefresh().finally(() => { pendingRefresh = null })
  return pendingRefresh
}

async function performTokenRefresh() {
  const session = readSession()
  if (!session?.refresh) return false
  const response = await fetch(`${apiBaseUrl}/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: session.refresh }),
    cache: "no-store",
  })
  if (!response.ok) {
    clearApiSession()
    return false
  }
  const tokens = await response.json() as { access: string; refresh?: string }
  const current = readSession()
  if (!current || current.refresh !== session.refresh) return Boolean(current)
  saveApiSession({
    ...current,
    access: tokens.access,
    refresh: tokens.refresh ?? session.refresh,
  })
  return true
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  options: { authenticated?: boolean; retryAuth?: boolean } = {},
): Promise<T> {
  const authenticated = options.authenticated ?? true
  const headers = new Headers(init.headers)
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")
  if (authenticated) {
    const access = getAccessToken()
    if (access) headers.set("Authorization", `Bearer ${access}`)
  }
  let response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
    cache: init.cache ?? "no-store",
  })
  if (response.status === 401 && authenticated && options.retryAuth !== false) {
    if (await refreshAccessToken()) {
      const access = getAccessToken()
      if (access) headers.set("Authorization", `Bearer ${access}`)
      response = await fetch(`${apiBaseUrl}${path}`, {
        ...init,
        headers,
        cache: init.cache ?? "no-store",
      })
    } else {
      clearApiSession()
    }
  }
  if (!response.ok) throw new ApiError(await responseError(response), response.status)
  if (response.status === 204) return undefined as T
  const body = await response.text()
  if (!body.trim()) return undefined as T
  try {
    return JSON.parse(body) as T
  } catch {
    throw new ApiError("The server returned an unreadable response. Refresh to check the latest status.", response.status)
  }
}

export function createCheckoutPayment(payload: CheckoutPayload) {
  return apiRequest<CheckoutPayment>("/billing/checkout/", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function pollCheckoutPayment(paymentUuid: string) {
  return apiRequest<CheckoutPayment>(`/billing/payments/${encodeURIComponent(paymentUuid)}/poll/`, {
    method: "POST",
  })
}

export function cancelCheckoutPayment(paymentUuid: string) {
  return apiRequest<CheckoutPayment>(`/billing/payments/${encodeURIComponent(paymentUuid)}/cancel/`, {
    method: "POST",
  })
}

export { authChangedEvent }
