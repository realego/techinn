import type { Metadata } from "next";

import { ServiceShopRedirect } from "@/components/service-shop-redirect";

export const metadata: Metadata = {
  title: { absolute: "Business Email Hosting Zimbabwe from $1.50/Mailbox | TechInn" },
  description: "Set up professional business email on your own domain with TechInn. Compare Zimbabwe email hosting plans from $1.50 per mailbox/month.",
  keywords: ["business email hosting Zimbabwe", "professional email on your domain", "custom domain email", "business email plans", "TechInn email hosting"],
  alternates: { canonical: "https://my.techinn.co.zw/shop/?service=email" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    url: "https://my.techinn.co.zw/shop/?service=email",
    siteName: "TechInn",
    title: "Business Email Hosting Zimbabwe | TechInn",
    description: "Choose a professional email plan for addresses like hello@yourbusiness.co.zw.",
  },
  twitter: {
    card: "summary",
    title: "Business Email Hosting | TechInn Zimbabwe",
    description: "Professional email addresses on your own domain, from $1.50 per mailbox/month.",
  },
};

export default function EmailHostingPage() {
  return <ServiceShopRedirect service="email" />;
}
