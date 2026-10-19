import {
  BlocksIcon,
  EclipseIcon,
  FastForwardIcon,
  LanguagesIcon,
  MonitorSmartphoneIcon,
  RocketIcon,
  ScanFaceIcon,
  SquarePenIcon,
} from "lucide-react";
import { ReactNode } from "react";

import { Item, ItemDescription, ItemIcon, ItemTitle } from "../../ui/item";
import { Section } from "../../ui/section";

interface ItemProps {
  title: string;
  description: string;
  icon: ReactNode;
}

interface ItemsProps {
  title?: string;
  items?: ItemProps[] | false;
  className?: string;
}

const DEFAULT_ITEMS: ItemProps[] = [
  {
    title: "Domains",
    description: "Search and register .co.zw, .org.zw, .ac.zw, .com, .net, and .org domains.",
    icon: <ScanFaceIcon className="size-5 stroke-1" />,
  },
  {
    title: "Web hosting",
    description: "Managed hosting, storage, SSL, file manager access, and website previews.",
    icon: <MonitorSmartphoneIcon className="size-5 stroke-1" />,
  },
  {
    title: "Business email",
    description: "Professional mailboxes on your domain with quotas and webmail access.",
    icon: <EclipseIcon className="size-5 stroke-1" />,
  },
  {
    title: "DNS management",
    description: "Review, add, edit, and remove DNS records from your dashboard.",
    icon: <BlocksIcon className="size-5 stroke-1" />,
  },
  {
    title: "Secure billing",
    description: "Track invoices, deposits, service periods, and separate renewals.",
    icon: <FastForwardIcon className="size-5 stroke-1" />,
  },
  {
    title: "Service support",
    description: "Follow provisioning status and get clear next steps when a service needs attention.",
    icon: <RocketIcon className="size-5 stroke-1" />,
  },
  {
    title: "Website design",
    description: "Start with a small-business website and add booking, shopping, or other features.",
    icon: <LanguagesIcon className="size-5 stroke-1" />,
  },
  {
    title: "Account control",
    description: "Manage your profile, passwords, OTP resets, team access, and notifications.",
    icon: <SquarePenIcon className="size-5 stroke-1" />,
  },
];

export default function Items({
  title = "Everything your business needs to get online.",
  items = DEFAULT_ITEMS,
  className,
}: ItemsProps) {
  return (
    <Section className={className}>
      <div className="max-w-container mx-auto flex flex-col items-center gap-6 sm:gap-20">
        <h2 className="max-w-[560px] text-center text-3xl leading-tight font-semibold sm:text-5xl sm:leading-tight">
          {title}
        </h2>
        {items !== false && items.length > 0 && (
          <div className="grid auto-rows-fr grid-cols-2 gap-0 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
            {items.map((item) => (
              <Item key={item.title}>
                <ItemTitle className="flex items-center gap-2">
                  <ItemIcon>{item.icon}</ItemIcon>
                  {item.title}
                </ItemTitle>
                <ItemDescription>{item.description}</ItemDescription>
              </Item>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}
