import Image from "next/image"

import { cn } from "@/lib/utils"

export function TechInnBrand({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex rounded-xl border border-orange-500/70 bg-slate-950 p-1 shadow-[0_0_14px_rgba(249,115,22,0.18)]", className)}>
      <Image
        alt="TechInn"
        className="h-auto w-full rounded-lg object-contain [filter:drop-shadow(0_0_1px_rgba(249,115,22,0.32))]"
        height={264}
        src="/techinn-brand.webp"
        unoptimized
        width={800}
      />
    </span>
  )
}
