"use client";

import { type VariantProps } from "class-variance-authority";
import { type ComponentProps, type ReactNode } from "react";

import { siteConfig } from "@/config/site";
import { useDemoSignedIn } from "@/lib/demo-auth";
import { useSignInHref } from "@/lib/auth-redirect";

import { Button, buttonVariants } from "./button";

export interface LinkButtonProps {
  href: string;
  children: ReactNode;
  variant?: VariantProps<typeof buttonVariants>["variant"];
  icon?: ReactNode;
  iconRight?: ReactNode;
  size?: ComponentProps<typeof Button>["size"];
}

export function LinkButton({
  href,
  children,
  variant = "default",
  icon,
  iconRight,
  size = "lg",
}: LinkButtonProps) {
  const signedIn = useDemoSignedIn();
  const signInHref = useSignInHref();
  const isGetStarted = href === siteConfig.getStartedUrl;
  const destination = isGetStarted
    ? signedIn ? "/dashboard/" : signInHref
    : href;
  return (
    <Button variant={variant} size={size} asChild>
      <a href={destination}>
        {icon}
        {isGetStarted && signedIn ? "Dashboard" : children}
        {iconRight}
      </a>
    </Button>
  );
}
