export type HostingService = "web" | "email";
export type PlanService = HostingService | "website";

export interface HostingPlan {
  id: string;
  name: string;
  description: string;
  price: number;
  billing: "monthly" | "project";
  features: string[];
  variant: "default" | "glow-brand" | "glow";
}

export const webHostingPlans: HostingPlan[] = [
  {
    id: "basic",
    name: "Basic",
    description: "A reliable start for your first website",
    price: 3.5,
    billing: "monthly",
    features: ["1 website", "2 GB SSD storage", "Unlimited email accounts", "Free SSL certificate", "Weekly backups", "SEO-friendly setup"],
    variant: "default",
  },
  {
    id: "growth",
    name: "Growth",
    description: "More room for growing sites and businesses",
    price: 7,
    billing: "monthly",
    features: ["Up to 5 websites", "10 GB SSD storage", "Unlimited email accounts", "Free SSL certificates", "Daily backups", "WordPress-ready hosting"],
    variant: "glow-brand",
  },
  {
    id: "business",
    name: "Business",
    description: "Extra space for busy, established websites",
    price: 12,
    billing: "monthly",
    features: ["Up to 20 websites", "25 GB SSD storage", "Unlimited email accounts", "Free SSL certificates", "Daily backups", "Priority support"],
    variant: "glow",
  },
];

export const emailHostingPlans: HostingPlan[] = [
  {
    id: "essential",
    name: "Essential",
    description: "A professional inbox for one person",
    price: 1.5,
    billing: "monthly",
    features: ["2 GB storage per mailbox", "Email at your own domain", "Webmail access", "IMAP and SMTP access", "Spam filtering"],
    variant: "default",
  },
  {
    id: "team",
    name: "Team",
    description: "More mailbox space for day-to-day teamwork",
    price: 3.5,
    billing: "monthly",
    features: ["10 GB storage per mailbox", "Email at your own domain", "Webmail access", "IMAP and SMTP access", "Spam filtering", "Email forwarding"],
    variant: "glow-brand",
  },
  {
    id: "business-mail",
    name: "Business Mail",
    description: "A larger inbox for a busy business",
    price: 6.5,
    billing: "monthly",
    features: ["25 GB storage per mailbox", "Email at your own domain", "Webmail access", "IMAP and SMTP access", "Spam filtering", "Priority setup support"],
    variant: "glow",
  },
];

export const websitePlans: HostingPlan[] = [
  {
    id: "basic-website",
    name: "Website development",
    description: "A clean, mobile-friendly website for a small business",
    price: 60,
    billing: "project",
    features: ["Up to 5 pages", "Mobile-friendly layout", "Contact form", "Basic on-page SEO", "Launch support"],
    variant: "default",
  },
];

export const websiteAddOns = [
  { id: "extra-page", name: "Additional page", description: "Add one page beyond the five included pages.", price: 10, features: ["Designed to match your website", "One page per add-on"] },
  { id: "online-store", name: "Shopping cart and checkout", description: "Add ecommerce features for customers to browse and buy online.", price: 120, features: ["Product catalogue setup", "Cart and checkout flow", "Payment integration setup"] },
  { id: "booking", name: "Online booking", description: "Let visitors request or schedule appointments from your website at no extra cost.", price: 0, features: ["Booking form or calendar setup", "Email enquiry notifications"] },
  { id: "blog", name: "Blog or news section", description: "Publish updates, articles, and useful information for customers.", price: 35, features: ["Blog listing page", "Article page template"] },
];

export function planSelectionHref(service: PlanService, planId: string, billing: "monthly" | "yearly" = "monthly") {
  return "/shop/?service=" + service + "&plan=" + encodeURIComponent(planId) + (billing === "yearly" ? "&billing=yearly" : "");
}
