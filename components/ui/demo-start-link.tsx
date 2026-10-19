"use client";

import { ArrowRightIcon } from "lucide-react";

import { useDemoSignedIn } from "@/lib/demo-auth";
import { useSignInHref } from "@/lib/auth-redirect";

export function DemoStartLink() {
  const signedIn = useDemoSignedIn();
  const signInHref = useSignInHref();
  return (
    <a
      href={signedIn ? "/dashboard/" : signInHref}
      className="flex items-center gap-1"
    >
      {signedIn ? "Dashboard" : "Get started"}
      <ArrowRightIcon className="size-3" />
    </a>
  );
}
