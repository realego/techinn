import { emailHostingPlans, webHostingPlans, websiteAddOns, websitePlans } from "@/config/hosting-plans";

export type ShopCategory = "All" | "Website Design" | "Web Hosting" | "Email Hosting" | "Domains" | "Chatbot Development" | "App Development";
export type ShopSelections = Record<string, string>;
export interface ShopOption {
  id: string;
  name: string;
  free?: boolean;
  choices: { id: string; label: string; price: number }[];
}
export interface ShopProduct {
  id: string;
  name: string;
  category: Exclude<ShopCategory, "All">;
  description: string;
  price: number;
  cadence: string;
  supportsYearly?: boolean;
  billingInterval?: "monthly" | "annually" | "one_time";
  annualOnly?: boolean;
  features: string[];
  visual: "website" | "hosting" | "email" | "domain" | "chatbot" | "app";
  image: string;
  options: ShopOption[];
  quantityLabel?: string;
  label?: string;
  popular?: boolean;
}
const noExtra = { id: "none", label: "Not needed", price: 0 };
const webOptions: ShopOption[] = [
  { id: "backup-retention", name: "Extended backup retention", choices: [noExtra, { id: "30days", label: "30-day retention", price: 1 }, { id: "90days", label: "90-day retention", price: 2 }] },
];
const emailOptionsByPlan: Record<string, ShopOption[]> = {
  essential: [
    { id: "storage", name: "Extra storage", choices: [{ ...noExtra, label: "Included 2 GB" }, { id: "5gb", label: "+5 GB storage", price: 5 }] },
    { id: "mailboxes", name: "Extra email accounts", choices: [{ ...noExtra, label: "21 accounts included" }, { id: "10", label: "+10 email accounts", price: 3 }] },
  ],
  team: [
    { id: "storage", name: "Extra storage", choices: [{ ...noExtra, label: "Included 5 GB" }, { id: "5gb", label: "+5 GB storage", price: 5 }] },
    { id: "mailboxes", name: "Extra email accounts", choices: [{ ...noExtra, label: "50 accounts included" }, { id: "20", label: "+20 email accounts", price: 5 }] },
  ],
  "business-mail": [
    { id: "storage", name: "Extra storage", choices: [{ ...noExtra, label: "Included 15 GB" }, { id: "15gb", label: "+15 GB storage", price: 15 }] },
  ],
};
export const domainExtensionChoices = [
  { id: "co-zw", label: ".co.zw domain", price: 2 },
  { id: "org-zw", label: ".org.zw domain", price: 3 },
  { id: "ac-zw", label: ".ac.zw domain", price: 3 },
  { id: "com", label: ".com domain", price: 20 },
  { id: "net", label: ".net domain", price: 20 },
  { id: "org", label: ".org domain", price: 20 },
];
const domainOptions: ShopOption[] = [
  { id: "extension", name: "Choose your domain", choices: domainExtensionChoices },
  { id: "monitoring", name: "Domain monitoring", choices: [noExtra, { id: "enabled", label: "Add domain monitoring", price: 4 }] },
  { id: "dns-assistance", name: "Managed DNS assistance", choices: [noExtra, { id: "enabled", label: "Add DNS assistance", price: 6 }] },
];
const appOptions: ShopOption[] = [
  { id: "publishing", name: "Publishing support", choices: [noExtra, { id: "enabled", label: "App Store and Play Store setup", price: 45 }] },
  { id: "maintenance", name: "Ongoing maintenance", choices: [noExtra, { id: "enabled", label: "Monthly maintenance", price: 25 }] },
];
const chatbotOptions: ShopOption[] = [
  { id: "flows", name: "Advanced flows", choices: [noExtra, { id: "enabled", label: "Add advanced flows", price: 25 }] },
  { id: "payments", name: "Payment integration", choices: [noExtra, { id: "enabled", label: "Add payment integration", price: 30 }] },
  { id: "booking", name: "Booking", free: true, choices: [noExtra, { id: "enabled", label: "Add booking", price: 0 }] },
  { id: "tickets", name: "Support tickets", choices: [noExtra, { id: "enabled", label: "Add ticket handling", price: 40 }] },
];

