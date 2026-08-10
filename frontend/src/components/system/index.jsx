import React from "react";
import {
  ArrowDown, ArrowRight, ArrowUp, CaretRight, Clock, Lock, Warning, WifiSlash,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export { default as RemoteCombobox } from "./RemoteCombobox";

export function PageShell({ children, className, size = "wide" }) {
  return <div className={cn(
    "mx-auto w-full min-w-0 space-y-5 md:space-y-6",
    size === "wide" ? "max-w-[1680px]" : size === "compact" ? "max-w-5xl" : "max-w-7xl",
    className,
  )}>{children}</div>;
}

export const WorkspaceShell = PageShell;

export function PageHeader({ eyebrow, title, description, actions, children, className }) {
  return <header className={cn("flex min-w-0 flex-col gap-4 xl:flex-row xl:items-end xl:justify-between", className)}>
    <div className="min-w-0 max-w-3xl">
      {eyebrow && <div className="overline mb-1.5">{eyebrow}</div>}
      <h1 className="font-display text-[1.75rem] font-semibold leading-tight tracking-[-0.045em] sm:text-[2rem] lg:text-[2.25rem]">{title}</h1>
      {description && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p>}
      {children}
    </div>
    {actions && <div className="page-header-actions">{actions}</div>}
  </header>;
}

export const WorkspaceHeader = PageHeader;

export function Surface({ children, className, interactive = false, ...props }) {
  return <section className={cn("surface-card", interactive && "surface-interactive", className)} {...props}>{children}</section>;
}

const statusTone = {
  active: "positive", healthy: "positive", completed: "positive", paid: "positive", available: "positive", operational: "positive", open: "positive",
  watch: "warning", warning: "warning", pending: "warning", partially_paid: "warning", low: "warning", expiring: "warning", scheduled: "info",
  action_needed: "danger", failed: "danger", overdue: "danger", cancelled: "danger", inactive: "neutral", draft: "neutral", closed: "neutral",
};

export function StatusBadge({ status, label, tone, className }) {
  const normalized = String(status || "neutral").toLowerCase();
  return <span className={cn("status-badge", `status-${tone || statusTone[normalized] || "neutral"}`, className)}>{label || normalized.replaceAll("_", " ")}</span>;
}

export function MetricCard({ metric, loading = false, onClick, className }) {
  if (loading) return <Surface className={cn("min-h-[7.5rem] p-4 sm:p-5", className)}><Skeleton className="h-3 w-24" /><Skeleton className="mt-5 h-8 w-28" /><Skeleton className="mt-3 h-3 w-20" /></Surface>;
  const comparison = metric?.comparison;
  const delta = comparison?.change_percent;
  const DeltaIcon = delta > 0 ? ArrowUp : delta < 0 ? ArrowDown : null;
  const formatted = formatMetric(metric?.value, metric?.format);
  const Component = onClick ? "button" : "article";
  return <Component
    onClick={onClick}
    className={cn(
      "surface-card metric-card relative min-h-[7.5rem] overflow-hidden p-4 text-left sm:p-5",
      onClick && "surface-interactive w-full",
      className,
    )}
  >
    <div className="flex items-center justify-between gap-3">
      <span className="truncate text-xs font-semibold text-muted-foreground sm:text-sm">{metric?.label}</span>
      {metric?.tone === "warning" && <span className="h-2 w-2 shrink-0 rounded-full bg-warning ring-4 ring-warning/10" aria-label="Needs attention" />}
      {metric?.tone === "danger" && <span className="h-2 w-2 shrink-0 rounded-full bg-danger ring-4 ring-danger/10" aria-label="Action required" />}
    </div>
    <div className="mt-3 truncate font-display text-2xl font-semibold tracking-[-0.05em] sm:text-[1.8rem]">{formatted}</div>
    <div className="mt-2 min-h-4 text-[11px] text-muted-foreground">
      {delta != null && <span className={cn("inline-flex items-center gap-1 font-semibold", delta > 0 ? "text-positive" : delta < 0 ? "text-danger" : "")}>{DeltaIcon && <DeltaIcon size={12} weight="bold" />}{Math.abs(delta)}% <span className="font-normal text-muted-foreground">vs previous</span></span>}
      {comparison && delta == null && <span>No previous baseline</span>}
    </div>
  </Component>;
}

export function MetricStrip({ metrics = [], loading = false, onMetric, className }) {
  const rows = loading ? Array.from({ length: 4 }, (_, index) => ({ id: `loading-${index}` })) : metrics;
  if (!rows.length) return null;
  return <section className={cn("grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-[repeat(var(--metric-count),minmax(0,1fr))]", className)} style={{ "--metric-count": Math.min(rows.length, 6) }} aria-label="Summary metrics">
    {rows.map((metric) => <MetricCard key={metric.id} loading={loading} metric={metric} onClick={!loading && onMetric ? () => onMetric(metric) : undefined} />)}
  </section>;
}

export function ChartPanel({ title, subtitle, action, children, loading, className, fillHeight = false }) {
  return <Surface className={cn("workspace-panel flex min-w-0 flex-col", fillHeight && "h-full", className)}>
    <div className="workspace-panel-header">
      <div className="min-w-0"><h2 className="truncate font-display text-base font-semibold sm:text-lg">{title}</h2>{subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}</div>
      {action}
    </div>
    <div className="flex min-h-[220px] flex-1 flex-col p-4 sm:min-h-[280px] sm:p-5">{loading ? <Skeleton className="h-52 w-full rounded-xl sm:h-64" /> : children}</div>
  </Surface>;
}

export function InsightPanel({ title, subtitle, action, icon: Icon, children, className, fillHeight = false }) {
  return <Surface className={cn("workspace-panel flex min-w-0 flex-col", fillHeight && "h-full", className)}>
    {(title || action) && <div className="workspace-panel-header"><div className="flex min-w-0 items-start gap-3">{Icon && <span className="state-icon h-9 w-9 shrink-0 rounded-lg"><Icon size={18} /></span>}<div className="min-w-0"><h2 className="truncate font-display text-base font-semibold sm:text-lg">{title}</h2>{subtitle && <p className="mt-1 text-xs leading-5 text-muted-foreground">{subtitle}</p>}</div></div>{action}</div>}
    {children}
  </Surface>;
}

export function FilterBar({ children, className }) {
  return <div className={cn("surface-card flex min-w-0 flex-col gap-2 p-2.5 sm:flex-row sm:items-center", className)}>{children}</div>;
}

export const FilterToolbar = FilterBar;

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  primaryAction,
  secondaryAction,
  steps = [],
  variant,
  alignment = "center",
  compact = false,
  className,
}) {
  const resolvedVariant = variant || (compact ? "section" : "page");
  const resolvedPrimaryAction = primaryAction || action;
  const isInline = resolvedVariant === "inline";
  const isLeftAligned = alignment === "left" || isInline;
  const sizeClass = {
    inline: "min-h-[72px] px-4 py-3.5",
    section: "min-h-[128px] px-5 py-6",
    page: "min-h-[220px] px-6 py-8 sm:min-h-[260px] sm:py-10",
    filtered: "min-h-[104px] px-5 py-5",
  }[resolvedVariant] || "min-h-[128px] px-5 py-6";

  return <div
    data-empty-state={resolvedVariant}
    className={cn(
      "state-panel",
      sizeClass,
      isInline ? "flex-row items-start justify-start gap-3 text-left" : "flex-col",
      isLeftAligned && !isInline ? "items-start text-left" : !isInline && "items-center text-center",
      className,
    )}
  >
    {Icon && <div className={cn("state-icon shrink-0", isInline && "h-9 w-9 rounded-lg")}><Icon size={isInline ? 18 : 22} /></div>}
    <div className={cn("min-w-0", !isInline && "w-full", !isLeftAligned && "flex flex-col items-center")}>
      <h3 className={cn("font-display font-semibold", isInline ? "text-sm" : "text-lg sm:text-xl")}>{title}</h3>
      {description && <p className={cn("max-w-lg text-sm text-muted-foreground", isInline ? "mt-0.5 leading-5" : "mt-1.5 leading-6")}>{description}</p>}
      {steps.length > 0 && <ol className="mt-5 grid w-full max-w-2xl gap-2 text-left sm:grid-cols-3">
        {steps.slice(0, 3).map((step, index) => <li key={step.id || step.title || index} className="rounded-xl border bg-card px-3 py-3 text-sm">
          <span className="mr-2 inline-grid h-5 w-5 place-items-center rounded-full bg-secondary text-[10px] font-bold text-muted-foreground">{index + 1}</span>
          <span className="font-medium">{step.title || step}</span>
          {step.description && <span className="mt-1 block pl-7 text-xs leading-5 text-muted-foreground">{step.description}</span>}
        </li>)}
      </ol>}
      {(resolvedPrimaryAction || secondaryAction) && <div className={cn("flex w-full flex-col gap-2 sm:w-auto sm:flex-row", isInline ? "mt-2 sm:mt-0" : "mt-4")}>
        {resolvedPrimaryAction}
        {secondaryAction}
      </div>}
    </div>
  </div>;
}

