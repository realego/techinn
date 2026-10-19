import Image from "next/image";

import { cn } from "@/lib/utils";

export function PromotionTag({ kind, className }: { kind: "free" | "popular"; className?: string }) {
  const popular = kind === "popular";
  return (
    <Image
      src={popular ? "/tags/popular.avif" : "/tags/free.jpg"}
      alt={popular ? "Popular" : "Free"}
      width={popular ? 626 : 599}
      height={popular ? 498 : 360}
      className={cn("h-auto shrink-0 rounded-md", popular ? "w-20" : "w-14", className)}
    />
  );
}