export const shopProducts: ShopProduct[] = [
  ...websitePlans.map((plan) => ({
    id: "website-" + plan.id,
    name: plan.name,
    category: "Website Design" as const,
    description: plan.description,
    price: plan.price,
    cadence: "one time",
    features: plan.features,
    visual: "website" as const,
    image: "/shop-assets/website-development.jpg",
    label: "Website design",
    popular: true,
    options: websiteAddOns.map((addOn) => ({
      id: addOn.id,
      name: addOn.id === "extra-page" ? "Additional pages" : addOn.name,
      free: addOn.price === 0,
      choices: addOn.id === "extra-page"
        ? [{ id: "none", label: "5 pages included", price: 0 }, ...Array.from({ length: 10 }, (_, index) => ({ id: String(index + 1), label: `${index + 1} extra ${index === 0 ? "page" : "pages"}`, price: (index + 1) * addOn.price }))]
        : [noExtra, { id: "enabled", label: "Add this feature", price: addOn.price }],
    })),
  })),
  ...webHostingPlans.map((plan) => ({
    id: "web-" + plan.id,
    name: plan.name + " Web Hosting",
    category: "Web Hosting" as const,
    description: plan.description,
    price: plan.price,
    cadence: "/ month",
    supportsYearly: true,
    features: plan.features,
    visual: "hosting" as const,
    label: "Hosting plan",
    options: webOptions,
    image: "/shop-assets/web-hosting.webp",
  })),
  ...emailHostingPlans.map((plan) => ({
    id: "email-" + plan.id,
    name: plan.name + " Email",
    category: "Email Hosting" as const,
    description: plan.description,
    price: plan.price,
    cadence: "/ year",
    supportsYearly: false,
    billingInterval: "annually" as const,
    annualOnly: true,
    features: plan.features,
    visual: "email" as const,
    quantityLabel: "mailbox",
    label: "Email plan",
    options: emailOptionsByPlan[plan.id] ?? [],
    image: "/shop-assets/business-email.svg",
  })),
  {
    id: "domains", name: "Domains", category: "Domains",
    description: "Choose the domain extension that gives your business a name customers can remember.", price: 0, cadence: "/ year",
    features: [".co.zw and .com options", "DNS management", "Renewable yearly"], visual: "domain", label: "Domain registration", options: domainOptions,
    image: "/shop-assets/domains.png",
  },
  {
    id: "chatbot-basic", name: "Basic chatbot development", category: "Chatbot Development",
    description: "A helpful business chatbot with automated replies, a general assistant, and essential admin alerts.",
    price: 80, cadence: "one time",
    features: [
      "Automated replies to common customer questions",
      "General assistant for your business",
      "Admin notifications for customer enquiries",
      "Answers about your products and services",
      "Basic setup, testing, and launch support",
    ],
    visual: "chatbot", label: "New service", options: chatbotOptions,
    image: "/shop-assets/chatbot-development.jpeg",
  },
  {
    id: "app-development", name: "App development", category: "App Development",
    description: "Turn your idea into a polished mobile app for your customers.", price: 250, cadence: "one time",
    features: ["Mobile app interface", "Responsive app screens", "Launch-ready foundation"], visual: "app", label: "New service", options: appOptions,
    image: "/shop-assets/app-development.png",
  },
];

export const storageExtensionProduct: ShopProduct = {
  id: "web-storage-addon",
  name: "Extra 5 GB hosting storage",
  category: "Web Hosting",
  description: "Add 5 GB of shared website and email storage to an active hosting service.",
  price: 2,
  cadence: "/ month",
  supportsYearly: true,
  features: ["5 GB added to the selected hosting service", "Shared by its websites and mailbox allocations"],
  visual: "hosting",
  image: "/shop-assets/web-hosting.webp",
  quantityLabel: "5 GB storage unit",
  options: [],
};

export function billingPrice(price: number, yearly: boolean, applyDiscount = true) {
  const cents = Math.round(price * 100);
  return (yearly && applyDiscount ? Math.round(cents * 108 / 10) : cents) / 100;
}

export function configureProduct(product: ShopProduct, selections: ShopSelections = {}) {
  const options: ShopSelections = {};
  const yearly = product.billingInterval === "annually" || Boolean(product.supportsYearly && selections.billing === "yearly");
  if (yearly) options.billing = "yearly";
  const cadence = yearly ? product.cadence.replace("month", "year") : product.cadence;
  const selectedOptions = product.options.flatMap((option) => {
    const choice = option.choices.find((item) => item.id === selections[option.id]);
    if (!choice || choice.id === "none") return [];
    options[option.id] = choice.id;
    return [{ name: option.name, label: choice.label, price: billingPrice(choice.price, yearly, !product.annualOnly) }];
  });
  const extraCents = selectedOptions.reduce((sum, option) => sum + Math.round(option.price * 100), 0);
  const unitPrice = (Math.round(billingPrice(product.price, yearly, !product.annualOnly) * 100) + extraCents) / 100;
  const id = product.id + ":" + JSON.stringify(Object.entries(options).sort(([a], [b]) => a.localeCompare(b)));
  return { id, options, selectedOptions, extraPrice: extraCents / 100, unitPrice, yearly, cadence };
}
