"use client";

import { BriefcaseBusiness, Mail, Rocket, Server, UserRound, UsersRound } from "lucide-react";
import { type ReactNode, useState } from "react";

import { emailHostingPlans, type HostingService,planSelectionHref, webHostingPlans } from "@/config/hosting-plans";
import { cn } from "@/lib/utils";

import { Button } from "../../ui/button";
import { PricingColumn } from "../../ui/pricing-column";
import { Section } from "../../ui/section";

interface PricingProps {
  service?: HostingService;
  title?: ReactNode;
  description?: string;
  className?: string;
}

const webIcons = [
  <Server key="basic" className="size-4" />,
  <Rocket key="growth" className="size-4" />,
  <BriefcaseBusiness key="business" className="size-4" />,
];
const emailIcons = [
  <Mail key="essential" className="size-4" />,
  <UsersRound key="team" className="size-4" />,
  <UserRound key="business-mail" className="size-4" />,
];

export default function Pricing({
  service = "web",
  title = service === "web"
    ? <>Hosting plans for <span className="text-orange-600 dark:text-orange-400">every next step.</span></>
    : <><span className="text-orange-600 dark:text-orange-400">Professional email</span> for every team.</>,
  description = service === "web"
    ? "Start with 2 GB of storage and unlimited email accounts, then grow when your website does."
    : "Use your domain for business email and pick the mailbox space that suits your work.",
  className,
}: PricingProps) {
  const [billing, setBilling] = useState<"monthly" | "yearly">(service === "email" ? "yearly" : "monthly");
  const plans = service === "web" ? webHostingPlans : emailHostingPlans;
  const icons = service === "web" ? webIcons : emailIcons;
  const priceUnit = service === "email" ? "per year" : "per month";

  return (
    <Section id={service === "web" ? "web-plans" : "email-plans"} className={cn("scroll-mt-24", className)}>
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-10 sm:gap-12">
        <div className="flex flex-col items-center gap-4 px-4 text-center sm:gap-6">
          <h2 className="text-3xl leading-tight font-semibold sm:text-5xl sm:leading-tight">{title}</h2>
          <p className="text-md text-muted-foreground max-w-[640px] font-medium sm:text-xl">{description}</p>
          {service === "web" && <div className="bg-muted/60 mt-2 flex items-center gap-1 rounded-full border p-1" aria-label="Billing period">
            <Button size="sm" variant={billing === "monthly" ? "default" : "ghost"} aria-pressed={billing === "monthly"} onClick={() => setBilling("monthly")}>Monthly</Button>
            <Button size="sm" variant={billing === "yearly" ? "default" : "ghost"} aria-pressed={billing === "yearly"} onClick={() => setBilling("yearly")}>Yearly <span className="ml-1 text-xs">Save 10%</span></Button>
          </div>}
        </div>
        <div className="max-w-container mx-auto grid w-full grid-cols-1 gap-8 md:grid-cols-3">
          {plans.map((plan, index) => {
            const shownPrice = billing === "yearly" && service === "web" ? plan.price * 0.9 : plan.price;
            const annualTotal = service === "email" ? plan.price : plan.price * 12 * 0.9;
            return (
              <PricingColumn
                key={plan.id}
                name={plan.name}
                icon={icons[index]}
                description={plan.description}
                price={shownPrice}
                priceUnit={priceUnit}
                priceNote={billing === "yearly"
                  ? "Billed $" + annualTotal.toFixed(2) + " yearly" + (service === "email" ? ". Annual plan only." : ". Save 10%.")
                  : "Billed $" + plan.price.toFixed(2) + " monthly" + (service === "email" ? " per mailbox" : "") + "."}
                cta={{
                  variant: plan.variant === "default" ? "glow" : "default",
                  label: "Choose " + plan.name,
                  href: planSelectionHref(service, plan.id, billing),
                }}
                features={plan.features}
                variant={plan.variant}
              />
            );
          })}
        </div>
        <p className="text-muted-foreground text-center text-xs">Prices are shown in USD. The selected plan, billing period, and included features are confirmed at checkout.</p>
      </div>
    </Section>
  );
}