export function ErrorState({ title = "This section could not be loaded", description = "Your existing information is unchanged. Try again when you are ready.", retry, className }) {
  return <EmptyState className={className} icon={Warning} title={title} description={description} action={retry && <Button variant="outline" onClick={retry}>Try again</Button>} />;
}

export function PermissionState({ className }) {
  return <EmptyState className={className} icon={Lock} title="You do not have access" description="Your role or data scope does not include this area. Ask an owner if your responsibilities have changed." />;
}

export function OfflineState({ retry, className }) {
  return <EmptyState className={className} icon={WifiSlash} title="You are offline" description="Reconnect to refresh live business information. Unsaved form values remain on this device." action={retry && <Button variant="outline" onClick={retry}>Check again</Button>} />;
}

export function PanelGrid({ children, mode = "natural", className, ...props }) {
  return <div className={cn("grid min-w-0 gap-5", mode === "equal" ? "items-stretch" : "items-start", className)} {...props}>{children}</div>;
}

export function ResponsiveCardGrid({ children, minWidth = "13rem", className, style, ...props }) {
  return <div
    className={cn("responsive-card-grid grid gap-3", className)}
    style={{ "--responsive-card-min": minWidth, ...style }}
    {...props}
  >{children}</div>;
}

export function PageSkeleton({ cards = 4, className }) {
  return <div className={cn("mx-auto w-full max-w-[1680px] space-y-5 p-4 sm:p-6 lg:p-8", className)} aria-label="Loading page">
    <div><Skeleton className="h-3 w-24" /><Skeleton className="mt-3 h-8 w-64 max-w-full" /><Skeleton className="mt-2 h-4 w-[30rem] max-w-full" /></div>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{Array.from({ length: cards }, (_, index) => <MetricCard key={index} loading />)}</div>
    <div className="grid gap-5 xl:grid-cols-12"><Skeleton className="h-80 rounded-2xl xl:col-span-8" /><Skeleton className="h-80 rounded-2xl xl:col-span-4" /></div>
  </div>;
}

