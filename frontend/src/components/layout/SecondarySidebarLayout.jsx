import React, { useState } from "react";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { CaretDown } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

function renderSlot(slot, controls) {
  return typeof slot === "function" ? slot(controls) : slot;
}

export default function SecondarySidebarLayout({
  ariaLabel = "Secondary navigation",
  sidebar,
  mobileSidebar,
  mobileTitle = "Navigation",
  mobileDescription = "Choose a section",
  sidebarWidthClassName = "w-[208px]",
  sidebarClassName,
  contentClassName,
  className,
  children,
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const controls = {
    openSidebar: () => setMobileOpen(true),
    closeSidebar: () => setMobileOpen(false),
  };

  return <div
    data-secondary-sidebar-layout="true"
    className={cn("flex min-h-full min-w-0 bg-background", className)}
  >
    <aside
      aria-label={ariaLabel}
      className={cn(
        "sticky top-0 hidden h-[calc(100dvh-4rem)] shrink-0 flex-col border-r bg-card transition-[width] duration-200 lg:flex",
        sidebarWidthClassName,
        sidebarClassName,
      )}
    >
      {renderSlot(sidebar, controls)}
    </aside>

    <div className={cn("min-w-0 flex-1", contentClassName)}>
      {renderSlot(children, controls)}
    </div>

    <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
      <SheetContent side="left" className="flex w-[86vw] max-w-[320px] flex-col p-0">
        <SheetHeader className="shrink-0 border-b px-5 py-5 text-left">
          <SheetTitle>{mobileTitle}</SheetTitle>
          <SheetDescription>{mobileDescription}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1">{renderSlot(mobileSidebar ?? sidebar, controls)}</div>
      </SheetContent>
    </Sheet>
  </div>;
}

export function SecondarySidebarHeader({ title, description, action, className }) {
  return <div className={cn("flex shrink-0 items-start gap-3 border-b px-4 py-4", className)}>
    <div className="min-w-0 flex-1">
      <div className="truncate text-sm font-semibold">{title}</div>
      {description && <div className="mt-1 truncate text-xs text-muted-foreground">{description}</div>}
    </div>
    {action}
  </div>;
}

export function SecondarySidebarNav({ children, className }) {
  return <nav className={cn("premium-scrollbar min-h-0 flex-1 overflow-y-auto px-2.5 py-3", className)}>{children}</nav>;
}

export function SecondarySidebarGroup({ label, children, className }) {
  return <section className={cn("mb-4 last:mb-0", className)}>
    {label && <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</div>}
    <div className="space-y-0.5">{children}</div>
  </section>;
}

export function SecondarySidebarItem({ icon: Icon, label, active, badge, dirty, onClick, className }) {
  return <button
    type="button"
    onClick={onClick}
    aria-current={active ? "page" : undefined}
    className={cn(
      "group flex min-h-9 w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors",
      active
        ? "bg-secondary font-semibold text-foreground shadow-[inset_2px_0_0_hsl(var(--primary))]"
        : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
      className,
    )}
  >
    {Icon && <Icon size={16} className="shrink-0" weight={active ? "fill" : "regular"} />}
    <span className="min-w-0 flex-1 truncate">{label}</span>
    {dirty && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-label="Unsaved changes" />}
    {badge != null && <span className="shrink-0 rounded-full bg-background px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">{badge}</span>}
  </button>;
}

export function SecondarySidebarTrigger({ icon: Icon, label, indicator, compact = false, className, onClick }) {
  return <button
    type="button"
    onClick={onClick}
    aria-label={`Open ${label} navigation`}
    className={cn(
      "h-11 items-center rounded-xl border bg-card shadow-sm lg:hidden",
      compact ? "grid w-11 shrink-0 place-items-center" : "flex w-full gap-3 px-3 text-left",
      className,
    )}
  >
    {Icon && <Icon size={18} className="shrink-0 text-muted-foreground" />}
    {!compact && <><span className="min-w-0 flex-1 truncate text-sm font-semibold">{label}</span>{indicator}<CaretDown size={15} className="shrink-0 text-muted-foreground" /></>}
  </button>;
}
