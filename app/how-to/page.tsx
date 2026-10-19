import type { Metadata } from "next";

import { HowToExperience } from "@/components/how-to-experience";
import Footer from "@/components/sections/footer/default";
import Navbar from "@/components/sections/navbar/default";
import { LayoutLines } from "@/components/ui/layout-lines";
import { howToGuides } from "@/config/how-to-guides";

const guideListStructuredData = {
  "@context": "https://schema.org",
  "@type": "ItemList",
  name: "TechInn how-to guides",
  itemListElement: howToGuides.map((guide, index) => ({
    "@type": "ListItem",
    position: index + 1,
    name: guide.title,
    url: `https://my.techinn.co.zw/how-to/${guide.id}/`,
  })),
};

export const metadata: Metadata = {
  title: "How-to Guides | TechInn",
  description: "Find answers about Zimbabwe domain names, .co.zw registration, web hosting, business email, website design, pricing, and checkout with clear TechInn how-to guides.",
  keywords: [
    "TechInn help",
    "Zimbabwe web hosting help",
    "domain name help Zimbabwe",
    ".co.zw domain search",
    "business email hosting Zimbabwe",
    "professional email setup",
    "website design packages Zimbabwe",
    "web hosting plans",
    "domain and hosting questions",
    "TechInn checkout help",
  ],
  robots: { index: true, follow: true },
  alternates: { canonical: "https://my.techinn.co.zw/how-to/" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    siteName: "TechInn",
    title: "How-to Guides | TechInn",
    description: "Straightforward answers about .co.zw domains, Zimbabwe web hosting, professional email, website design, and TechInn checkout.",
    url: "https://my.techinn.co.zw/how-to/",
  },
  twitter: {
    card: "summary",
    title: "TechInn How-to Guides",
    description: "Answers about domains, hosting, business email, website design, pricing, and checkout.",
  },
};

export default function HowToPage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(guideListStructuredData).replace(/</g, "\\u003c") }} />
      <LayoutLines />
      <Navbar />
      <HowToExperience />
      <Footer />
    </>
  );
}