export function DataTable({
  columns, rows, rowKey = "id", onRowClick, empty, loading, className,
  density = "balanced", mobileColumns = 4, caption,
}) {
  const rowPadding = density === "compact" ? "px-4 py-2.5" : "px-4 py-3.5";
  if (loading) return <div className={cn("surface-card overflow-hidden", className)}>{Array.from({ length: 6 }, (_, index) => <div key={index} className="flex gap-3 border-b p-3.5 last:border-0"><Skeleton className="h-9 w-9 rounded-lg" /><div className="flex-1"><Skeleton className="h-3.5 w-1/3" /><Skeleton className="mt-2 h-3 w-1/2" /></div></div>)}</div>;
  if (!rows?.length) return empty || <EmptyState compact title="No records found" description="Try changing the active filters or add the first record." />;
  return <div className={cn("surface-card overflow-hidden", className)}>
    <div className="premium-scrollbar hidden max-w-full overflow-auto lg:block">
      <table className="w-full border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 z-10"><tr className="border-b bg-surface-subtle/95 text-left text-[11px] uppercase tracking-[0.06em] text-muted-foreground backdrop-blur">{columns.map((column) => <th className={cn("whitespace-nowrap px-4 py-3 font-semibold", column.className)} key={column.key}>{column.label}</th>)}</tr></thead>
        <tbody>{rows.map((row) => <tr key={row[rowKey]} tabIndex={onRowClick ? 0 : undefined} onClick={() => onRowClick?.(row)} onKeyDown={(event) => { if (onRowClick && (event.key === "Enter" || event.key === " ")) onRowClick(row); }} className={cn("border-b last:border-0", onRowClick && "cursor-pointer transition-colors hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring")}>{columns.map((column) => <td className={cn(rowPadding, "align-middle", column.cellClassName)} key={column.key}>{column.render ? column.render(row) : row[column.key]}</td>)}</tr>)}</tbody>
      </table>
    </div>
    <div className="divide-y lg:hidden">{rows.map((row) => {
      const MobileRow = onRowClick ? "button" : "div";
      return <MobileRow type={onRowClick ? "button" : undefined} key={row[rowKey]} onClick={onRowClick ? () => onRowClick(row) : undefined} className={cn("block w-full p-4 text-left", onRowClick && "transition-colors hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring")}>{columns.slice(0, mobileColumns).map((column, index) => <div key={column.key} className={cn(index === 0 ? "font-semibold" : "mt-2 flex items-start justify-between gap-4 text-sm")}><span className={cn(index === 0 && "sr-only", "text-xs text-muted-foreground")}>{column.label}</span><span className={cn(index > 0 && "text-right")}>{column.render ? column.render(row) : row[column.key]}</span></div>)}</MobileRow>;
    })}</div>
  </div>;
}

