"use client";

import { ArrowRight, Globe2, Mail } from "lucide-react";
import Link from "next/link";

import { emailHostingPlans, type HostingPlan, type HostingService,planSelectionHref, webHostingPlans } from "@/config/hosting-plans";

import { Button } from "./button";
import {
  NavigationMenu,
  NavigationMenuContent,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  NavigationMenuTrigger,
  navigationMenuTriggerStyle,
} from "./navigation-menu";

function MiniPlansMenu({ service }: { service: HostingService }) {
  const isWeb = service === "web";
  const plans = isWeb ? webHostingPlans : emailHostingPlans;
  const pageHref = "/shop/?service=" + service;

  return (
    <div className="grid w-[640px] grid-cols-[210px_1fr] gap-3 p-3">
      <NavigationMenuLink asChild>
        <Link
          href={pageHref}
          className="from-muted/30 to-muted/10 flex min-h-full flex-col justify-end rounded-md bg-linear-to-b p-5 no-underline outline-hidden"
        >
          {isWeb ? <Globe2 className="text-brand size-6" /> : <Mail className="text-brand size-6" />}
          <span className="mt-5 text-lg font-semibold">{isWeb ? "Web Hosting" : "Email Hosting"}</span>
          <span className="text-muted-foreground mt-2 text-sm leading-relaxed">
            {isWeb ? "Find the right space for your website and email." : "Give your team a professional address on your domain."}
          </span>
          <span className="mt-5 flex items-center gap-1 text-sm font-medium">
            View all plans <ArrowRight className="size-4" />
          </span>
        </Link>
      </NavigationMenuLink>
      <div className="flex flex-col gap-1">
        {plans.map((plan: HostingPlan) => (
          <div key={plan.id} className="hover:bg-accent/60 flex items-center justify-between gap-4 rounded-md p-3 transition-colors">
            <div className="min-w-0">
              <Link href={planSelectionHref(service, plan.id)} className="block text-sm font-semibold hover:underline">{plan.name}</Link>
              <p className="text-muted-foreground mt-1 line-clamp-1 text-xs">{plan.description}</p>
              <p className="mt-1 text-xs font-medium">
                ${plan.price.toFixed(2)} <span className="text-muted-foreground font-normal">/ {isWeb ? "month" : "mailbox / month"}</span>
              </p>
            </div>
            <Button asChild size="sm" variant={plan.variant === "glow-brand" ? "default" : "outline"}>
              <Link href={planSelectionHref(service, plan.id)}>Choose</Link>
            </Button>
          </div>
        ))}
        <p className="text-muted-foreground px-3 pt-1 text-[11px]">Working prices in USD · checkout preview</p>
      </div>
    </div>
  );
}

export default function Navigation() {
  return (
    <NavigationMenu className="hidden lg:flex">
      <NavigationMenuList>
        <NavigationMenuItem>
          <NavigationMenuTrigger>Web Hosting</NavigationMenuTrigger>
          <NavigationMenuContent><MiniPlansMenu service="web" /></NavigationMenuContent>
        </NavigationMenuItem>
        <NavigationMenuItem>
          <NavigationMenuTrigger>Email Hosting</NavigationMenuTrigger>
          <NavigationMenuContent><MiniPlansMenu service="email" /></NavigationMenuContent>
        </NavigationMenuItem>
        <NavigationMenuItem>
          <NavigationMenuLink className={navigationMenuTriggerStyle()} asChild>
            <Link href="/domains/">Domains</Link>
          </NavigationMenuLink>
        </NavigationMenuItem>
        <NavigationMenuItem>
          <NavigationMenuLink className={navigationMenuTriggerStyle()} asChild>
            <Link href="/shop/">Shop</Link>
          </NavigationMenuLink>
        </NavigationMenuItem>
        <NavigationMenuItem>
          <NavigationMenuLink className={navigationMenuTriggerStyle()} asChild>
            <Link href="/how-to/">How to</Link>
          </NavigationMenuLink>
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
  );
}
