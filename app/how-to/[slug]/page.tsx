import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { GuideArticle } from "@/components/how-to-experience";
import Footer from "@/components/sections/footer/default";
import Navbar from "@/components/sections/navbar/default";
import { LayoutLines } from "@/components/ui/layout-lines";
import { howToGuides } from "@/config/how-to-guides";

type GuidePageProps = {
  params: Promise<{ slug: string }>;
};

export const dynamicParams = false;

export function generateStaticParams() {
  return howToGuides.map(({ id }) => ({ slug: id }));
}

export async function generateMetadata({ params }: GuidePageProps): Promise<Metadata> {
  const { slug } = await params;
  const guide = howToGuides.find((item) => item.id === slug);
  if (!guide) return {};

  const pageUrl = `https://my.techinn.co.zw/how-to/${guide.id}/`;
  return {
    title: `${guide.title} | TechInn How-to`,
    description: guide.summary,
    keywords: [
      guide.title,
      guide.category,
      "TechInn help",
      "Zimbabwe",
      "Zimbabwe small business",
      ...guide.faqs.map((faq) => faq.question),
    ],
    robots: { index: true, follow: true },
    alternates: { canonical: pageUrl },
    openGraph: {
      type: "article",
      locale: "en_ZW",
      siteName: "TechInn",
      title: guide.title,
      description: guide.summary,
      url: pageUrl,
    },
    twitter: {
      card: "summary",
      title: `${guide.title} | TechInn`,
      description: guide.summary,
    },
  };
}

function structuredData(guide: (typeof howToGuides)[number]) {
  const pageUrl = `https://my.techinn.co.zw/how-to/${guide.id}/`;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "HowTo",
        "@id": `${pageUrl}#howto`,
        name: guide.title,
        description: guide.summary,
        inLanguage: "en",
        step: guide.steps.map((step, index) => ({
          "@type": "HowToStep",
          position: index + 1,
          name: step.title,
          text: step.description,
        })),
        ...(guide.videoUrl
          ? {
              video: {
                "@type": "VideoObject",
                name: guide.videoTitle,
                description: guide.videoDescription,
                contentUrl: guide.videoUrl,
              },
            }
          : {}),
      },
      {
        "@type": "FAQPage",
        "@id": `${pageUrl}#faq`,
        mainEntity: guide.faqs.map((faq) => ({
          "@type": "Question",
          name: faq.question,
          acceptedAnswer: { "@type": "Answer", text: faq.answer },
        })),
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: "https://my.techinn.co.zw/" },
          { "@type": "ListItem", position: 2, name: "How-to Guides", item: "https://my.techinn.co.zw/how-to/" },
          { "@type": "ListItem", position: 3, name: guide.title, item: pageUrl },
        ],
      },
    ],
  };
}

export default async function HowToGuidePage({ params }: GuidePageProps) {
  const { slug } = await params;
  const guide = howToGuides.find((item) => item.id === slug);
  if (!guide) notFound();

  const otherGuides = howToGuides.filter((item) => item.id !== guide.id);
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData(guide)).replace(/</g, "\\u003c") }} />
      <LayoutLines />
      <Navbar />
      <main className="px-4 pb-16 pt-8 sm:pt-12">
        <div className="max-w-5xl mx-auto">
          <nav aria-label="Breadcrumb" className="text-muted-foreground mb-6 flex flex-wrap items-center gap-2 text-sm">
            <Link href="/" className="hover:text-foreground">Home</Link>
            <span aria-hidden="true">/</span>
            <Link href="/how-to/" className="hover:text-foreground">How-to guides</Link>
            <span aria-hidden="true">/</span>
            <span aria-current="page" className="text-foreground">{guide.title}</span>
          </nav>
          <div className="rounded-xl border bg-background p-5 sm:p-8 lg:p-10">
            <GuideArticle guide={guide} />
          </div>
          <nav aria-label="Related how-to guides" className="mt-10 border-t pt-6">
            <h2 className="mb-4 text-lg font-semibold">More TechInn help</h2>
            <ul className="grid gap-3 sm:grid-cols-2">
              {otherGuides.map((otherGuide) => (
                <li key={otherGuide.id}>
                  <Link href={`/how-to/${otherGuide.id}/`} className="group block rounded-lg border p-4 transition-colors hover:border-brand/40 hover:bg-muted/20">
                    <span className="text-brand text-xs font-medium">{otherGuide.category}</span>
                    <span className="mt-1 block font-medium group-hover:underline">{otherGuide.title}</span>
                    <span className="text-muted-foreground mt-1 block text-sm leading-relaxed">{otherGuide.summary}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </main>
      <Footer />
    </>
  );
}
