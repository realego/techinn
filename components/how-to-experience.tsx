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

function GuideNavigation({
  query,
  activeId,
}: {
  query: string;
  activeId: string;
}) {
  const normalizedQuery = query.trim().toLowerCase();
  const visibleGuides = howToGuides.filter((guide) => !normalizedQuery || searchableText(guide).includes(normalizedQuery));
  const categories = [...new Set(visibleGuides.map((guide) => guide.category))];

  return (
    <Sidebar collapsible="none" className="h-full w-full bg-transparent">
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Browse guides</SidebarGroupLabel>
          {categories.length === 0 ? (
            <p className="text-muted-foreground px-2 py-3 text-sm">No guides match your search.</p>
          ) : categories.map((category) => (
            <SidebarGroup key={category}>
              <SidebarGroupLabel>{category}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {visibleGuides.filter((guide) => guide.category === category).map((guide) => (
                    <SidebarMenuItem key={guide.id}>
                      <SidebarMenuButton
                        asChild
                        isActive={activeId === guide.id}
                        className="h-auto min-h-9 whitespace-normal py-2 text-left"
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
          Example
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
  const visibleGuides = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return howToGuides.filter((guide) => !normalizedQuery || searchableText(guide).includes(normalizedQuery));
  }, [query]);
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
                  <Input id="how-to-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search guides…" className="h-9 pl-9 text-sm" />
                </div>
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
                      <Input id="how-to-search-mobile" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search guides…" className="h-9 pl-9 text-sm" />
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
