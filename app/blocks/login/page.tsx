"use client"

import { useRouter } from "next/navigation"
import { useEffect } from "react"

export default function LegacyLoginPage() {
  const router = useRouter()
  useEffect(() => { router.replace("/login/" + window.location.search) }, [router])
  return <p className="p-8 text-center">Opening sign in…</p>
}
