"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function ServiceShopRedirect({ service }: { service: "web" | "email" }) {
  const router = useRouter();
  const href = "/shop/?service=" + service;
  useEffect(() => { router.replace(href); }, [router, href]);
  return <main className="p-8 text-center"><Link href={href}>View {service === "web" ? "web hosting" : "email hosting"} in the shop →</Link></main>;
}
