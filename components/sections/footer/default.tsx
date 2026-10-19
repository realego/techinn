import Link from "next/link";
import { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { CookieSettingsTrigger } from "@/components/cookie-settings-trigger";

import { TechInnBrand } from "../../logos/techinn-brand";
import {
  Footer,
  FooterBottom,
  FooterColumn,
  FooterContent,
} from "../../ui/footer";
import { ModeToggle } from "../../ui/mode-toggle";

interface FooterLink {
  text: string;
  href: string;
}

interface FooterColumnProps {
  title: string;
  links: FooterLink[];
}

interface FooterProps {
  logo?: ReactNode;
  name?: string;
  columns?: FooterColumnProps[];
  copyright?: string;
  policies?: FooterLink[];
  showModeToggle?: boolean;
  className?: string;
}

export default function FooterSection({
  logo = <TechInnBrand className="w-28 sm:w-32" />,
  name = "TechInn Hosting",
  columns = [
    {
      title: "Product",
      links: [
        { text: "Domains", href: "/domains/" },
        { text: "Web hosting", href: "/shop/?service=web" },
        { text: "Business email", href: "/shop/?service=email" },
        { text: "How to guides", href: "/how-to/" },
      ],
    },
    {
      title: "Company",
      links: [
        { text: "Shop all services", href: "/shop/" },
        { text: "Customer dashboard", href: "/dashboard/" },
        { text: "Contact TechInn", href: "mailto:support@my.techinn.co.zw" },
      ],
    },
    {
      title: "Contact",
      links: [
        { text: "Support email", href: "mailto:support@my.techinn.co.zw" },
        { text: "WhatsApp", href: "https://wa.me/263717959400" },
        { text: "Call 00263717959400", href: "tel:00263717959400" },
        { text: "Billing help", href: "/how-to/billing-renewals/" },
        { text: "Hosting help", href: "/how-to/hosting-file-manager/" },
      ],
    },
  ],
  copyright = "© 2026 TechInn. All rights reserved",
  policies = [
    { text: "Privacy Policy", href: "/privacy/" },
    { text: "Terms of Service", href: "/terms/" },
  ],
  showModeToggle = true,
  className,
}: FooterProps) {
  return (
    <footer className={cn("bg-background w-full px-4", className)}>
      <div className="max-w-container mx-auto">
        <Footer>
          <FooterContent>
            <FooterColumn className="col-span-2 sm:col-span-3 md:col-span-1">
              <Link href="/" aria-label={name + " home"} className="inline-flex items-center gap-2">
                {logo}
              </Link>
            </FooterColumn>
            {columns.map((column) => (
              <FooterColumn key={column.title}>
                <h3 className="text-md pt-1 font-semibold">{column.title}</h3>
                {column.links.map((link) => (
                  <a
                    key={`${link.href}-${link.text}`}
                    href={link.href}
                    className="text-muted-foreground text-sm"
                  >
                    {link.text}
                  </a>
                ))}
              </FooterColumn>
            ))}
          </FooterContent>
          <FooterBottom>
            <div>{copyright}</div>
            <div className="flex items-center gap-4">
              {policies.map((policy) => (
                <a key={`${policy.href}-${policy.text}`} href={policy.href}>
                  {policy.text}
                </a>
              ))}
              <CookieSettingsTrigger />
              {showModeToggle && <ModeToggle />}
            </div>
          </FooterBottom>
        </Footer>
      </div>
    </footer>
  );
}
