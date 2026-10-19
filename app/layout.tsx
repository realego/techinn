import "@/app/globals.css";

import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";

import { AttributionCapture } from "@/components/attribution-capture";
import { CookieConsent } from "@/components/cookie-consent";
import { SessionActivity } from "@/components/session-activity";
import { inter } from "@/lib/fonts";

import { siteConfig } from "../config/site";

export const metadata: Metadata = {
  title: {
    default: "TechInn Zimbabwe | Domains, Web Hosting & Business Email",
    template: `%s | ${siteConfig.name}`,
  },
  metadataBase: new URL(siteConfig.url),
  description: siteConfig.description,
  keywords: [
    "TechInn Zimbabwe",
    "domain names Zimbabwe",
    ".co.zw domain registration",
    "web hosting Zimbabwe",
    "business email hosting Zimbabwe",
    "website design Zimbabwe",
    "small business websites Zimbabwe",
  ],
  authors: [{ name: "TechInn", url: siteConfig.url }],
  creator: "TechInn",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    locale: "en_ZW",
    url: siteConfig.url + "/",
    title: "TechInn Zimbabwe | Domains, Web Hosting & Business Email",
    description: siteConfig.description,
    siteName: siteConfig.name,
    images: [
      {
        url: siteConfig.ogImage,
        width: 1774,
        height: 887,
        alt: "TechInn - Domains, Web Hosting, Business Email and Website Design",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "TechInn Zimbabwe | Domains, Web Hosting & Business Email",
    description: siteConfig.description,
    images: [siteConfig.ogImage],
  },
  icons: {
    icon: [
      { url: "/techinn-favicon-ntxuir.ico", sizes: "16x16 32x32 48x48" },
      { url: "/techinn-icon-32-v2.png", type: "image/png", sizes: "32x32" },
      { url: "/techinn-icon-16-v2.png", type: "image/png", sizes: "16x16" },
    ],
    shortcut: "/techinn-favicon-ntxuir.ico",
    apple: { url: "/techinn-apple-icon-v2.png", sizes: "180x180", type: "image/png" },
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="dark"
      style={{ colorScheme: "dark" }}
      suppressHydrationWarning
    >
      <body className={`${inter.variable} bg-background font-sans antialiased`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <AttributionCapture />
          <SessionActivity />
          <CookieConsent />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
