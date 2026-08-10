import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { CalendarBlank, Clock, Scissors, UserPlus, UsersThree } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, EmptyState, ErrorState, MetricStrip, PageHeader, PageShell, ResponsiveCardGrid, SegmentControl, StatusBadge, Surface } from "@/components/system";
import { EntityAvatar, EntityProfileLink } from "@/components/entities/EntityProfile";
import { profileRef } from "@/lib/profileNavigation";
import {
  useGetSalonBookingsQuery, useGetSalonFollowUpsQuery, useGetSalonOverviewQuery,
  useGetSalonRebookingQuery, useGetSalonSummaryQuery,
} from "@/features/salon/salonApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";

const sections = ["overview", "bookings", "walk-ins", "clients", "services", "staff", "preferences", "follow-ups", "performance"];

export default function Salon() {
  const { can } = useAuth();
  const { locationId } = useBusiness();
  const route = useLocation();
  const navigate = useNavigate();
  const active = sections.includes(route.pathname.split("/").pop()) ? route.pathname.split("/").pop() : "overview";
  const [range, setRange] = useState(30);
  const overviewQuery = useGetSalonOverviewQuery({ locationId, range }, withSkip(QUERY_POLICIES.operational, !locationId || active !== "overview"));
  const bookingsQuery = useGetSalonBookingsQuery({ locationId, range: 30 }, withSkip(QUERY_POLICIES.operational, !locationId || !["bookings", "walk-ins"].includes(active)));
  const rebookingQuery = useGetSalonRebookingQuery({ locationId, range: 90 }, withSkip(QUERY_POLICIES.collaborative, !locationId || active !== "preferences"));
  const followUpsQuery = useGetSalonFollowUpsQuery({ locationId, range: 30 }, withSkip(QUERY_POLICIES.collaborative, !locationId || active !== "follow-ups"));
  const performanceQuery = useGetSalonSummaryQuery({ locationId, range }, withSkip(QUERY_POLICIES.operational, !locationId || active !== "performance"));
  const data = overviewQuery.data;
  if (overviewQuery.isError && !data && active === "overview") return <PageShell><ErrorState title="Salon workspace could not be loaded" description={overviewQuery.error?.data?.detail} retry={overviewQuery.refetch} /></PageShell>;
  const summary = active === "performance" ? performanceQuery.data?.summary : data?.summary;
  const metrics = summary ? [
    { id: "bookings", label: "Bookings today", value: summary.bookings_today },
    { id: "walkins", label: "Walk-ins today", value: summary.walk_ins_today },
    { id: "rebooking", label: "Rebooking opportunities", value: summary.rebooking_opportunities, tone: summary.rebooking_opportunities ? "warning" : "neutral" },
    ...(summary.revenue_paise == null ? [] : [{ id: "revenue", label: `${range}-day revenue`, value: summary.revenue_paise, format: "money" }]),
  ] : [];
  const overviewBookings = data?.bookings?.slice(0, 6) || [];
  const overviewRebooking = data?.rebooking?.slice(0, 6) || [];
  const overviewFollowUps = data?.follow_ups?.slice(0, 6) || [];
  const hasOverviewWork = Boolean(overviewBookings.length || overviewRebooking.length || overviewFollowUps.length);
  const changeSection = (value) => navigate(value === "overview" ? "/app/salon" : `/app/salon/${value}`);
  return <PageShell className="reveal">
    <PageHeader eyebrow="Salon workspace" title="Today in your salon" description="Bookings, walk-ins, client preferences, rebooking, and follow-ups in one operational view." actions={<>{can("appointments.manage") && <Button variant="outline" onClick={() => navigate("/app/calendar?new=1&source=walk_in")}><UserPlus className="mr-2" />Start walk-in</Button>}{can("appointments.manage") && <Button onClick={() => navigate("/app/calendar?new=1")}><CalendarBlank className="mr-2" />New booking</Button>}</>} />
    <Tabs value={active} onValueChange={changeSection}><TabsList className="premium-scrollbar h-auto w-full justify-start overflow-x-auto rounded-xl bg-secondary/60 p-1">{sections.map((section) => <TabsTrigger key={section} value={section} className="whitespace-nowrap capitalize">{section.replace("-", " ")}</TabsTrigger>)}</TabsList>
      <TabsContent value="overview" className="mt-6 space-y-5"><div className="flex justify-end"><SegmentControl items={[7, 30, 90].map((days) => ({ value: days, label: `${days} days` }))} value={range} onChange={setRange} /></div><MetricStrip metrics={metrics} loading={overviewQuery.isLoading && !summary} />{overviewQuery.isLoading || hasOverviewWork ? <><ResponsiveCardGrid minWidth="28rem" className="gap-5">{(overviewQuery.isLoading || overviewBookings.length > 0) && <BookingPanel bookings={overviewBookings} loading={overviewQuery.isLoading} navigate={navigate} />}{(overviewQuery.isLoading || overviewRebooking.length > 0) && <RebookingPanel rows={overviewRebooking} loading={overviewQuery.isLoading} />}</ResponsiveCardGrid>{(overviewQuery.isLoading || overviewFollowUps.length > 0) && <FollowupPanel rows={overviewFollowUps} loading={overviewQuery.isLoading} />}</> : <EmptyState variant="section" alignment="left" icon={Scissors} title="Today is ready to be scheduled" description="There are no upcoming bookings, rebooking gaps, or open follow-ups in this view." primaryAction={can("appointments.manage") ? <Button onClick={() => navigate("/app/calendar?new=1")}><CalendarBlank className="mr-2" />New booking</Button> : null} steps={[{ title: "Book clients" }, { title: "Complete services" }, { title: "Follow up" }]} />}</TabsContent>
      <TabsContent value="bookings" className="mt-6">{bookingsQuery.isError && !bookingsQuery.data ? <ErrorState title="Bookings could not be loaded" description={bookingsQuery.error?.data?.detail} retry={bookingsQuery.refetch} /> : <DataTable loading={bookingsQuery.isLoading} rows={bookingsQuery.data?.bookings || []} columns={bookingColumns} empty={<EmptyState variant="page" alignment="left" icon={CalendarBlank} title="No upcoming bookings" description="Create the first booking to coordinate the client, service, stylist, and time." primaryAction={can("appointments.manage") ? <Button onClick={() => navigate("/app/calendar?new=1")}>New booking</Button> : null} steps={[{ title: "Choose client" }, { title: "Select service" }, { title: "Confirm time" }]} />} />}</TabsContent>
      <TabsContent value="walk-ins" className="mt-6">{bookingsQuery.isError && !bookingsQuery.data ? <ErrorState title="Walk-ins could not be loaded" description={bookingsQuery.error?.data?.detail} retry={bookingsQuery.refetch} /> : <DataTable loading={bookingsQuery.isLoading} rows={(bookingsQuery.data?.bookings || []).filter((row) => row.source === "walk_in")} columns={bookingColumns} empty={<EmptyState variant="section" alignment="left" icon={UserPlus} title="No active walk-ins" description="Walk-ins started at the front desk appear here until their service is complete." primaryAction={can("appointments.manage") ? <Button onClick={() => navigate("/app/calendar?new=1&source=walk_in")}>Start walk-in</Button> : null} />} />}</TabsContent>
      <TabsContent value="clients" className="mt-6"><DestinationPanel icon={UsersThree} title="Salon clients" description="Open the client directory with Salon terminology, preferences, visit history, formulas, and follow-ups." action="Open clients" onClick={() => navigate("/app/clients")} /></TabsContent>
      <TabsContent value="services" className="mt-6"><DestinationPanel icon={Scissors} title="Service menu" description="Prices, duration, tax, and location availability are managed in the shared catalog." action="Open services" onClick={() => navigate("/app/catalog?type=service")} /></TabsContent>
      <TabsContent value="staff" className="mt-6"><DestinationPanel icon={UsersThree} title="Stylists and schedules" description="Manage skills, locations, schedules, and access from the Team workspace." action="Open team" onClick={() => navigate("/app/team")} /></TabsContent>
      <TabsContent value="preferences" className="mt-6">{rebookingQuery.isError && !rebookingQuery.data ? <ErrorState title="Rebooking opportunities could not be loaded" description={rebookingQuery.error?.data?.detail} retry={rebookingQuery.refetch} /> : <RebookingPanel rows={rebookingQuery.data?.rebooking || []} loading={rebookingQuery.isLoading} detailed />}</TabsContent>
      <TabsContent value="follow-ups" className="mt-6">{followUpsQuery.isError && !followUpsQuery.data ? <ErrorState title="Follow-ups could not be loaded" description={followUpsQuery.error?.data?.detail} retry={followUpsQuery.refetch} /> : <FollowupPanel rows={followUpsQuery.data?.follow_ups || []} loading={followUpsQuery.isLoading} />}</TabsContent>
      <TabsContent value="performance" className="mt-6">{performanceQuery.isError && !performanceQuery.data ? <ErrorState title="Salon performance could not be loaded" description={performanceQuery.error?.data?.detail} retry={performanceQuery.refetch} /> : <MetricStrip loading={performanceQuery.isLoading && !summary} metrics={summary ? [{ id: "completed", label: "Completed today", value: summary.completed_today }, { id: "roster", label: "Team on roster", value: summary.staff_on_roster }, ...(summary.revenue_paise != null ? [{ id: "revenue", label: `${range}-day revenue`, value: summary.revenue_paise, format: "money" }] : [])] : []} />}</TabsContent>
    </Tabs>
  </PageShell>;
}

