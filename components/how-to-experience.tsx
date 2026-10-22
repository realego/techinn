"use client";

import {
  ArrowRight,
  BookOpen,
  ChevronRight,
  CircleHelp,
  Menu,
  Play,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { type HowToGuide,howToGuides } from "@/config/how-to-guides";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./ui/sheet";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from "./ui/sidebar";
import Image from "next/image";

type GuideScreenshot = {
  file: string;
  alt: string;
  caption: string;
};

const guideScreenshots: Record<string, GuideScreenshot[]> = {
  "getting-started": [
    { file: "techinn-howto-getting-started.jpg", alt: "TechInn getting started guide view", caption: "Start with the service that matches your next step." },
    { file: "techinn-home.jpg", alt: "TechInn home page services", caption: "The home page brings domains, hosting, email, and website services together." },
  ],
  domains: [
    { file: "techinn-domains-dashboard.jpg", alt: "TechInn domains dashboard", caption: "Review domains and their current status in the dashboard." },
    { file: "techinn-domain-active.jpg", alt: "TechInn active domain status", caption: "An active domain is ready for its connected services." },
    { file: "techinn-domain-unavailable.jpg", alt: "TechInn unavailable domain result", caption: "Unavailable names are clearly marked before checkout." },
  ],
  "web-hosting": [
    { file: "techinn-web-hosting.jpg", alt: "TechInn web hosting plans", caption: "Compare storage, billing, and hosting features." },
    { file: "techinn-desktop-shop.jpg", alt: "TechInn desktop shop", caption: "Add hosting and optional features from the shop." },
  ],
  "business-email": [
    { file: "techinn-email-plans.jpg", alt: "TechInn business email plans", caption: "Choose mailbox capacity and storage for your team." },
    { file: "techinn-email-dashboard.jpg", alt: "TechInn email dashboard", caption: "Select a domain and manage mailbox setup from Email." },
    { file: "techinn-mailbox-management.jpg", alt: "TechInn mailbox management", caption: "Manage mailbox addresses, passwords, and quotas." },
  ],
  "dashboard-domain-email": [
    { file: "techinn-sidebar-annotated.png", alt: "Annotated TechInn dashboard navigation", caption: "Use the dashboard navigation to move between domains, DNS, hosting, and email." },
    { file: "techinn-dns-controls.jpg", alt: "TechInn DNS record controls", caption: "Review and edit DNS records in the domain workspace." },
    { file: "techinn-mailbox-management.jpg", alt: "TechInn mailbox management controls", caption: "Create and manage mailboxes after the domain is ready." },
  ],
  "website-design": [
    { file: "techinn-home.jpg", alt: "TechInn website services on the home page", caption: "Website services start from the main service catalogue." },
    { file: "techinn-desktop-shop.jpg", alt: "TechInn website service shop", caption: "Review website services and add-ons before checkout." },
  ],
  checkout: [
    { file: "techinn-cart-two-services.jpg", alt: "TechInn cart with two services", caption: "Check that each domain and service is listed separately." },
    { file: "techinn-checkout-filled-demo.jpg", alt: "TechInn checkout details form", caption: "Complete the required customer and domain details." },
    { file: "techinn-checkout-payment-methods.jpg", alt: "TechInn checkout payment methods", caption: "Choose the payment method shown for your order." },
  ],
  "account-dashboard": [
    { file: "techinn-dashboard-sidebar.jpg", alt: "TechInn customer dashboard sidebar", caption: "The dashboard sidebar keeps your services and account areas together." },
    { file: "techinn-desktop-dashboard.jpg", alt: "TechInn desktop customer dashboard", caption: "See service status and actions from the customer dashboard." },
  ],
  "team-access-roles": [
    { file: "techinn-account-security.jpg", alt: "TechInn account security settings", caption: "Review account and team access controls securely." },
    { file: "techinn-dashboard-sidebar.jpg", alt: "TechInn dashboard navigation", caption: "Use the dashboard navigation to reach service permissions." },
  ],
  "billing-payments": [
    { file: "techinn-payment-options.jpg", alt: "TechInn payment options", caption: "Review the available payment methods before submitting." },
    { file: "techinn-checkout-payment-annotated.png", alt: "Annotated TechInn checkout payment area", caption: "Confirm the amount and payment reference in the payment panel." },
    { file: "techinn-billing.jpg", alt: "TechInn billing dashboard", caption: "Billing keeps invoices, payments, and balances together." },
  ],
  "billing-renewals": [
    { file: "techinn-billing.jpg", alt: "TechInn billing and renewals", caption: "Find services due for renewal in Billing." },
    { file: "techinn-deposit-form.jpg", alt: "TechInn deposit form", caption: "Add a balance deposit and review its service note." },
  ],
  "hosting-file-manager": [
    { file: "techinn-desktop-dashboard.jpg", alt: "TechInn hosting dashboard", caption: "Open hosting actions from the Web & Hosting service area." },
    { file: "techinn-dashboard-sidebar.jpg", alt: "TechInn dashboard hosting navigation", caption: "Use the sidebar to return to hosting services." },
  ],
  "account-security-notifications": [
    { file: "techinn-account-security.jpg", alt: "TechInn account security page", caption: "Manage password, verification, and account security settings." },
  ],
  "notifications-activity": [
    { file: "techinn-dashboard-sidebar.jpg", alt: "TechInn dashboard activity navigation", caption: "Open account areas from the customer dashboard." },
    { file: "techinn-billing.jpg", alt: "TechInn account activity and billing", caption: "Review service and billing activity as it is recorded." },
  ],
  "mailbox-management": [
    { file: "techinn-email-dashboard.jpg", alt: "TechInn email service dashboard", caption: "Choose the email service and domain you want to manage." },
    { file: "techinn-mailbox-management.jpg", alt: "TechInn mailbox controls", caption: "Create, resize, reset, and remove mailboxes from one workspace." },
  ],
  "hosting-storage-addon": [
    { file: "techinn-web-hosting.jpg", alt: "TechInn hosting plan storage options", caption: "Compare included hosting storage before choosing an add-on." },
    { file: "techinn-desktop-shop.jpg", alt: "TechInn shop hosting add-ons", caption: "Select recurring hosting extras from the service options." },
  ],
  "domain-connection-methods": [
    { file: "techinn-domains-dashboard.jpg", alt: "TechInn domain connection dashboard", caption: "Start domain connection from Domains & DNS." },
    { file: "techinn-dns-controls.jpg", alt: "TechInn DNS connection controls", caption: "Review the DNS records after connecting a domain." },
  ],
  "pending-domain-preview": [
    { file: "techinn-domain-active.jpg", alt: "TechInn domain activation status", caption: "A pending domain changes to active after registry confirmation." },
    { file: "techinn-desktop-dashboard.jpg", alt: "TechInn service preview dashboard", caption: "Use the dashboard preview while a domain is processing." },
  ],
  "service-expiry-suspension": [
    { file: "techinn-billing.jpg", alt: "TechInn service billing status", caption: "Billing shows service periods, renewals, and payment status." },
  ],
  "analytics-usage": [
    { file: "techinn-desktop-dashboard.jpg", alt: "TechInn customer dashboard usage view", caption: "Review service activity and resource information in the dashboard." },
  ],
};

function GuideScreenshots({ guide }: { guide: HowToGuide }) {
  const screenshots = guideScreenshots[guide.id];
  if (!screenshots?.length) return null;
  return (
    <section className="mt-8" aria-labelledby={`${guide.id}-screenshots`}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 id={`${guide.id}-screenshots`} className="text-lg font-semibold tracking-tight">See it in TechInn</h2>
        <span className="text-xs text-muted-foreground">Screenshots from the customer portal</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {screenshots.map((screenshot) => (
          <figure key={screenshot.file} className="overflow-hidden rounded-lg border bg-muted/10">
            <div className="relative aspect-[4/3] bg-muted/20">
              <Image src={`/how-to/${screenshot.file}`} alt={screenshot.alt} fill sizes="(min-width: 1024px) 30vw, (min-width: 640px) 45vw, 90vw" className="object-contain p-1" unoptimized />
            </div>
            <figcaption className="border-t px-3 py-2 text-xs leading-5 text-muted-foreground">{screenshot.caption}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

function searchableText(guide: HowToGuide) {
  return [
    guide.category,
    guide.title,
    guide.summary,
    guide.answer,
    guide.example,
    ...guide.steps.flatMap((step) => [step.title, step.description]),
    ...guide.faqs.flatMap((faq) => [faq.question, faq.answer]),
  ].join(" ").toLowerCase();
}

function searchGuideScore(guide: HowToGuide, query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return 1;
  const title = guide.title.toLowerCase();
  const category = guide.category.toLowerCase();
  const summary = guide.summary.toLowerCase();
  const content = searchableText(guide);
  const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
  let score = title.includes(normalizedQuery) ? 140 : 0;
  if (category.includes(normalizedQuery)) score += 110;
  if (summary.includes(normalizedQuery)) score += 60;
  for (const token of tokens) {
    if (title.includes(token)) score += 45;
    else if (category.includes(token)) score += 40;
    else if (summary.includes(token)) score += 25;
    else if (content.includes(token)) score += 8;
    else return 0;
  }
  return score;
}

function searchGuides(query: string) {
  return howToGuides
    .map((guide, index) => ({ guide, index, score: searchGuideScore(guide, query) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map(({ guide }) => guide);
}

function GuideNavigation({
  query,
  activeId,
}: {
  query: string;
  activeId: string;
}) {
  const visibleGuides = searchGuides(query);
  const categories = [...new Set(visibleGuides.map((guide) => guide.category))];

  return (
    <Sidebar collapsible="none" className="h-full w-full bg-transparent">
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="border-b border-border/70 px-3 pb-2 text-xs font-semibold uppercase tracking-[0.12em] text-foreground">
            Browse guides
          </SidebarGroupLabel>
          {categories.length === 0 ? (
            <p className="text-muted-foreground px-2 py-3 text-sm">No guides match your search.</p>
          ) : categories.map((category) => (
            <SidebarGroup key={category}>
              <SidebarGroupLabel className="mt-2 border-b border-orange-500/30 px-3 pb-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-orange-600 dark:text-orange-400">
                {category}
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {visibleGuides.filter((guide) => guide.category === category).map((guide) => (
                    <SidebarMenuItem key={guide.id}>
                      <SidebarMenuButton
                        asChild
                        isActive={activeId === guide.id}
                        className="h-auto min-h-9 whitespace-normal border-l-2 border-transparent py-2 text-left transition-colors hover:border-orange-400 hover:bg-orange-500/10 data-[active=true]:border-orange-500 data-[active=true]:bg-orange-500/10 data-[active=true]:font-semibold"
                      >
                        <Link href={`/how-to/${guide.id}/`}>
                          <span className="line-clamp-2">{guide.title}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}

function VideoSection({ guide }: { guide: HowToGuide }) {
    return (
    <section aria-labelledby={`${guide.id}-video-title`} className="mt-10">
      <h2 id={`${guide.id}-video-title`} className="mb-3 flex items-center gap-2 text-lg font-semibold tracking-tight">
        <Play aria-hidden="true" className="text-brand size-4" />
        Video guide
      </h2>
      {guide.videoUrl ? (
        <video
          controls
          preload="metadata"
          className="aspect-video w-full rounded-xl border bg-black"
          src={guide.videoUrl}
          aria-label={guide.videoTitle}
        >
          Your browser does not support embedded video.
        </video>
      ) : (
        <div className="bg-muted/20 flex aspect-video flex-col items-center justify-center rounded-xl border border-dashed px-6 text-center">
          <span className="bg-brand/10 text-brand mb-3 flex size-12 items-center justify-center rounded-full">
            <Play aria-hidden="true" className="size-5" />
          </span>
          <p className="font-medium">{guide.videoTitle}</p>
          <p className="text-muted-foreground mt-2 max-w-lg text-sm leading-relaxed">{guide.videoDescription}</p>
          <p className="text-muted-foreground mt-3 text-xs">Video coming soon</p>
        </div>
      )}
    </section>
  );
}

export function GuideArticle({ guide }: { guide: HowToGuide }) {
  return (
    <article className="min-w-0">
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{guide.category}</Badge>
        <span className="text-muted-foreground text-xs">Step-by-step guide</span>
      </div>
      <h1 className="max-w-3xl text-3xl leading-tight font-semibold tracking-tight text-balance sm:text-5xl">{guide.title}</h1>
      <p className="text-muted-foreground mt-4 max-w-3xl text-base leading-7 sm:text-lg">{guide.summary}</p>

      <section className="border-brand/30 bg-brand/5 mt-8 rounded-xl border p-5 sm:p-6" aria-labelledby={`${guide.id}-answer`}>
        <h2 id={`${guide.id}-answer`} className="text-sm font-semibold uppercase tracking-wide">Quick answer</h2>
        <p className="mt-2 text-sm leading-7 sm:text-base">{guide.answer}</p>
      </section>

      <GuideScreenshots guide={guide} />

      <section aria-labelledby={`${guide.id}-steps`} className="mt-10">
        <h2 id={`${guide.id}-steps`} className="text-xl font-semibold tracking-tight">How to do it</h2>
        <ol className="mt-5 space-y-5">
          {guide.steps.map((step, index) => (
            <li key={step.title} className="flex gap-4">
              <span className="bg-brand/10 text-brand flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold">{index + 1}</span>
              <div className="min-w-0 pt-0.5">
                <h3 className="font-semibold">{step.title}</h3>
                <p className="text-muted-foreground mt-1 text-sm leading-7">{step.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <aside className="mt-8 rounded-xl border p-5" aria-labelledby={`${guide.id}-example`}>
        <h2 id={`${guide.id}-example`} className="flex items-center gap-2 font-semibold">
          <BookOpen aria-hidden="true" className="text-brand size-4" />
          Scenario example
        </h2>
        <p className="text-muted-foreground mt-2 text-sm leading-7">{guide.example}</p>
      </aside>

      <VideoSection guide={guide} />

      <section aria-labelledby={`${guide.id}-faqs`} className="mt-10">
        <h2 id={`${guide.id}-faqs`} className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <CircleHelp aria-hidden="true" className="text-brand size-5" />
          Frequently asked questions
        </h2>
        <div className="mt-4 divide-y rounded-xl border px-4">
          {guide.faqs.map((faq) => (
            <details key={faq.question} className="group py-4">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium [&::-webkit-details-marker]:hidden">
                {faq.question}
                <ChevronRight aria-hidden="true" className="text-muted-foreground size-4 shrink-0 transition-transform group-open:rotate-90" />
              </summary>
              <p className="text-muted-foreground mt-3 max-w-3xl text-sm leading-7">{faq.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <div className="mt-10 border-t pt-6">
        <Button asChild variant="outline" className="gap-2">
          <Link href={guide.relatedHref}>{guide.relatedLabel}<ArrowRight aria-hidden="true" className="size-4" /></Link>
        </Button>
      </div>
    </article>
  );
}

export function HowToExperience() {
  const [query, setQuery] = useState("");
  const [activeId] = useState(howToGuides[0].id);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const visibleGuides = useMemo(() => searchGuides(query), [query]);
  const activeGuide = visibleGuides.find((guide) => guide.id === activeId) ?? visibleGuides[0];

  return (
    <main className="min-h-screen px-4 pb-20 pt-8 sm:pt-12">
      <div className="max-w-container mx-auto">
        <div className="mb-8">
          <p className="text-brand mb-2 text-sm font-medium">TechInn help center</p>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-5xl">How to use TechInn services</h1>
          <p className="text-muted-foreground mt-3 max-w-3xl leading-7">
            Clear, step-by-step help for domains, web hosting, business email, website design, your account, and checkout.
          </p>
        </div>
        <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="hidden lg:block">
            <div className="sticky top-24 overflow-hidden rounded-xl border bg-background">
              <div className="border-b p-3">
                <label htmlFor="how-to-search" className="sr-only">Search help guides</label>
                <div className="relative">
                  <Search aria-hidden="true" className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
                  <Input id="how-to-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search topics and guide content…" className="h-9 pl-9 text-sm" />
                </div>
                <p className="mt-2 px-1 text-[11px] text-muted-foreground">{visibleGuides.length} {visibleGuides.length === 1 ? "guide" : "guides"} found · topics rank first</p>
              </div>
              <SidebarProvider className="min-h-0">
                <GuideNavigation query={query} activeId={activeGuide?.id ?? ""} />
              </SidebarProvider>
            </div>
          </aside>
          <div className="min-w-0">
            <div className="mb-4 flex items-center gap-3 lg:hidden">
              <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
                <SheetTrigger asChild>
                  <Button type="button" variant="outline" size="sm" className="gap-2">
                    <Menu aria-hidden="true" className="size-4" />Browse guides
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="w-80 max-w-[90vw] p-0">
                  <SheetHeader className="border-b p-4 text-left">
                    <SheetTitle>How-to guides</SheetTitle>
                    <SheetDescription>Search and choose a topic.</SheetDescription>
                    <label htmlFor="how-to-search-mobile" className="sr-only">Search help guides</label>
                    <div className="relative pt-2">
                      <Search aria-hidden="true" className="text-muted-foreground absolute left-3 top-[calc(50%+4px)] size-4 -translate-y-1/2" />
                    <Input id="how-to-search-mobile" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search topics and guide content…" className="h-9 pl-9 text-sm" />
                    </div>
                  </SheetHeader>
                  <SidebarProvider className="min-h-0">
                    <GuideNavigation query={query} activeId={activeGuide?.id ?? ""} />
                  </SidebarProvider>
                </SheetContent>
              </Sheet>
              <span className="text-muted-foreground truncate text-sm">{activeGuide?.category}</span>
            </div>
            <div className="min-h-[60vh] rounded-xl border bg-background p-5 sm:p-8 lg:p-10">
              {activeGuide ? (
                <GuideArticle guide={activeGuide} />
              ) : (
                <div role="status" className="flex min-h-64 flex-col items-center justify-center text-center">
                  <Search aria-hidden="true" className="text-muted-foreground mb-3 size-6" />
                  <p className="font-medium">No guides found</p>
                  <p className="text-muted-foreground mt-1 text-sm">Try another word or clear your search.</p>
                  <Button variant="link" size="sm" onClick={() => setQuery("")}>Clear search</Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
