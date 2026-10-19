import type { Metadata } from "next";

import { ServiceShopRedirect } from "@/components/service-shop-redirect";

export const metadata: Metadata = {
  title: { absolute: "Web Hosting Zimbabwe from $3.50/Month | TechInn" },
  description: "Compare TechInn web hosting plans in Zimbabwe, from $3.50/month. Plans include SSD storage, SSL, backups, and email accounts for your domain.",
  keywords: ["web hosting Zimbabwe", "website hosting plans", "affordable web hosting", "SSD hosting Zimbabwe", "TechInn web hosting"],
  alternates: { canonical: "https://my.techinn.co.zw/shop/?service=web" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    url: "https://my.techinn.co.zw/shop/?service=web",
    siteName: "TechInn",
    title: "Web Hosting Zimbabwe from $3.50/Month | TechInn",
    description: "Compare website hosting plans with SSD storage, SSL, backups, and email for your domain.",
  },
  twitter: {
    card: "summary",
    title: "Web Hosting Plans in Zimbabwe | TechInn",
    description: "Compare affordable web hosting plans for your business website.",
  },
};

export default function WebHostingPage() {
  return <ServiceShopRedirect service="web" />;
}
