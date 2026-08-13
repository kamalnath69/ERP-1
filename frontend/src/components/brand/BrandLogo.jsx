import React from "react";

import { cn } from "@/lib/utils";

export const BRAND_LOGO_SRC = "/logo-mark.png";

export default function BrandLogo({
  showName = true,
  subtitle,
  className,
  markClassName,
  nameClassName,
  subtitleClassName,
}) {
  return <span className={cn("inline-flex min-w-0 items-center gap-2.5", className)}>
    <span className={cn(
      "grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-xl border border-black/[0.08] bg-white p-1 shadow-[0_1px_3px_rgba(15,23,42,0.12)]",
      markClassName,
    )}>
      <img
        src={BRAND_LOGO_SRC}
        alt=""
        aria-hidden="true"
        draggable="false"
        width="192"
        height="192"
        decoding="async"
        className="h-full w-full object-contain"
      />
    </span>
    {showName && <span className="min-w-0 leading-none">
      <span className={cn("block truncate text-lg font-bold tracking-[-0.035em]", nameClassName)}>Edvatiq</span>
      {subtitle && <span className={cn("mt-1 block truncate text-[9px] font-semibold uppercase tracking-[0.16em]", subtitleClassName)}>{subtitle}</span>}
    </span>}
  </span>;
}
