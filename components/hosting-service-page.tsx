import { Database, Globe2, Headphones, Inbox, LockKeyhole, Mail, MonitorSmartphone, Rocket, SearchCheck, ShieldCheck } from "lucide-react";

import CTA from "@/components/sections/cta/default";
import FAQ from "@/components/sections/faq/default";
import Footer from "@/components/sections/footer/default";
import Hero from "@/components/sections/hero/default";
import Items from "@/components/sections/items/default";
import Navbar from "@/components/sections/navbar/default";
import Pricing from "@/components/sections/pricing/default";
import { Badge } from "@/components/ui/badge";
import { LayoutLines } from "@/components/ui/layout-lines";

type Service = "web" | "email";

const webBenefits = [
  { title: "Room to grow", description: "Choose the storage and website capacity that fits your next step.", icon: <Database className="size-5 stroke-1" /> },
  { title: "Email included", description: "Use addresses on your own domain with every web hosting plan.", icon: <Mail className="size-5 stroke-1" /> },
  { title: "Secure connections", description: "SSL is included in the proposed plan features.", icon: <LockKeyhole className="size-5 stroke-1" /> },
  { title: "SEO-ready foundations", description: "Start with a mobile-friendly, discoverable website structure.", icon: <SearchCheck className="size-5 stroke-1" /> },
  { title: "Simple setup", description: "A clear path from choosing a plan to bringing your site online.", icon: <Rocket className="size-5 stroke-1" /> },
  { title: "Support options", description: "Pick the level of help that matches your business needs.", icon: <Headphones className="size-5 stroke-1" /> },
];

const emailBenefits = [
  { title: "Your domain, your address", description: "Present your business with a professional email address.", icon: <Globe2 className="size-5 stroke-1" /> },
  { title: "Shared space that fits", description: "Start at 2 GB shared storage and add room as your team grows.", icon: <Inbox className="size-5 stroke-1" /> },
  { title: "Works across devices", description: "Use webmail or a compatible mail app on desktop and mobile.", icon: <MonitorSmartphone className="size-5 stroke-1" /> },
  { title: "Spam filtering", description: "Keep unwanted messages out of your daily workflow.", icon: <ShieldCheck className="size-5 stroke-1" /> },
];

const webQuestions = [
  { question: "What is included in the Basic plan?", answer: <p>Basic is the proposed entry plan for one website, with 2 GB of SSD storage, unlimited email accounts, SSL, and weekly backups.</p> },
  { question: "How does yearly billing work?", answer: <p>Yearly billing uses the monthly rate with a 10% discount and is charged for the full year. The plan cards show the exact annual total.</p> },
  { question: "Can I use my own domain?", answer: <p>Yes, the hosting experience is designed to work with a domain you already own or one you find on our Domains page.</p> },
];

const emailQuestions = [
  { question: "Do I need a domain for email hosting?", answer: <p>A domain gives you addresses like hello@yourbusiness.com. You can use one you own or explore names on our Domains page.</p> },
  { question: "How is email hosting priced?", answer: <p>Email hosting is sold as an annual plan with shared storage and a set number of accounts. Add storage or account capacity when you need it.</p> },
  { question: "Can I use email on my phone?", answer: <p>The planned service includes webmail and standard IMAP and SMTP access for compatible mail apps.</p> },
];

export function HostingServicePage({ service }: { service: Service }) {
  const isWeb = service === "web";
  return (
    <main className="bg-background text-foreground min-h-screen w-full">
      <LayoutLines />
      <Navbar />
      {isWeb && (
        <Hero
          title={<>Web hosting built for <span className="text-orange-600 dark:text-orange-400">what comes next.</span></>}
          description="From your first site to a growing business, find a hosting plan with the space, email, and essentials you need."
          badge={<Badge variant="outline" className="border-brand/30 text-brand">Web Hosting by TechInn</Badge>}
          mockup={false}
          buttons={[
            { href: "#plans", text: "View plans", variant: "default" },
            { href: "/domains/", text: "Find a domain", variant: "glow" },
          ]}
        />
      )}
      <Pricing service={service} />
      <Items
        title={isWeb ? "The essentials, all in one place." : "A better home for your business email."}
        items={isWeb ? webBenefits : emailBenefits}
      />
      <FAQ title="Questions about the plans" items={isWeb ? webQuestions : emailQuestions} />
      <CTA
        title={isWeb ? "Ready to put your website online?" : "Give your business email a new home."}
        buttons={[{ href: "#plans", text: "Compare plans", variant: "default" }]}
      />
      <Footer />
    </main>
  );
}
