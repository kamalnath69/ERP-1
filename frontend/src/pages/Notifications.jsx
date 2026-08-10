import React, { useDeferredValue, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Check, CheckCircle, Gear, Info, MagnifyingGlass, Warning, XCircle } from "@phosphor-icons/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CursorListFooter, EmptyState, ErrorState, FilterBar, PageHeader, PageShell, StatusBadge, Surface } from "@/components/system";
import { destinationPath } from "@/app/routeManifest";
import { useBusiness } from "@/contexts/BusinessContext";
import { QUERY_POLICIES } from "@/store/api/queryPolicies";
import { useGetNotificationInboxQuery, useMarkAllNotificationsReadMutation, useMarkNotificationReadMutation } from "@/features/notifications/notificationsApi";
import useCursorPagination from "@/hooks/useCursorPagination";

const filters = [
  ["all", "All"], ["unread", "Unread"], ["action_required", "Action required"], ["delivery_issues", "Delivery issues"],
];
const icons = { warning: Warning, success: CheckCircle, error: XCircle, info: Info };

export default function Notifications() {
  const navigate = useNavigate();
  const { organization } = useBusiness();
  const isCollege = organization?.industry === "college";
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const pageKey = JSON.stringify({ filter, q });
  const paging = useCursorPagination(pageKey);
  const query = useGetNotificationInboxQuery({ status: filter, q, cursor: paging.cursor, limit: 25 }, QUERY_POLICIES.live);
  const [markRead] = useMarkNotificationReadMutation();
  const [markAll, markAllState] = useMarkAllNotificationsReadMutation();
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(query.data); }, [acceptPage, query.data]);
  const items = paging.items;

  if (query.isError && !query.data) return <PageShell><ErrorState title="Notifications could not be loaded" description={query.error?.data?.detail} retry={query.refetch} /></PageShell>;

  const open = async (item) => {
    if (!item.is_read) markRead({ id: item.id, status: filter });
    const path = destinationPath(item.destination, organization?.industry);
    if (path) navigate(path);
  };
  const readAll = async () => {
    try { await markAll().unwrap(); toast.success("Notifications marked as read"); }
    catch (error) { toast.error(error?.data?.detail || "Could not update notifications"); }
  };

  return <PageShell className="reveal" size="narrow">
    <PageHeader eyebrow={isCollege ? "College inbox" : "Operational inbox"} title="Notifications" description={isCollege ? "Student support alerts, placement updates, evidence freshness, and communication delivery health." : "Updates that affect your work, reminders that need action, and communication delivery health."} actions={<div className="flex gap-2"><Button variant="outline" onClick={() => navigate("/app/me?tab=notifications")}><Gear className="mr-2" />Preferences</Button><Button variant="outline" onClick={readAll} disabled={markAllState.isLoading || !items.some((item) => !item.is_read)}><Check className="mr-2" />Mark all read</Button></div>} />
    <div className="premium-scrollbar flex gap-2 overflow-x-auto" role="tablist" aria-label="Notification filters">{filters.map(([value, label]) => <button role="tab" aria-selected={filter === value} key={value} onClick={() => setFilter(value)} className={`whitespace-nowrap rounded-full px-4 py-2 text-sm ${filter === value ? "bg-primary text-primary-foreground" : "border bg-card hover:bg-secondary"}`}>{label}</button>)}</div>
    <FilterBar><div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search notifications" /></div></FilterBar>
    {query.isLoading && !items.length ? <NotificationSkeleton /> : items.length ? <Surface className="overflow-hidden"><div className="divide-y">{items.map((item) => { const Icon = icons[item.kind] || Info; const actionable = Boolean(item.destination); return <button key={item.id} onClick={() => open(item)} disabled={!actionable && item.is_read} className={`flex w-full gap-4 p-5 text-left transition-colors hover:bg-surface-hover disabled:cursor-default ${item.is_read ? "opacity-70" : "bg-accent/[.035]"}`}><span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${item.kind === "warning" || item.kind === "error" ? "bg-destructive/10 text-danger" : "bg-secondary text-primary"}`}><Icon size={21} /></span><span className="min-w-0 flex-1"><span className="flex flex-wrap items-start justify-between gap-2"><span className="font-semibold">{item.title}</span><time className="shrink-0 text-xs text-muted-foreground">{relative(item.created_at)}</time></span><span className="mt-1 block text-sm leading-6 text-muted-foreground">{item.body || "Open this update for more information."}</span><span className="mt-3 flex flex-wrap items-center gap-2">{item.category !== "general" && <StatusBadge status={item.category === "delivery_issue" ? "failed" : "warning"} label={item.category === "delivery_issue" ? "Delivery issue" : "Action required"} />}{actionable && <span className="text-xs font-semibold text-accent">Open related work</span>}</span></span>{!item.is_read && <span className="mt-2 h-2.5 w-2.5 shrink-0 rounded-full bg-accent" aria-label="Unread" />}</button>; })}</div></Surface> : <EmptyState variant="section" alignment="left" icon={Bell} title={q ? "No notifications match this search" : emptyCopy(filter, isCollege).title} description={q ? "Try a different title or message keyword." : emptyCopy(filter, isCollege).description} />}
    {(items.length > 0 || query.data?.has_more) && <CursorListFooter count={items.length} noun="notifications" hasMore={Boolean(query.data?.has_more)} loading={query.isFetching} error={query.isError} onLoadMore={() => paging.loadMore(query.data?.next_cursor)} onRetry={query.refetch} />}
  </PageShell>;
}

function NotificationSkeleton() { return <Surface className="overflow-hidden">{[1, 2, 3, 4].map((item) => <div className="flex gap-4 border-b p-5 last:border-0" key={item}><div className="h-11 w-11 animate-pulse rounded-xl bg-secondary" /><div className="flex-1"><div className="h-4 w-1/3 animate-pulse rounded bg-secondary" /><div className="mt-3 h-3 w-2/3 animate-pulse rounded bg-secondary" /></div></div>)}</Surface>; }
function emptyCopy(filter, isCollege = false) { return ({ unread: { title: "Nothing unread", description: "You have reviewed every current notification." }, action_required: { title: "No actions waiting", description: "There are no notification-driven tasks requiring your attention." }, delivery_issues: { title: "No delivery issues", description: "Recent communications have no unresolved delivery failures." } }[filter] || { title: "You are all caught up", description: isCollege ? "Important student, academic, and placement updates will appear here." : "Important business updates and reminders will appear here." }); }
function relative(value) { const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000); if (seconds < 60) return "Just now"; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`; if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`; return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(value)); }
