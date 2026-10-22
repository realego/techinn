import type { Metadata } from "next";
import Image from "next/image";

import { DomainSearchForm } from "../components/domain-search-form";
import { HomeDomainHeading } from "../components/home-domain-heading";
import CTA from "../components/sections/cta/default";
import FAQ from "../components/sections/faq/default";
import Footer from "../components/sections/footer/default";
import Hero from "../components/sections/hero/default";
import Items from "../components/sections/items/default";
import Navbar from "../components/sections/navbar/default";
import Pricing from "../components/sections/pricing/default";
import Stats from "../components/sections/stats/default";
import { Badge } from "../components/ui/badge";
import Glow from "../components/ui/glow";
import { LayoutLines } from "../components/ui/layout-lines";

export const metadata: Metadata = {
  title: { absolute: "TechInn Zimbabwe | .co.zw Domains, Web Hosting & Business Email" },
  description: "Search .co.zw domains and explore affordable web hosting, professional business email, and mobile-friendly website design for Zimbabwean businesses. Website packages from $60.",
  keywords: [
    "TechInn Zimbabwe",
    "buy .co.zw domain",
    "domain search Zimbabwe",
    "web hosting Zimbabwe",
    "affordable website hosting",
    "business email Zimbabwe",
    "professional email on my domain",
    "website design Zimbabwe",
    "small business website packages",
  ],
  alternates: { canonical: "https://my.techinn.co.zw/" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    url: "https://my.techinn.co.zw/",
    siteName: "TechInn",
    title: "TechInn Zimbabwe | .co.zw Domains, Web Hosting & Business Email",
    description: "Find a .co.zw domain, web hosting, professional business email, and small-business website design from TechInn.",
    images: [{ url: "https://my.techinn.co.zw/techinn-logo.png", width: 1774, height: 887, alt: "TechInn Zimbabwe" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "TechInn Zimbabwe | Domains, Hosting & Business Email",
    description: "Search domains and explore hosting, professional email, and website design for Zimbabwean businesses.",
    images: ["https://my.techinn.co.zw/techinn-logo.png"],
  },
};

export default function Home() {
  return (
    <main className="bg-background text-foreground min-h-screen w-full">
      <LayoutLines />
      <Navbar className="h-20 -mb-20" />
      <section className="group/domain relative isolate overflow-hidden px-4 pt-32 pb-10 sm:pt-36 sm:pb-14">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black_70%,transparent_100%)]">
          <div className="absolute inset-0 bg-linear-to-b from-orange-500/15 via-orange-500/5 to-transparent" />
          <div className="absolute inset-0 translate-y-4 opacity-70 transition-[transform,opacity] duration-700 ease-out group-hover/domain:-translate-y-3 group-hover/domain:opacity-100 group-focus-within/domain:-translate-y-3 group-focus-within/domain:opacity-100 motion-reduce:transform-none motion-reduce:transition-none">
            <Glow variant="center" className="top-[85%] [&>div]:opacity-70 dark:[&>div]:opacity-100" />
          </div>
        </div>
        <div className="max-w-container relative z-10 mx-auto text-center">
          <HomeDomainHeading />
          <DomainSearchForm className="mx-auto max-w-3xl" />
        </div>
      </section>
      <Pricing service="web" />
      <CTA
        title="Email hosting plans"
        description="Professional email for your domain, with mailbox space for every stage of your business."
        buttons={[
          {
            href: "/shop/?service=email",
            text: "Explore email plans",
            variant: "default",
          },
        ]}
      />
      <Pricing service="email" />
      <Hero
        title={<>We can build a good website for your business <span className="text-orange-600 dark:text-orange-400">from just $60.</span></>}
        description="Start with up to five mobile-friendly pages, a contact form, and basic SEO. Add features such as online shopping or bookings only when you need them, with a clear price for each."
        badge={<Badge variant="outline" className="border-brand/30 text-brand">Website design by TechInn</Badge>}
        buttons={[
          { href: "/shop/?service=website", text: "Explore website design", variant: "default" },
          { href: "/domains/", text: "Find a domain", variant: "glow" },
        ]}
      />
      <Items />
      <Stats />
      <FAQ />
      <section className="group/reviews relative isolate overflow-hidden px-4 py-16 sm:py-24" aria-labelledby="google-review-title">
        <div className="relative z-10 mx-auto flex max-w-container flex-col items-center gap-5 rounded-2xl border border-orange-500/20 bg-orange-500/5 px-5 py-10 text-center sm:px-10">
          <h2 id="google-review-title" className="text-3xl font-semibold tracking-tight sm:text-4xl">Enjoying TechInn?</h2>
          <p className="text-muted-foreground max-w-xl text-sm leading-6 sm:text-base">Share your experience on Google. Your feedback helps other Zimbabwean businesses find the right digital services.</p>
          <a
            href="https://g.page/r/CewwIePtW5X9EBM/review"
            target="_blank"
            rel="noreferrer"
            aria-label="Review TechInn on Google"
            className="group/review-link rounded-xl border border-orange-400/60 bg-background/80 p-2 shadow-sm transition-[border-color,box-shadow,transform] duration-200 hover:border-orange-500 hover:shadow-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-orange-500"
          >
            <Image
              src="/reviews/google-review-button.png"
              alt="Google Reviews — leave a review for TechInn"
              width={334}
              height={187}
              className="h-auto w-56 transition-transform duration-200 group-hover/review-link:scale-105 sm:w-64"
              unoptimized
            />
            <span className="sr-only">Review TechInn on Google</span>
          </a>
        </div>
        <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 -z-10 opacity-70 transition-opacity duration-500 group-hover/reviews:opacity-100"><Glow variant="bottom" /></div>
      </section>
      <Footer />
    </main>
  );
}