export const SmartTable = DataTable;

export function CursorListFooter({ count = 0, hasMore, loading, error, onLoadMore, onRetry, noun = "records", className }) {
  if (!count && !hasMore && !error) return null;
  return <div className={cn("flex flex-col gap-3 border-t bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between", className)}>
    <span className="text-xs text-muted-foreground">Showing {Number(count).toLocaleString("en-IN")} {noun}</span>
    {error ? <Button variant="outline" size="sm" onClick={onRetry}>Retry loading</Button>
      : hasMore ? <Button variant="outline" size="sm" disabled={loading} onClick={onLoadMore}>{loading ? "Loading..." : "Load more"}</Button>
        : <span className="text-xs font-medium text-muted-foreground">All loaded</span>}
  </div>;
}

export function DetailHero({ avatar, eyebrow, title, subtitle, badges, metrics, actions, className }) {
  return <Surface className={cn("overflow-hidden", className)}><div className="detail-hero p-5 sm:p-6"><div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between"><div className="flex min-w-0 items-center gap-4">{avatar}<div className="min-w-0">{eyebrow && <div className="overline">{eyebrow}</div>}<h1 className="mt-1 truncate font-display text-2xl font-semibold sm:text-3xl">{title}</h1>{subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}<div className="mt-3 flex flex-wrap gap-2">{badges}</div></div></div>{actions && <div className="flex flex-wrap gap-2">{actions}</div>}</div>{metrics && <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border lg:grid-cols-4">{metrics.map((metric) => <div key={metric.label} className="bg-card p-3.5 sm:p-4"><div className="text-[11px] font-medium text-muted-foreground">{metric.label}</div><div className="mt-1.5 font-display text-xl font-semibold">{formatMetric(metric.value, metric.format)}</div></div>)}</div>}</div></Surface>;
}

export function Timeline({ items, empty }) {
  if (!items?.length) return empty || <EmptyState compact title="No activity yet" description="Relevant activity will appear here as work is completed." />;
  return <ol className="relative ml-2 border-l">{items.map((item) => <li key={item.id} className="relative pb-6 pl-6 last:pb-0"><span className="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full border-2 border-card bg-accent" /><div className="flex flex-wrap items-start justify-between gap-2"><div><div className="text-sm font-semibold">{item.title}</div>{item.detail && <p className="mt-1 text-sm leading-5 text-muted-foreground">{item.detail}</p>}</div><time className="text-[11px] text-muted-foreground">{item.time}</time></div></li>)}</ol>;
}

