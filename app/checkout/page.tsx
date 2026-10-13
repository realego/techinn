import type { Metadata } from "next";

import { CheckoutExperience } from "@/components/checkout-experience";
import Footer from "@/components/sections/footer/default";
import Navbar from "@/components/sections/navbar/default";
import { LayoutLines } from "@/components/ui/layout-lines";

export const metadata: Metadata = {
  title: { absolute: "Secure Checkout | TechInn" },
  description: "Review selected TechInn services and pay securely using EcoCash, OneMoney, or card through Paynow.",
  robots: { index: false, follow: true },
  alternates: { canonical: "https://my.techinn.co.zw/checkout/" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    url: "https://my.techinn.co.zw/checkout/",
    siteName: "TechInn",
    title: "Secure Checkout | TechInn",
    description: "Review selected services and continue to secure Paynow checkout.",
  },
  twitter: {
    card: "summary",
    title: "TechInn Secure Checkout",
    description: "Review selected services and pay securely through Paynow.",
  },
};

export default function CheckoutPage() {
  return (
    <main className="bg-background text-foreground min-h-screen w-full">
      <LayoutLines />
      <Navbar />
      <CheckoutExperience />
      <Footer />
    </main>
  );
}
