import type { Metadata } from "next";
import { Suspense } from "react";

import Footer from "@/components/sections/footer/default";
import Navbar from "@/components/sections/navbar/default";
import { ShopExperience } from "@/components/shop-experience";
import { LayoutLines } from "@/components/ui/layout-lines";

export const metadata: Metadata = {
  title: { absolute: "Shop Domains, Hosting, Email & Website Design | TechInn Zimbabwe" },
  description: "Compare domain names, web hosting plans, professional email hosting, and small-business website design packages from TechInn Zimbabwe.",
  keywords: ["TechInn shop", "domains and web hosting Zimbabwe", "email hosting plans", "website design packages Zimbabwe", "business website services"],
  alternates: { canonical: "https://my.techinn.co.zw/shop/" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    url: "https://my.techinn.co.zw/shop/",
    siteName: "TechInn",
    title: "Shop Domains, Hosting, Email & Website Design | TechInn",
    description: "Compare domains, hosting, professional email, and website design for your business.",
  },
  twitter: {
    card: "summary",
    title: "Shop TechInn Business Services",
    description: "Compare domains, web hosting, business email, and website design.",
  },
};

export default function ShopPage() {
  return (
    <>
      <LayoutLines />
      <Navbar />
      <Suspense fallback={<div className="min-h-96 px-4 py-10 text-center text-muted-foreground">Loading services…</div>}>
        <ShopExperience />
      </Suspense>
      <Footer />
    </>
  );
}
