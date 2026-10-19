import type { Metadata } from "next";

import { DomainsExperience } from "@/components/domains-experience";
import Footer from "@/components/sections/footer/default";
import Navbar from "@/components/sections/navbar/default";
import { LayoutLines } from "@/components/ui/layout-lines";

export const metadata: Metadata = {
  title: { absolute: "Domain Search Zimbabwe | .co.zw, .com & More | TechInn" },
  description: "Find a domain name for your Zimbabwe business. Explore .co.zw, .com, .net, and .online domain options with TechInn.",
  keywords: ["domain search Zimbabwe", "buy .co.zw domain", ".com domain Zimbabwe", "business domain name", "TechInn domains"],
  alternates: { canonical: "https://my.techinn.co.zw/domains/" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    url: "https://my.techinn.co.zw/domains/",
    siteName: "TechInn",
    title: "Domain Search Zimbabwe | .co.zw, .com & More | TechInn",
    description: "Explore domain name options for your business, including .co.zw, .com, .net, and .online.",
  },
  twitter: {
    card: "summary",
    title: "Domain Search Zimbabwe | TechInn",
    description: "Find a memorable .co.zw or other domain name for your business with TechInn.",
  },
};

export default function DomainsPage() {
  return (
    <main className="bg-background text-foreground min-h-screen w-full">
      <LayoutLines />
      <Navbar />
      <DomainsExperience />
      <Footer />
    </main>
  );
}
