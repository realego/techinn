"use client"

import { useSyncExternalStore } from "react"

import {
  apiRequest,
  authChangedEvent,
  clearApiSession,
  getApiSession,
  saveApiSession,
} from "@/lib/api"

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange)
  window.addEventListener(authChangedEvent, onChange)
  return () => {
    window.removeEventListener("storage", onChange)
    window.removeEventListener(authChangedEvent, onChange)
  }
}

function getSignedInSnapshot() {
  return Boolean(getApiSession()?.access)
}

function getCustomerSnapshot() {
  if (typeof window === "undefined") return null
  return getApiSession() ? window.localStorage.getItem("techinn-api-session") : null
}

export function useSignedIn() {
  return useSyncExternalStore(subscribe, getSignedInSnapshot, () => false)
}

export function useCustomerProfile() {
  const rawSession = useSyncExternalStore(
    subscribe,
    getCustomerSnapshot,
    () => null,
  )
  if (!rawSession) return null
  try {
    return (JSON.parse(rawSession) as ReturnType<typeof getApiSession>)?.customer ?? null
  } catch {
    return null
  }
}

export async function signIn(email: string, password: string) {
  const tokens = await apiRequest<{ access: string; refresh: string }>(
    "/auth/token/",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    },
    { authenticated: false },
  )
  saveApiSession({ ...tokens, customer: { uuid: "", first_name: "", last_name: "", email, phone: "", company_name: "", test_checkout_enabled: false } })
  try {
    const customer = await apiRequest<NonNullable<ReturnType<typeof getApiSession>>["customer"]>(
      "/auth/me/",
    )
    const session = getApiSession()
    if (session) saveApiSession({ ...session, customer })
    return customer
  } catch (error) {
    clearApiSession()
    throw error
  }
}

export async function signInWithGoogle(credential: string) {
  const tokens = await apiRequest<{ access: string; refresh: string }>(
    "/auth/google/",
    { method: "POST", body: JSON.stringify({ credential }) },
    { authenticated: false },
  )
  saveApiSession({
    ...tokens,
    customer: { uuid: "", first_name: "", last_name: "", email: "", phone: "", company_name: "", test_checkout_enabled: false },
  })
  try {
    const customer = await apiRequest<NonNullable<ReturnType<typeof getApiSession>>["customer"]>("/auth/me/")
    const session = getApiSession()
    if (session) saveApiSession({ ...session, customer })
    return customer
  } catch (error) {
    clearApiSession()
    throw error
  }
}

export async function registerCustomer(input: {
  first_name: string
  last_name?: string
  email: string
  password: string
}) {
  await apiRequest("/auth/register/", {
    method: "POST",
    body: JSON.stringify(input),
  }, { authenticated: false })
  return signIn(input.email, input.password)
}

export async function requestPasswordReset(email: string) {
  return apiRequest<{ detail: string }>(
    "/auth/password/reset/",
    { method: "POST", body: JSON.stringify({ email }) },
    { authenticated: false },
  )
}

export async function confirmPasswordReset(input: { uid: string; token: string; new_password: string }) {
  return apiRequest<{ detail: string }>(
    "/auth/password/reset/confirm/",
    { method: "POST", body: JSON.stringify(input) },
    { authenticated: false },
  )
}

export function signOut() {
  void apiRequest("/auth/logout/", { method: "POST" }, { retryAuth: false }).catch(() => {})
  clearApiSession()
}
