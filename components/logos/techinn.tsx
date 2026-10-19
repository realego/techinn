import Image from "next/image";

import { cn } from "@/lib/utils";

export default function TechInnLogo({ className, priority = false }: { className?: string; priority?: boolean }) {
  return (
    <span className={cn("block w-16 shrink-0 sm:w-20", className)}>
      <Image
        src="/techinn-logo-ntxuir.png"
        alt="TechInn Hosting"
        width={1774}
        height={887}
        priority={priority}
        className="block h-auto w-full object-contain dark:mix-blend-screen"
      />
    </span>
  );
}