const bookingColumns = [
  { key: "client", label: "Client", render: (row) => row.client ? <EntityProfileLink profileRef={profileRef("client", row.client.id)} className="flex items-center gap-3"><EntityAvatar name={row.client.name} avatarUrl={row.client.avatar_url} className="h-9 w-9 rounded-xl text-sm" /><span><span className="block font-semibold">{row.client.name}</span><span className="text-xs text-muted-foreground">{row.client.phone}</span></span></EntityProfileLink> : "Unavailable client" },
  { key: "starts_at", label: "Time", render: (row) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(row.starts_at)) },
  { key: "service_name", label: "Service", render: (row) => row.service_name || "General service" },
  { key: "employee_name", label: "Stylist", render: (row) => row.employee_name || "Unassigned" },
  { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
];

function BookingPanel({ bookings = [], navigate, loading = false }) {
  return <Surface className="overflow-hidden"><PanelHeader title="What is next" subtitle="Upcoming confirmed and scheduled bookings" action={<Button variant="ghost" size="sm" onClick={() => navigate("/app/salon/bookings")}>View all</Button>} />{loading ? <PanelSkeleton /> : bookings.length ? <div className="divide-y">{bookings.map((row) => <div key={row.id} className="flex items-center gap-4 p-4 sm:px-5"><div className="grid h-11 w-11 place-items-center rounded-xl bg-secondary"><Clock /></div><div className="min-w-0 flex-1"><div className="truncate font-semibold">{row.client?.name || "Client"}</div><div className="mt-1 truncate text-xs text-muted-foreground">{row.service_name || "General service"} · {row.employee_name || "Unassigned"}</div></div><div className="text-right"><div className="text-sm font-medium">{new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit" }).format(new Date(row.starts_at))}</div><StatusBadge className="mt-1" status={row.status} /></div></div>)}</div> : <EmptyState variant="inline" icon={CalendarBlank} title="No upcoming bookings" description="The current scoped calendar has no scheduled work." className="m-5" />}</Surface>;
}
function RebookingPanel({ rows = [], detailed = false, loading = false }) {
  return <Surface className="overflow-hidden"><PanelHeader title="Rebooking opportunities" subtitle="Clients beyond their normal visit interval" />{loading ? <PanelSkeleton /> : rows.length ? <div className="divide-y">{rows.map((row) => <EntityProfileLink key={row.id} profileRef={profileRef("client", row.client.id)} className="flex items-center gap-4 p-4 hover:bg-surface-hover sm:px-5"><EntityAvatar name={row.client.name} avatarUrl={row.client.avatar_url} className="h-10 w-10 rounded-xl text-sm" /><span className="min-w-0 flex-1"><span className="block truncate font-semibold">{row.client.name}</span><span className="mt-1 block text-xs text-muted-foreground">Expected {dateLabel(row.expected_on)}{detailed ? ` · Last visit ${dateLabel(row.last_visit)}` : ""}</span></span><StatusBadge status={row.delay_days > 14 ? "action_needed" : "watch"} label={`${row.delay_days}d late`} /></EntityProfileLink>)}</div> : <EmptyState variant="inline" icon={CheckIcon} title="No rebooking gaps" description="No client is currently beyond a configured visit interval." className="m-5" />}</Surface>;
}
function FollowupPanel({ rows = [], loading = false }) {
  return <Surface className="overflow-hidden"><PanelHeader title="Open follow-ups" subtitle="Promises and commitments that still need an owner" />{loading ? <PanelSkeleton /> : rows.length ? <div className="grid gap-px bg-border sm:grid-cols-2 xl:grid-cols-3">{rows.map((row) => <EntityProfileLink key={row.id} profileRef={profileRef("client", row.client.id)} className="bg-card p-5 hover:bg-surface-hover"><div className="flex items-center gap-3"><EntityAvatar name={row.client.name} avatarUrl={row.client.avatar_url} className="h-9 w-9 rounded-xl text-sm" /><div className="truncate font-semibold">{row.client.name}</div></div><div className="mt-4 font-medium">{row.title}</div><div className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{row.description || "No additional note"}</div>{row.due_at && <div className="mt-3 text-xs text-muted-foreground">Due {new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(row.due_at))}</div>}</EntityProfileLink>)}</div> : <EmptyState variant="inline" icon={UsersThree} title="No open follow-ups" description="Current client commitments are complete." className="m-5" />}</Surface>;
}
function PanelSkeleton() { return <div className="space-y-3 p-5" aria-label="Loading"><div className="h-12 animate-pulse rounded-xl bg-secondary" /><div className="h-12 animate-pulse rounded-xl bg-secondary" /><div className="h-12 animate-pulse rounded-xl bg-secondary" /></div>; }
function DestinationPanel({ icon: Icon, title, description, action, onClick }) { return <EmptyState variant="section" alignment="left" icon={Icon} title={title} description={description} action={<Button onClick={onClick}>{action}</Button>} />; }
function PanelHeader({ title, subtitle, action }) { return <div className="flex items-start justify-between gap-4 border-b px-5 py-4"><div><h2 className="font-display text-2xl font-semibold">{title}</h2><p className="mt-1 text-xs text-muted-foreground">{subtitle}</p></div>{action}</div>; }
function dateLabel(value) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(`${value}T00:00:00`)); }
function CheckIcon(props) { return <Scissors {...props} />; }
