import type { MetadataRoute } from "next";

import { howToGuides } from "@/config/how-to-guides";

const siteUrl = "https://my.techinn.co.zw";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    "",
    "/shop/",
    "/domains/",
    "/web-hosting/",
    "/email-hosting/",
    "/checkout/",
    "/how-to/",
  ];
  const staticEntries = routes.map((route) => ({
    url: `${siteUrl}${route || "/"}`,
    lastModified: new Date(),
  }));
  const guideEntries = howToGuides.map((guide) => ({
    url: `${siteUrl}/how-to/${guide.id}/`,
    lastModified: new Date(),
  }));

  return [...staticEntries, ...guideEntries];
}
