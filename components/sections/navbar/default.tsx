"use client";

import { type VariantProps } from "class-variance-authority";
import { ChevronDown, Menu } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";

import { CartMenu } from "@/components/cart-menu";
import { emailHostingPlans, type HostingService,planSelectionHref, webHostingPlans } from "@/config/hosting-plans";
import { signOutDemo, useDemoSignedIn } from "@/lib/demo-auth";
import { useSignInHref } from "@/lib/auth-redirect";
import { cn } from "@/lib/utils";

import TechInnLogo from "../../logos/techinn";
import { Button, buttonVariants } from "../../ui/button";
import {
  Navbar as NavbarComponent,
  NavbarLeft,
  NavbarRight,
} from "../../ui/navbar";
import Navigation from "../../ui/navigation";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "../../ui/sheet";

interface NavbarLink {
  text: string;
  href: string;
}

interface NavbarActionProps {
  text: string;
  href: string;
  variant?: VariantProps<typeof buttonVariants>["variant"];
  icon?: ReactNode;
  iconRight?: ReactNode;
  isButton?: boolean;
}

interface NavbarProps {
  logo?: ReactNode;
  name?: string;
  homeUrl?: string;
  mobileLinks?: NavbarLink[];
  actions?: NavbarActionProps[];
  showNavigation?: boolean;
  customNavigation?: ReactNode;
  className?: string;
}

export default function Navbar({
  logo = <TechInnLogo priority className="w-12 sm:w-14" />,
  name = "TechInn Hosting",
  homeUrl = "/",
  mobileLinks = [
    { text: "Web Hosting", href: "/shop/?service=web" },
    { text: "Email Hosting", href: "/shop/?service=email" },
    { text: "Domains", href: "/domains/" },
    { text: "Shop", href: "/shop/" },
    { text: "How to", href: "/how-to/" },
  ],
  actions,
  showNavigation = true,
  customNavigation,
  className,
}: NavbarProps) {
  const [isScrolled, setIsScrolled] = useState(false);
  const signedIn = useDemoSignedIn();
  const signInHref = useSignInHref();
  const displayedActions = actions ?? [
    signedIn
      ? { text: "Sign out", href: "/", isButton: false }
      : { text: "Sign in", href: signInHref, isButton: false },
    signedIn
      ? { text: "Dashboard", href: "/dashboard/", isButton: true }
      : { text: "Get Started", href: signInHref, isButton: true },
  ];
  const onActionClick = (text: string) => {
    if (text === "Sign out") signOutDemo();
  };

  useEffect(() => {
    const updateScrollState = () => setIsScrolled(window.scrollY > 12);
    updateScrollState();
    window.addEventListener("scroll", updateScrollState, { passive: true });
    return () => window.removeEventListener("scroll", updateScrollState);
  }, []);

  return (
    <header className={cn("sticky top-0 z-50 -mb-4 px-4 pb-4", className)}>
      <div
        className={cn(
          "fade-bottom absolute left-0 h-24 w-full transition-colors duration-200",
          isScrolled
            ? "bg-background/20 backdrop-blur-sm dark:bg-background/25 lg:border-b lg:border-border/60 lg:bg-background/90 lg:backdrop-blur-xl lg:dark:bg-background/90"
            : "bg-background/20 backdrop-blur-sm dark:bg-background/25 lg:backdrop-blur-[2px]",
        )}
      ></div>
      <div className="max-w-container relative mx-auto">
        <NavbarComponent>
          <NavbarLeft>
            <a
              href={homeUrl}
              aria-label={name + " home"}
              className="flex shrink-0 items-center gap-2 whitespace-nowrap text-base font-bold sm:text-xl"
            >
              {logo}
            </a>
            {showNavigation && (customNavigation || <Navigation />)}
          </NavbarLeft>
          <NavbarRight className="gap-1.5 sm:gap-4">
            <CartMenu />
            {displayedActions.map((action) =>
              action.isButton ? (
                <Button
                  key={`${action.href}-${action.text}`}
                  variant={action.variant || "default"}
                  asChild
                >
                  <a href={action.href} onClick={() => onActionClick(action.text)}>
                    {action.icon}
                    {action.text}
                    {action.iconRight}
                  </a>
                </Button>
              ) : (
                <a
                  key={`${action.href}-${action.text}`}
                  href={action.href}
                  onClick={() => onActionClick(action.text)}
                  className="hidden whitespace-nowrap text-sm lg:block"
                >
                  {action.text}
                </a>
              ),
            )}
            <Sheet>
              <SheetTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0 lg:hidden"
                >
                  <Menu className="size-5" />
                  <span className="sr-only">Toggle navigation menu</span>
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="overflow-y-auto">
                <SheetTitle className="sr-only">Navigation menu</SheetTitle>
                <nav className="grid gap-6 text-lg font-medium">
                  <a
                    href={homeUrl}
                    aria-label={name + " home"}
                    className="flex items-center gap-2 text-xl font-bold"
                  >
                    {logo}
                    <span>{name}</span>
                  </a>
                  {mobileLinks.map((link) =>
                    link.href === "/shop/?service=web" || link.href === "/shop/?service=email" ? (
                      <MobilePlanGroup
                        key={link.href}
                        service={link.href === "/shop/?service=web" ? "web" : "email"}
                      />
                    ) : (
                      <a
                        key={`${link.href}-${link.text}`}
                        href={link.href}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        {link.text}
                      </a>
                    ),
                  )}
                  {displayedActions.map((action) => (
                    <a
                      key={`${action.href}-${action.text}`}
                      href={action.href}
                      onClick={() => onActionClick(action.text)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      {action.text}
                    </a>
                  ))}
                </nav>
              </SheetContent>
            </Sheet>
          </NavbarRight>
        </NavbarComponent>
      </div>
    </header>
  );
}

function MobilePlanGroup({ service }: { service: HostingService }) {
  const isWeb = service === "web";
  const plans = isWeb ? webHostingPlans : emailHostingPlans;
  const href = "/shop/?service=" + service;
  return (
    <details className="group">
      <summary className="text-muted-foreground hover:text-foreground flex cursor-pointer list-none items-center justify-between">
        {isWeb ? "Web Hosting" : "Email Hosting"}
        <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-3 flex flex-col gap-2 border-l pl-4 text-sm">
        <a href={href} className="text-foreground font-medium">View all plans</a>
        {plans.map((plan) => (
          <a
            key={plan.id}
            href={planSelectionHref(service, plan.id)}
            className="hover:bg-accent rounded-md px-2 py-2"
          >
            <span className="flex justify-between gap-2 font-medium">
              <span>Choose {plan.name}</span>
              <span>${plan.price.toFixed(2)}/mo</span>
            </span>
          </a>
        ))}
      </div>
    </details>
  );
}
