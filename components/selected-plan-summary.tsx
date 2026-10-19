"use client";

import { useSyncExternalStore } from "react";

import { emailHostingPlans, webHostingPlans, websitePlans } from "@/config/hosting-plans";

const subscribe = () => () => {};

export function SelectedPlanSummary() {
  const search = useSyncExternalStore(subscribe, () => window.location.search, () => "");
  const params = new URLSearchParams(search);
  const service = params.get("service");
  const planId = params.get("plan");
  const plans = service === "web"
    ? webHostingPlans
    : service === "email"
      ? emailHostingPlans
      : service === "website"
        ? websitePlans
        : [];
  const plan = plans.find((item) => item.id === planId);
  if (!plan || (service !== "web" && service !== "email" && service !== "website")) return null;
  return (
    <div className="bg-card rounded-xl border p-4 shadow-sm">
      <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide">Selected plan</p>
      <div className="mt-2 flex items-baseline justify-between gap-3">
        <strong>{plan.name} {service === "website" ? "Website Design" : service === "web" ? "Web Hosting" : "Email Hosting"}</strong>
        <span className="shrink-0 text-sm font-medium">
          ${plan.price.toFixed(2)}{plan.billing === "project" ? " one time" : plan.billing === "yearly" ? "/yr" : "/mo"}
        </span>
      </div>
      <a href={"/shop/?service=" + service} className="text-muted-foreground mt-2 inline-block text-xs underline underline-offset-2">
        Change plan
      </a>
    </div>
  );
}
