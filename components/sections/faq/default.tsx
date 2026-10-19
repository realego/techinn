import type { ReactNode } from "react";

import { Section } from "../../ui/section";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "../../ui/accordion";

const QUESTIONS = [
  { question: "What can I buy from TechInn?", answer: "TechInn provides domain registration, web hosting, business email, website design, app development, and business feature services such as booking and payment flows." },
  { question: "Can I use a domain that I already own?", answer: "Yes. Assign a purchased or connected domain to your hosting or email service from the dashboard. A pending domain can be assigned while registration completes." },
  { question: "When will my website or email become active?", answer: "Hosting can be prepared while a domain is processing, including a temporary preview URL. Public website traffic and email delivery begin after the domain and DNS are active." },
  { question: "How do renewals work?", answer: "Domains, hosting, and email appear as separate renewable services in Billing. Select Renew on the exact service, and the deposit form marks the payment as reserved for that service only." },
  { question: "What happens if a service expires?", answer: "The service is suspended according to its billing period. Websites show a TechInn suspension page, while files remain available for restoration after renewal." },
  { question: "How do I get help with setup?", answer: "Use the How-to guides, review the service status in your dashboard, or contact TechInn support from the details shown on your account and service pages." },
];

type FAQItem = { question: string; answer: ReactNode };

export default function FAQ({
  className,
  title = "Questions and answers",
  items,
}: {
  className?: string;
  title?: string;
  items?: FAQItem[] | false;
}) {
  const questions = items === false ? [] : items ?? QUESTIONS;
  return (
    <Section className={className}>
      <div className="mx-auto flex max-w-container flex-col items-center gap-8">
        <div className="text-center">
          <p className="text-brand text-sm font-medium">TechInn help</p>
          <h2 className="mt-2 text-3xl font-semibold sm:text-5xl">{title}</h2>
          <p className="text-muted-foreground mx-auto mt-3 max-w-2xl text-sm leading-6 sm:text-base">Clear answers about domains, hosting, email, payments, renewals, and your customer dashboard.</p>
        </div>
        <Accordion type="single" collapsible className="w-full max-w-[800px]">
          {questions.map((item, index) => (
            <AccordionItem key={item.question} value={`home-faq-${index}`}>
              <AccordionTrigger>{item.question}</AccordionTrigger>
              <AccordionContent>{item.answer}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </Section>
  );
}
