import type { ReactNode } from "react";
import Navbar from "@/components/sections/navbar/default";
import Footer from "@/components/sections/footer/default";

export type LegalSection = { title: string; content: ReactNode };

export function LegalPage({ title, intro, updated, sections }: { title: string; intro: string; updated: string; sections: LegalSection[] }) {
  return <><Navbar /><main className="mx-auto max-w-4xl px-4 pb-20 pt-12 sm:pt-16"><header className="border-b pb-8"><p className="text-sm font-medium text-orange-600 dark:text-orange-400">TechInn legal</p><h1 className="mt-2 text-4xl font-semibold tracking-tight sm:text-5xl">{title}</h1><p className="text-muted-foreground mt-4 max-w-3xl text-base leading-7">{intro}</p><p className="text-muted-foreground mt-4 text-xs">Effective date: {updated}</p></header><div className="mt-10 space-y-9">{sections.map((section) => <section key={section.title} className="scroll-mt-24"><h2 className="text-2xl font-semibold tracking-tight">{section.title}</h2><div className="text-muted-foreground mt-3 space-y-3 text-sm leading-7">{section.content}</div></section>)}</div></main><Footer /></>;
}
