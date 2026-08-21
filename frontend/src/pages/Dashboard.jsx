import React, { useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import {
  ArrowDown, ArrowRight, ArrowUp, ChartBar, CheckCircle, Clock,
  DotsSixVertical, Eye, EyeSlash, Gear, UsersThree,
} from "@phosphor-icons/react";

import { destinationPath } from "@/app/routeManifest";
import TrendChart from "@/components/dashboard/TrendChart";
import PlacementDashboard from "@/components/college/PlacementDashboard";
import { EntityAvatar } from "@/components/entities/EntityProfile";
import {
  ChartPanel, DrawerForm, EmptyState, ErrorState, InsightPanel,
  DashboardBand, DashboardCanvas, DashboardLanes, DashboardSkeleton,
  PageHeader, PageShell, SegmentControl, StatusBadge,
  formatMetric,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { useGetDashboardWorkspaceQuery, useSaveMyPreferenceMutation } from "@/store/api/workspaceApi";
import {
  resetDashboardLayout, selectDashboardLayout, selectDashboardLayouts, setDashboardLayout,
} from "@/store/slices/preferencesSlice";
import { cn } from "@/lib/utils";

const CHART_KINDS = new Set(["line_chart", "bar_chart", "donut_chart"]);

export default function Dashboard() {
  const { organization } = useBusiness();
  if (organization?.industry === "college") return <PlacementDashboard />;
  return <BusinessDashboard />;
}

function BusinessDashboard() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { organization, locationId, location } = useBusiness();
  const [range, setRange] = useState(30);
  const [customizing, setCustomizing] = useState(false);
  const [savePreference] = useSaveMyPreferenceMutation();
  const query = useGetDashboardWorkspaceQuery(
    { locationId, range },
    withSkip(QUERY_POLICIES.operational, !locationId),
  );
  const data = query.data;
  const layoutKey = `${organization?.industry || "business"}:${(data?.roles || []).join("+") || "default"}`;
  const savedLayout = useSelector(selectDashboardLayout(layoutKey));
  const allLayouts = useSelector(selectDashboardLayouts);
  const arrangedWidgets = useMemo(
    () => arrangeWidgets(data?.widgets || [], savedLayout),
    [data?.widgets, savedLayout],
  );
  const roleText = (data?.roles || []).map(humanize).join(" + ");

  if (query.isLoading && !data) return <DashboardSkeleton />;
  if (query.isError && !data) return <PageShell><ErrorState title="Your dashboard could not be loaded" description={query.error?.data?.detail || "Live business information is temporarily unavailable."} retry={query.refetch} /></PageShell>;

  const go = (destination) => {
    const path = destinationPath(destination, organization?.industry);
    if (path) navigate(path);
  };
  const chartWidgets = arrangedWidgets.filter((widget) => CHART_KINDS.has(widget.kind));
  const workWidget = arrangedWidgets.find((widget) => widget.kind === "work_queue");
  const attentionWidget = arrangedWidgets.find((widget) => widget.kind === "attention");
  const hasWork = Boolean(workWidget?.data?.length);
  const hasAttention = Boolean(attentionWidget?.data?.length);
  const otherWidgets = arrangedWidgets.filter((widget) => !CHART_KINDS.has(widget.kind) && !["work_queue", "attention"].includes(widget.kind));
  const primaryMetrics = selectPrimaryMetrics(data?.metrics || [], data?.industry || organization?.industry);
  const primaryIds = new Set(primaryMetrics.map((metric) => metric.id));
  const secondaryMetrics = (data?.metrics || []).filter((metric) => !primaryIds.has(metric.id));
  const profile = resolveBusinessDashboardProfile(data?.roles || []);
  const hasSavedLayout = Boolean(savedLayout?.order?.length || savedLayout?.hidden?.length);
  const sectionOrder = resolveBusinessSectionOrder(arrangedWidgets, profile, hasSavedLayout);

  const sections = {
    analytics: <DashboardBand key="analytics" as="section" aria-label="Business analytics">
      <AnalyticsGrid widgets={chartWidgets} secondaryMetrics={secondaryMetrics} go={go} />
    </DashboardBand>,
    execution: (workWidget || attentionWidget) ? <DashboardBand key="execution" as="section" aria-label="Today's execution">
      <ExecutionGrid workWidget={workWidget} attentionWidget={attentionWidget} go={go} profile={profile} hasWork={hasWork} hasAttention={hasAttention} />
    </DashboardBand> : null,
    other: otherWidgets.length ? <DashboardBand key="other" as="section" aria-label="More business information">
      <SupportingWidgets widgets={otherWidgets} go={go} />
    </DashboardBand> : null,
  };

  return <PageShell className="reveal pb-10" data-testid="dashboard-page">
    <DashboardCanvas data-dashboard-profile={profile}>
      <DashboardBand as="div">
        <PageHeader
          eyebrow={`${location?.name || organization?.name || "Business"} / ${roleText || "Workspace"}`}
          title={`${greeting()}, ${user?.first_name}.`}
          className="lg:flex-row lg:items-start lg:justify-between xl:items-start"
          actions={<div role="group" aria-label="Dashboard period" className="flex max-w-full items-center gap-2"><SegmentControl value={range} onChange={setRange} items={[7, 30, 90].map((days) => ({ value: days, label: `${days} days` }))} /><Button variant="outline" size="icon" className="shrink-0" aria-label="Customize dashboard" onClick={() => setCustomizing(true)}><Gear /></Button></div>}
        />
      </DashboardBand>

      <DashboardBand as="div"><MetricRibbon metrics={primaryMetrics} go={go} /></DashboardBand>
      {sectionOrder.map((section) => sections[section])}
    </DashboardCanvas>

    <DashboardCustomizer
      open={customizing}
      onOpenChange={setCustomizing}
      widgets={data?.widgets || []}
      layout={savedLayout}
      onSave={(layout) => {
        const layouts = { ...allLayouts, [layoutKey]: layout };
        dispatch(setDashboardLayout({ key: layoutKey, layout }));
        savePreference({ namespace: "dashboard", value: { layouts } });
      }}
      onReset={() => {
        const layouts = { ...allLayouts };
        delete layouts[layoutKey];
        dispatch(resetDashboardLayout(layoutKey));
        savePreference({ namespace: "dashboard", value: { layouts } });
      }}
    />
  </PageShell>;
}

function MetricRibbon({ metrics, go }) {
  if (!metrics.length) return null;
  return <section className="surface-card reveal-stagger overflow-hidden" aria-label="Key business metrics">
    <div className="dashboard-metric-grid gap-px bg-border">
      {metrics.map((metric) => {
        const change = metric.comparison?.change_percent;
        const DeltaIcon = change > 0 ? ArrowUp : change < 0 ? ArrowDown : null;
        const Component = metric.destination ? "button" : "article";
        return <Component
          key={metric.id}
          data-dashboard-metric={metric.id}
          type={metric.destination ? "button" : undefined}
          onClick={metric.destination ? () => go(metric.destination) : undefined}
          className={cn(
            "group min-w-0 bg-card px-4 py-4 text-left sm:px-5 sm:py-5",
            metric.destination && "transition-colors hover:bg-surface-hover",
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[11px] font-semibold text-muted-foreground sm:text-xs">{metric.label}</span>
            {["warning", "danger"].includes(metric.tone) && <span className={cn("h-2 w-2 shrink-0 rounded-full ring-4", metric.tone === "danger" ? "bg-danger ring-danger/10" : "bg-warning ring-warning/10")} />}
          </div>
          <div className="mt-2 flex items-end justify-between gap-3">
            <span className="truncate font-display text-2xl font-semibold tracking-[-0.05em] sm:text-[1.7rem]">{formatMetric(metric.value, metric.format)}</span>
            {metric.destination && <ArrowRight size={15} className="mb-1 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />}
          </div>
          {change != null && <span className={cn("mt-1.5 inline-flex items-center gap-1 text-[10px] font-semibold", change > 0 ? "text-positive" : change < 0 ? "text-danger" : "text-muted-foreground")}>{DeltaIcon && <DeltaIcon size={11} weight="bold" />}{Math.abs(change)}% <span className="font-normal text-muted-foreground">vs prior</span></span>}
        </Component>;
      })}
    </div>
  </section>;
}

function AnalyticsGrid({ widgets, secondaryMetrics, go }) {
  const populatedWidgets = widgets.filter(hasChartData);
  if (!populatedWidgets.length && !secondaryMetrics.length) return <EmptyState variant="section" alignment="left" icon={ChartBar} title="Insights will build from your activity" description="Record sales, visits, appointments, or stock movement to begin seeing business trends here." />;
  const cards = populatedWidgets.map((widget) => <DashboardWidget key={widget.id} widget={widget} go={go} />);
  if (!cards.length) return <DashboardLanes primary={<OperationalSnapshot metrics={secondaryMetrics} go={go} wide />} />;
  const primaryCount = Math.ceil(cards.length / 2);
  const primary = cards.slice(0, primaryCount);
  const supporting = cards.slice(primaryCount);
  if (secondaryMetrics.length) supporting.push(<OperationalSnapshot key="operational-snapshot" metrics={secondaryMetrics} go={go} wide={cards.length === 2} />);
  return <DashboardLanes primary={primary} supporting={supporting} />;
}

function OperationalSnapshot({ metrics, go, className, wide }) {
  return <InsightPanel className={cn("dashboard-card", className)} title="Operational snapshot" subtitle="Additional live measures, kept compact" icon={ChartBar}>
    <div className={cn(wide && "sm:grid sm:grid-cols-2")}>
      {metrics.map((metric, index) => {
        const Row = metric.destination ? "button" : "div";
        const change = metric.comparison?.change_percent;
        return <Row type={metric.destination ? "button" : undefined} key={metric.id} onClick={metric.destination ? () => go(metric.destination) : undefined} className={cn("flex w-full items-center gap-3 border-b px-5 py-3.5 text-left last:border-b-0", metric.destination && "transition-colors hover:bg-surface-hover", wide && index % 2 === 0 && "sm:border-r")}>
          <span className={cn("h-2 w-2 shrink-0 rounded-full ring-4", metric.tone === "warning" ? "bg-warning ring-warning/10" : "bg-positive ring-positive/10")} />
          <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{metric.label}</span>{change != null && <span className={cn("mt-0.5 block text-[10px]", change > 0 ? "text-positive" : change < 0 ? "text-danger" : "text-muted-foreground")}>{change > 0 ? "+" : ""}{change}% vs prior period</span>}</span>
          <span className="shrink-0 font-display text-lg font-semibold">{formatMetric(metric.value, metric.format)}</span>
          {metric.destination && <ArrowRight size={14} className="shrink-0 text-muted-foreground" />}
        </Row>;
      })}
    </div>
  </InsightPanel>;
}

function ExecutionGrid({ workWidget, attentionWidget, go, profile, hasWork, hasAttention }) {
  if (!hasWork && !hasAttention) return <EmptyState variant="inline" alignment="left" icon={CheckCircle} title="You are caught up" description="There are no assigned tasks or client signals that need attention right now." />;
  const work = hasWork ? <DashboardWidget key="work" widget={workWidget} go={go} compact /> : null;
  const attention = hasAttention ? <DashboardWidget key="attention" widget={attentionWidget} go={go} /> : null;
  const leadWithAttention = profile === "leadership";
  return <DashboardLanes
    primary={leadWithAttention ? (attention || work) : (work || attention)}
    supporting={hasWork && hasAttention ? (leadWithAttention ? work : attention) : null}
  />;
}

function SupportingWidgets({ widgets, go }) {
  const splitAt = Math.ceil(widgets.length / 2);
  const render = (widget) => <DashboardWidget key={widget.id} widget={widget} go={go} />;
  return <DashboardLanes
    primary={widgets.slice(0, splitAt).map(render)}
    supporting={widgets.slice(splitAt).map(render)}
  />;
}

function DashboardWidget({ widget, go, className, compact = false }) {
  if (CHART_KINDS.has(widget.kind)) {
    const chartType = widget.kind === "donut_chart" ? "donut" : widget.kind === "bar_chart" ? "bar" : "area";
    const hasData = hasChartData(widget);
    return <ChartPanel
      className={cn("dashboard-card", className)}
      title={widget.title}
      subtitle={widget.subtitle}
      action={widget.destination && <Button variant="ghost" size="sm" onClick={() => go(widget.destination)}>Details<ArrowRight /></Button>}
    >
      {hasData ? <TrendChart data={widget.data} format={widget.format} type={chartType} xKey={widget.x_key || "date"} series={widget.series} height="clamp(14rem, 54cqi, 18rem)" ariaLabel={`${widget.title}. ${widget.subtitle || "Business performance"}`} /> : <EmptyState variant="section" icon={ChartBar} title={widget.empty?.title || `No ${widget.title.toLowerCase()} data`} description={widget.empty?.message || "This view will fill as activity is recorded."} className="border-0 bg-transparent" />}
    </ChartPanel>;
  }

  if (widget.kind === "work_queue") return <InsightPanel className={cn("dashboard-card", className)} title={widget.title} subtitle={widget.subtitle}>
    {widget.data?.length ? <div className="flex-1 divide-y">{widget.data.slice(0, compact ? 6 : 8).map((item) => <button type="button" key={`${item.source}:${item.id}`} onClick={() => go(item.destination)} className="flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-surface-hover sm:px-5">
      <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-secondary text-muted-foreground"><Clock size={16} /></span>
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-2"><span className="truncate text-sm font-semibold">{item.title}</span><StatusBadge status={item.status} /></span>
        <span className="mt-1 line-clamp-2 block text-xs leading-5 text-muted-foreground">{item.reason}</span>
        <span className="mt-1.5 block text-[10px] font-medium text-muted-foreground">{item.source}{item.due_at ? ` / ${formatDue(item.due_at)}` : ""}</span>
      </span>
      <ArrowRight className="mt-2 shrink-0 text-muted-foreground" />
    </button>)}</div> : <EmptyState compact icon={CheckCircle} title={widget.empty?.title} description={widget.empty?.message} className="m-4" />}
  </InsightPanel>;

  if (widget.kind === "attention") return <InsightPanel className={cn("dashboard-card", className)} title={widget.title} subtitle={widget.subtitle}>
    {widget.data?.length ? <div className="divide-y">{widget.data.map((item) => <button type="button" key={item.id} onClick={() => go(item.destination)} className="flex w-full min-w-0 items-start gap-3 bg-card p-4 text-left transition-colors hover:bg-surface-hover">
      <EntityAvatar name={item.client?.name} kind="client" className="h-10 w-10 rounded-xl text-xs" />
      <span className="min-w-0 flex-1"><span className="flex items-center gap-2"><span className="truncate text-sm font-semibold">{item.client?.name}</span><span className={cn("h-2 w-2 shrink-0 rounded-full", item.state === "action_needed" ? "bg-danger" : item.state === "watch" ? "bg-warning" : "bg-positive")} /></span><span className="mt-1 block text-xs font-semibold">{item.title}</span><span className="mt-1 line-clamp-2 block text-[11px] leading-5 text-muted-foreground">{item.reason}</span></span>
    </button>)}</div> : <EmptyState compact icon={UsersThree} title={widget.empty?.title} description={widget.empty?.message} className="m-4" />}
  </InsightPanel>;
  return null;
}

function DashboardCustomizer({ open, onOpenChange, widgets, layout, onSave, onReset }) {
  const [draft, setDraft] = useState(() => normalizeLayout(widgets, layout));
  const [dragged, setDragged] = useState(null);
  React.useEffect(() => { if (open) setDraft(normalizeLayout(widgets, layout)); }, [open, widgets, layout]);
  const move = (index, delta) => {
    const next = [...draft.order];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setDraft({ ...draft, order: next });
  };
  const moveTo = (sourceId, targetId) => {
    if (!sourceId || sourceId === targetId) return;
    const next = [...draft.order];
    const source = next.indexOf(sourceId);
    const target = next.indexOf(targetId);
    next.splice(target, 0, next.splice(source, 1)[0]);
    setDraft({ ...draft, order: next });
  };
  const toggle = (id) => setDraft({ ...draft, hidden: draft.hidden.includes(id) ? draft.hidden.filter((item) => item !== id) : [...draft.hidden, id] });
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Customize Home" description="Drag, reorder, or hide panels available to your role. Metrics remain permission controlled.">
    <div className="space-y-2">{draft.order.map((id, index) => {
      const widget = widgets.find((item) => item.id === id);
      if (!widget) return null;
      const hidden = draft.hidden.includes(id);
      return <div
        key={id}
        draggable
        onDragStart={() => setDragged(id)}
        onDragEnd={() => setDragged(null)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={() => moveTo(dragged, id)}
        className={cn("flex items-center gap-3 rounded-xl border bg-card p-3 transition-opacity", dragged === id && "opacity-50")}
      >
        <DotsSixVertical className="cursor-grab text-muted-foreground" />
        <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{widget.title}</div><div className="truncate text-xs text-muted-foreground">{widget.subtitle}</div></div>
        <button type="button" onClick={() => toggle(id)} aria-label={hidden ? `Show ${widget.title}` : `Hide ${widget.title}`} className="grid h-8 w-8 place-items-center rounded-lg border hover:bg-secondary">{hidden ? <EyeSlash /> : <Eye />}</button>
        <div className="flex"><button type="button" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Move ${widget.title} up`} className="grid h-8 w-7 place-items-center rounded-l-lg border disabled:opacity-30"><ArrowUp /></button><button type="button" disabled={index === draft.order.length - 1} onClick={() => move(index, 1)} aria-label={`Move ${widget.title} down`} className="grid h-8 w-7 place-items-center rounded-r-lg border border-l-0 disabled:opacity-30"><ArrowDown /></button></div>
      </div>;
    })}</div>
    <div className="mt-6 flex justify-between gap-3"><Button variant="ghost" onClick={() => { onReset(); onOpenChange(false); }}>Restore defaults</Button><Button onClick={() => { onSave(draft); onOpenChange(false); }}>Save layout</Button></div>
  </DrawerForm>;
}

function selectPrimaryMetrics(metrics, industry) {
  const preferences = {
    gym: ["collections_today", "active_clients", "checkins_today", "renewals_due", "current_occupancy"],
    salon: ["collections_today", "appointments_today", "active_clients", "new_clients"],
    clinic: ["collections_today", "patient_queue", "pending_labs", "active_clients"],
  }[industry] || ["collections_today", "active_clients", "appointments_today", "outstanding"];
  const selected = [];
  const add = (metric) => { if (metric && !selected.some((item) => item.id === metric.id) && selected.length < 4) selected.push(metric); };
  add(metrics.find((metric) => metric.tone === "warning" && Number(metric.value || 0) > 0));
  preferences.forEach((id) => add(metrics.find((metric) => metric.id === id)));
  metrics.forEach(add);
  return selected;
}

const BUSINESS_LEADERSHIP_ROLES = new Set([
  "owner", "business-owner", "administrator", "admin", "manager", "finance-manager", "accountant", "auditor",
]);

export function resolveBusinessDashboardProfile(roles = []) {
  const normalized = roles.map((role) => String(role || "").trim().toLowerCase().replaceAll("_", "-").replaceAll(" ", "-"));
  return normalized.some((role) => BUSINESS_LEADERSHIP_ROLES.has(role)) ? "leadership" : "operations";
}

export function resolveBusinessSectionOrder(widgets, profile, hasSavedLayout) {
  const defaults = profile === "leadership"
    ? ["analytics", "execution", "other"]
    : ["execution", "analytics", "other"];
  if (!hasSavedLayout) return defaults;
  const ordered = [];
  widgets.forEach((widget) => {
    const section = CHART_KINDS.has(widget.kind)
      ? "analytics"
      : ["work_queue", "attention"].includes(widget.kind) ? "execution" : "other";
    if (!ordered.includes(section)) ordered.push(section);
  });
  return [...ordered, ...defaults.filter((section) => !ordered.includes(section))];
}

function hasChartData(widget) {
  if (!Array.isArray(widget.data) || !widget.data.length) return false;
  const keys = Array.isArray(widget.series) && widget.series.length
    ? widget.series.map((item) => item.key)
    : [widget.format === "money" ? "value_paise" : "value"];
  return widget.data.some((row) => keys.some((key) => Number(row?.[key] || 0) !== 0));
}

function normalizeLayout(widgets, layout) {
  const ids = widgets.map((widget) => widget.id);
  return {
    order: [...(layout?.order || []).filter((id) => ids.includes(id)), ...ids.filter((id) => !layout?.order?.includes(id))],
    hidden: (layout?.hidden || []).filter((id) => ids.includes(id)),
  };
}

function arrangeWidgets(widgets, layout) {
  const normalized = normalizeLayout(widgets, layout);
  return normalized.order.filter((id) => !normalized.hidden.includes(id)).map((id) => widgets.find((widget) => widget.id === id)).filter(Boolean);
}

function greeting() { const hour = new Date().getHours(); return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"; }
function humanize(value) { return String(value).replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function formatDue(value) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(value)); }