export function ActivityRail({ title = "Recent activity", items = [], onOpen, empty, className }) {
  return <InsightPanel title={title} className={className}><div className="divide-y">{items.length ? items.map((item) => <button key={item.id} type="button" disabled={!onOpen} onClick={() => onOpen?.(item)} className="flex w-full items-start gap-3 px-5 py-3.5 text-left transition-colors hover:bg-surface-hover disabled:pointer-events-none"><span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-secondary"><Clock size={16} /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{item.title}</span>{item.detail && <span className="mt-0.5 block line-clamp-2 text-xs leading-5 text-muted-foreground">{item.detail}</span>}</span>{onOpen && <CaretRight className="mt-2 shrink-0 text-muted-foreground" />}</button>) : empty || <EmptyState compact title="No recent activity" description="New activity will appear here." className="m-4" />}</div></InsightPanel>;
}

export function QueuePanel({ title, subtitle, items = [], renderItem, action, empty, className }) {
  return <InsightPanel title={title} subtitle={subtitle} action={action} className={className}><div className="divide-y">{items.length ? items.map((item, index) => <React.Fragment key={item.id || index}>{renderItem(item, index)}</React.Fragment>) : empty || <EmptyState compact title="Nothing waiting" description="This queue is clear." className="m-4" />}</div></InsightPanel>;
}

export function SegmentControl({ items = [], value, onChange, className }) {
  return <div className={cn("premium-scrollbar inline-flex max-w-full overflow-x-auto rounded-xl border bg-card p-1", className)}>{items.map((item) => <button type="button" key={item.value} onClick={() => onChange(item.value)} className={cn("whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors", value === item.value ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-secondary hover:text-foreground")}>{item.label}{item.count != null && <span className="ml-1.5 opacity-70">{item.count}</span>}</button>)}</div>;
}

export function SplitPane({ primary, secondary, className, primaryClassName, secondaryClassName, mode = "natural" }) {
  return <div className={cn("grid min-w-0 gap-5 xl:grid-cols-12", mode === "equal" ? "items-stretch" : "items-start", className)}><div className={cn("min-w-0 xl:col-span-8", mode === "equal" && "h-full", primaryClassName)}>{primary}</div><aside className={cn("min-w-0 xl:col-span-4", mode === "equal" && "h-full", secondaryClassName)}>{secondary}</aside></div>;
}

export function EntityRow({ avatar, title, subtitle, meta, status, action, onClick }) {
  const Component = onClick ? "button" : "div";
  return <Component type={onClick ? "button" : undefined} onClick={onClick} className={cn("flex w-full min-w-0 items-center gap-3 px-4 py-3 text-left", onClick && "transition-colors hover:bg-surface-hover")}>{avatar}<span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{title}</span>{subtitle && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{subtitle}</span>}</span>{meta && <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">{meta}</span>}{status && <StatusBadge status={status} />}{action}</Component>;
}

export function QuickActionBar({ actions, onAction, className }) {
  if (!actions?.length) return null;
  return <div className={cn("quick-action-bar", className)}>{actions.map((action, index) => <Button key={action.id} variant={index === 0 ? "default" : "outline"} onClick={() => onAction(action)}>{action.label}{index === 0 && <ArrowRight className="ml-1" />}</Button>)}</div>;
}

export const StickyActionBar = QuickActionBar;

export function DrawerForm({ open, onOpenChange, title, description, children, className }) {
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent className={cn("premium-scrollbar w-full overflow-y-auto border-l bg-card p-0 sm:max-w-xl", className)}><SheetHeader className="sticky top-0 z-10 border-b bg-card/95 px-5 py-5 pr-14 text-left backdrop-blur-xl sm:px-6"><SheetTitle className="font-display text-xl font-semibold sm:text-2xl">{title}</SheetTitle>{description && <SheetDescription className="leading-5">{description}</SheetDescription>}</SheetHeader><div className="p-5 sm:p-6">{children}</div></SheetContent></Sheet>;
}

export const ContextDrawer = DrawerForm;

export function formatMetric(value, format = "number") {
  if (value == null) return "—";
  if (format === "money") return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value) / 100);
  if (format === "bytes") {
    const bytes = Number(value);
    if (bytes < 1024) return `${bytes.toLocaleString("en-IN")} B`;
    if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  }
  if (format === "percent") return `${Number(value).toLocaleString("en-IN")}%`;
  return Number(value).toLocaleString("en-IN");
}
