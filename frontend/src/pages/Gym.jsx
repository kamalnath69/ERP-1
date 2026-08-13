import React, { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight, Barbell, CalendarBlank, CheckCircle, ForkKnife, Gauge, Plus, Pulse,
  Snowflake, UserFocus, UsersThree, Wrench,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import {
  DataTable, DrawerForm, EmptyState, ErrorState, MetricStrip, PageHeader, PageShell,
  ResponsiveCardGrid, StatusBadge, Surface, formatMetric,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { FieldError, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  useAddDietPlanMutation, useAddMeasurementMutation, useAddWorkoutPlanMutation,
  useAssignTrainerMutation, useBookGymClassMutation, useCancelMembershipMutation,
  useCheckInMemberMutation, useCheckOutMemberMutation, useCreateGymClassMutation,
  useCreateGymEquipmentMutation, useCreateMembershipMutation, useCreateMembershipPlanMutation,
  useFreezeMembershipMutation, useGetGymAttendanceQuery, useGetGymClassesQuery,
  useGetGymCoachingQuery, useGetGymEquipmentQuery, useGetGymSummaryQuery,
  useGetMembershipPlansQuery, useGetMembershipQuoteQuery, useGetMembershipsQuery, useRenewMembershipMutation,
  useResumeMembershipMutation, useRevokeMembershipCancellationMutation,
} from "@/features/gym/gymApi";
import { useGetClientsQuery, useGetEmployeesQuery } from "@/store/api/workspaceApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { useStableIdempotencyKey } from "@/hooks/usePendingAction";
import {
  applyApiErrors, cancellationSchema, equipmentSchema, FORM_OPTIONS, freezeMembershipSchema,
  gymCheckinSchema, gymClassBookingSchema, gymClassSchema, gymCoachingSchema,
  membershipPlanSchema, membershipRenewalSchema, membershipSchema,
} from "@/lib/validation";


const sectionDefinitions = [
  { id: "overview", label: "Overview" },
  { id: "memberships", label: "Memberships", permission: "gym.memberships.view" },
  { id: "attendance", label: "Attendance", permission: "gym.attendance.view" },
  { id: "classes", label: "Classes", permission: "gym.classes.view" },
  { id: "coaching", label: "Coaching", permission: "gym.coaching.view" },
  { id: "measurements", label: "Measurements", permission: "gym.measurements.view" },
  { id: "workouts", label: "Workouts", permission: "gym.workouts.view" },
  { id: "diets", label: "Diets", permission: "gym.diets.view" },
  { id: "equipment", label: "Equipment", permission: "gym.equipment.view" },
];


export default function Gym() {
  const { can } = useAuth();
  const { locationId } = useBusiness();
  const route = useLocation();
  const navigate = useNavigate();
  const sections = sectionDefinitions.filter((section) => !section.permission || can(section.permission));
  const candidate = route.pathname.split("/").filter(Boolean).pop();
  const active = sections.some((section) => section.id === candidate) ? candidate : "overview";
  const [membershipOpen, setMembershipOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [membershipAction, setMembershipAction] = useState(null);
  const [checkinOpen, setCheckinOpen] = useState(false);
  const [coachingOpen, setCoachingOpen] = useState(null);
  const [classOpen, setClassOpen] = useState(false);
  const [bookClass, setBookClass] = useState(null);
  const [equipmentOpen, setEquipmentOpen] = useState(false);

  const summaryQuery = useGetGymSummaryQuery({ locationId }, withSkip(QUERY_POLICIES.live, !locationId));
  const membershipsNeeded = ["overview", "memberships", "attendance"].includes(active) || membershipAction || checkinOpen;
  const membershipsQuery = useGetMembershipsQuery({ locationId }, withSkip(QUERY_POLICIES.operational, !locationId || !can("gym.memberships.view") || !membershipsNeeded));
  const attendanceNeeded = ["overview", "attendance"].includes(active);
  const attendanceQuery = useGetGymAttendanceQuery({ locationId }, withSkip(QUERY_POLICIES.live, !locationId || !can("gym.attendance.view") || !attendanceNeeded));
  const classesNeeded = ["overview", "classes"].includes(active) || Boolean(bookClass);
  const classesQuery = useGetGymClassesQuery({ locationId }, withSkip(QUERY_POLICIES.operational, !locationId || !can("gym.classes.view") || !classesNeeded));
  const coachingSection = ["coaching", "measurements", "workouts", "diets"].includes(active) ? ({ coaching: "trainers", measurements: "measurements", workouts: "workouts", diets: "diets" }[active]) : null;
  const coachingQuery = useGetGymCoachingQuery({ section: coachingSection || "trainers" }, withSkip(QUERY_POLICIES.collaborative, !coachingSection));
  const equipmentQuery = useGetGymEquipmentQuery({ locationId }, withSkip(QUERY_POLICIES.collaborative, !locationId || active !== "equipment"));

  const changeSection = (section) => navigate(section === "overview" ? "/app/gym" : `/app/gym/${section}`);
  const summary = summaryQuery.data;
  const metrics = summary ? [
    { id: "members", label: "Active memberships", value: summary.active_memberships },
    { id: "inside", label: "Inside now", value: summary.inside_now },
    { id: "checkins", label: "Check-ins today", value: summary.check_ins_today },
    { id: "renewals", label: "Expiring in 7 days", value: summary.expiring_7_days, tone: summary.expiring_7_days ? "warning" : "neutral" },
  ] : [];
  const renewalRows = (membershipsQuery.data || []).filter((row) => row.status === "active").slice(0, 6);
  const todayClasses = (classesQuery.data || []).filter((row) => isToday(row.starts_at)).slice(0, 6);
  const insideRows = (attendanceQuery.data || []).filter((row) => !row.checked_out_at).slice(0, 8);
  const overviewLoading = membershipsQuery.isLoading || classesQuery.isLoading || attendanceQuery.isLoading;
  const hasOverviewWork = Boolean(renewalRows.length || todayClasses.length || insideRows.length);

  return <PageShell className="reveal">
    <PageHeader
      eyebrow="Gym operations"
      title="Move every Client forward"
      description="Memberships, timestamped attendance, classes, coaching, progress, nutrition, and equipment in one role-aware workspace."
      actions={<>{can("gym.attendance.mark") && <Button variant="outline" onClick={() => setCheckinOpen(true)}><CheckCircle className="mr-2" />Check in</Button>}{can("gym.memberships.manage") && <Button onClick={() => setMembershipOpen(true)}><Plus className="mr-2" />New membership</Button>}</>}
    />
    <Tabs value={active} onValueChange={changeSection}>
      <TabsList className="premium-scrollbar h-auto w-full justify-start overflow-x-auto rounded-xl bg-secondary/60 p-1">{sections.map((section) => <TabsTrigger key={section.id} value={section.id} className="whitespace-nowrap">{section.label}</TabsTrigger>)}</TabsList>
      <TabsContent value="overview" className="mt-6 space-y-6">
        {summaryQuery.isError && !summary ? <ErrorState title="Gym overview could not be loaded" description={summaryQuery.error?.data?.detail} retry={summaryQuery.refetch} /> : <MetricStrip metrics={metrics} loading={summaryQuery.isLoading && !summary} />}
        {overviewLoading || hasOverviewWork ? <>
          <ResponsiveCardGrid minWidth="28rem" className="gap-5">
            {(membershipsQuery.isLoading || renewalRows.length > 0) && <Surface className="overflow-hidden"><PanelHeader title="Renewals to protect" copy="Active memberships closest to expiry." action={can("gym.memberships.view") && <Button variant="ghost" onClick={() => changeSection("memberships")}>View memberships<ArrowRight className="ml-2" /></Button>} /><DataTable className="rounded-none border-0 shadow-none" loading={membershipsQuery.isLoading} rows={renewalRows} columns={membershipColumns({ compact: true })} /></Surface>}
            {(classesQuery.isLoading || todayClasses.length > 0) && <Surface className="overflow-hidden"><PanelHeader title="Today&apos;s classes" copy="Capacity and trainer coverage for this location." action={can("gym.classes.view") && <Button variant="ghost" onClick={() => changeSection("classes")}>View classes<ArrowRight className="ml-2" /></Button>} /><DataTable className="rounded-none border-0 shadow-none" loading={classesQuery.isLoading} rows={todayClasses} columns={classColumns()} /></Surface>}
          </ResponsiveCardGrid>
          {(attendanceQuery.isLoading || insideRows.length > 0) && <Surface className="overflow-hidden"><PanelHeader title="Live attendance" copy="Timestamped visits currently inside the gym." action={can("gym.attendance.view") && <Button variant="ghost" onClick={() => changeSection("attendance")}>View attendance<ArrowRight className="ml-2" /></Button>} /><DataTable className="rounded-none border-0 shadow-none" loading={attendanceQuery.isLoading} rows={insideRows} columns={attendanceColumns()} /></Surface>}
        </> : <EmptyState variant="section" alignment="left" icon={Gauge} title="Gym operations are ready" description="No renewal, class, or live-attendance work needs attention at this location." primaryAction={can("gym.memberships.manage") ? <Button onClick={() => setMembershipOpen(true)}><Plus className="mr-2" />New membership</Button> : can("gym.attendance.mark") ? <Button onClick={() => setCheckinOpen(true)}><CheckCircle className="mr-2" />Check in</Button> : null} steps={[{ title: "Activate members" }, { title: "Schedule classes" }, { title: "Track attendance" }]} />}
      </TabsContent>
      <TabsContent value="memberships" className="mt-6"><MembershipPanel query={membershipsQuery} canManage={can("gym.memberships.manage")} onCreate={() => setMembershipOpen(true)} onPlan={() => setPlanOpen(true)} onOpen={setMembershipAction} onClient={(id) => navigate(`/app/clients/${id}`)} /></TabsContent>
      <TabsContent value="attendance" className="mt-6"><AttendancePanel query={attendanceQuery} canMark={can("gym.attendance.mark")} onCheckin={() => setCheckinOpen(true)} onClient={(id) => navigate(`/app/clients/${id}`)} /></TabsContent>
      <TabsContent value="classes" className="mt-6"><ClassesPanel query={classesQuery} canManage={can("gym.classes.manage")} onCreate={() => setClassOpen(true)} onBook={setBookClass} /></TabsContent>
      {[["coaching", "trainers"], ["measurements", "measurements"], ["workouts", "workouts"], ["diets", "diets"]].map(([section, kind]) => <TabsContent key={section} value={section} className="mt-6"><CoachingPanel section={section} kind={kind} query={coachingQuery} canManage={can(managePermission(kind))} onCreate={() => setCoachingOpen(kind)} onClient={(id) => navigate(`/app/clients/${id}`)} /></TabsContent>)}
      <TabsContent value="equipment" className="mt-6"><EquipmentPanel query={equipmentQuery} canManage={can("gym.equipment.manage")} onCreate={() => setEquipmentOpen(true)} /></TabsContent>
    </Tabs>
    <MembershipDrawer open={membershipOpen} onOpenChange={setMembershipOpen} locationId={locationId} />
    <PlanDrawer open={planOpen} onOpenChange={setPlanOpen} />
    <MembershipActionDrawer membership={membershipAction} onOpenChange={(open) => !open && setMembershipAction(null)} />
    <CheckinDrawer open={checkinOpen} onOpenChange={setCheckinOpen} locationId={locationId} memberships={membershipsQuery.data || []} />
    <CoachingDrawer kind={coachingOpen} onOpenChange={(open) => !open && setCoachingOpen(null)} locationId={locationId} />
    <ClassDrawer open={classOpen} onOpenChange={setClassOpen} locationId={locationId} />
    <ClassBookingDrawer gymClass={bookClass} onOpenChange={(open) => !open && setBookClass(null)} locationId={locationId} />
    <EquipmentDrawer open={equipmentOpen} onOpenChange={setEquipmentOpen} locationId={locationId} />
  </PageShell>;
}


function MembershipPanel({ query, canManage, onCreate, onPlan, onOpen, onClient }) {
  const [status, setStatus] = useState("current");
  if (query.isError && !query.data) return <ErrorState title="Memberships could not be loaded" description={query.error?.data?.detail} retry={query.refetch} />;
  const rows = (query.data || []).filter((row) => status === "all" || (status === "current" ? ["active", "frozen"].includes(row.status) : row.status === status));
  return <div className="space-y-4"><div className="flex flex-col gap-3 sm:flex-row sm:justify-between"><Select value={status} onValueChange={setStatus}><SelectTrigger className="w-full sm:w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="current">Current memberships</SelectItem><SelectItem value="active">Active</SelectItem><SelectItem value="frozen">Frozen</SelectItem><SelectItem value="scheduled">Scheduled renewals</SelectItem><SelectItem value="cancelled">Cancelled</SelectItem><SelectItem value="renewed">Renewed</SelectItem><SelectItem value="expired">Expired</SelectItem><SelectItem value="all">All history</SelectItem></SelectContent></Select>{canManage && <div className="flex gap-2"><Button variant="outline" onClick={onPlan}>Manage plans</Button><Button onClick={onCreate}><Plus className="mr-2" />New membership</Button></div>}</div><DataTable loading={query.isLoading} rows={rows} columns={membershipColumns({ onClient, includeActions: canManage, onOpen })} onRowClick={onOpen} empty={<EmptyState variant={status !== "current" ? "filtered" : "page"} alignment="left" icon={UserFocus} title={status !== "current" ? "No memberships match this status" : "Create your first membership"} description={status !== "current" ? "Return to current memberships or choose another lifecycle state." : "Activate a membership for a Client who needs Gym access. Product-only Clients remain in the main directory."} primaryAction={status !== "current" ? <Button variant="outline" onClick={() => setStatus("current")}>Show current memberships</Button> : canManage ? <Button onClick={onCreate}>Create membership</Button> : null} steps={status !== "current" ? [] : [{ title: "Choose client" }, { title: "Select plan" }, { title: "Record payment" }]} />} /></div>;
}


function membershipColumns({ compact, onClient, includeActions, onOpen } = {}) { return [
  { key: "client", label: "Client", render: (row) => <button className="text-left" onClick={(event) => { if (!onClient) return; event.stopPropagation(); onClient(row.client?.id); }}><span className="font-semibold">{row.client?.display_name || "Client"}</span><span className="mt-1 block text-xs text-muted-foreground">{row.client?.client_number}{row.inside_now ? " · Inside now" : ""}</span></button> },
  { key: "plan", label: "Plan", render: (row) => row.plan?.name || "Unavailable plan" },
  { key: "ends_on", label: "Expires", render: (row) => <div>{dateOnly(row.ends_on)}{row.status === "active" && <div className="mt-1 text-xs text-muted-foreground">{daysRemaining(row.ends_on)} days remaining</div>}</div> },
  { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
  ...(!compact ? [{ key: "trainer", label: "Trainer", render: (row) => row.trainer?.display_name || "Not assigned" }] : []),
  ...(includeActions ? [{ key: "action", label: "", render: (row) => <Button size="sm" variant="outline" onClick={(event) => { event.stopPropagation(); onOpen(row); }}>Manage</Button> }] : []),
]; }


function AttendancePanel({ query, canMark, onCheckin, onClient }) {
  const [checkout, state] = useCheckOutMemberMutation();
  const doCheckout = async (row) => { try { await checkout(row.id).unwrap(); toast.success(`${row.client?.display_name || "Client"} checked out`); } catch (error) { toast.error(error?.data?.detail || "Check-out could not be recorded"); } };
  if (query.isError && !query.data) return <ErrorState title="Attendance could not be loaded" retry={query.refetch} />;
  const columns = attendanceColumns(onClient, canMark ? (row) => doCheckout(row) : null, state.isLoading);
  return <div className="space-y-4"><div className="flex justify-end">{canMark && <Button onClick={onCheckin}><CheckCircle className="mr-2" />Check in Client</Button>}</div><DataTable loading={query.isLoading} rows={query.data || []} columns={columns} empty={<EmptyState variant="page" alignment="left" icon={CheckCircle} title="Record the first check-in" description="Attendance uses explicit check-in and check-out timestamps, never a guessed present status." primaryAction={canMark ? <Button onClick={onCheckin}>Record first check-in</Button> : null} steps={[{ title: "Choose member" }, { title: "Check in" }, { title: "Check out" }]} />} /></div>;
}


function attendanceColumns(onClient, onCheckout, saving) { return [
  { key: "client", label: "Client", render: (row) => <button className="text-left font-semibold" onClick={(event) => { if (!onClient) return; event.stopPropagation(); onClient(row.client?.id); }}>{row.client?.display_name || "Client"}<span className="mt-1 block text-xs font-normal text-muted-foreground">{row.location_name}</span></button> },
  { key: "checked_in_at", label: "Checked in", render: (row) => dateTime(row.checked_in_at) },
  { key: "checked_out_at", label: "Checked out", render: (row) => row.checked_out_at ? dateTime(row.checked_out_at) : <StatusBadge status="active" label="Inside now" /> },
  { key: "duration", label: "Duration", render: (row) => `${row.duration_minutes} min` },
  { key: "source", label: "Source", render: (row) => sentence(row.method) },
  ...(onCheckout ? [{ key: "action", label: "", render: (row) => !row.checked_out_at ? <Button disabled={saving} size="sm" onClick={(event) => { event.stopPropagation(); onCheckout(row); }}>Check out</Button> : null }] : []),
]; }


function ClassesPanel({ query, canManage, onCreate, onBook }) {
  if (query.isError && !query.data) return <ErrorState title="Classes could not be loaded" retry={query.refetch} />;
  return <div className="space-y-4"><div className="flex justify-end">{canManage && <Button onClick={onCreate}><Plus className="mr-2" />Schedule class</Button>}</div><DataTable loading={query.isLoading} rows={query.data || []} columns={classColumns(canManage ? onBook : null)} empty={<EmptyState variant="page" alignment="left" icon={CalendarBlank} title="Schedule your first class" description="Create a class with a trainer, time, and clear capacity." primaryAction={canManage ? <Button onClick={onCreate}>Schedule first class</Button> : null} steps={[{ title: "Set class" }, { title: "Assign trainer" }, { title: "Accept bookings" }]} />} /></div>;
}


function classColumns(onBook) { return [
  { key: "name", label: "Class", render: (row) => <div className="font-semibold">{row.name}<div className="mt-1 text-xs font-normal text-muted-foreground">{row.location_name}</div></div> },
  { key: "starts_at", label: "Schedule", render: (row) => <div>{dateTime(row.starts_at)}<div className="mt-1 text-xs text-muted-foreground">{duration(row.starts_at, row.ends_at)} min</div></div> },
  { key: "trainer", label: "Trainer", render: (row) => row.trainer_name || "Unassigned" },
  { key: "capacity", label: "Capacity", render: (row) => `${row.booked} / ${row.capacity} booked` },
  { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
  ...(onBook ? [{ key: "action", label: "", render: (row) => row.available > 0 && row.status === "scheduled" ? <Button size="sm" variant="outline" onClick={(event) => { event.stopPropagation(); onBook(row); }}>Book Client</Button> : null }] : []),
]; }


function CoachingPanel({ section, kind, query, canManage, onCreate, onClient }) {
  if (query.isError && !query.data) return <ErrorState title={`${sentence(section)} could not be loaded`} description={query.error?.data?.detail} retry={query.refetch} />;
  const columns = coachingColumns(kind, onClient);
  return <div className="space-y-4"><div className="flex justify-end">{canManage && <Button onClick={onCreate}><Plus className="mr-2" />Add {singular(kind)}</Button>}</div><DataTable loading={query.isLoading} rows={query.data || []} columns={columns} empty={<EmptyState variant="page" alignment="left" icon={kind === "diets" ? ForkKnife : Barbell} title={`No ${section} records yet`} description="Authorized coaching work for assigned Clients appears here." primaryAction={canManage ? <Button onClick={onCreate}>Add {singular(kind)}</Button> : null} />} /></div>;
}


function coachingColumns(kind, onClient) {
  const base = [{ key: "client", label: "Client", render: (row) => <button className="font-semibold" onClick={(event) => { event.stopPropagation(); onClient(row.client?.id); }}>{row.client?.display_name || "Client"}</button> }];
  if (kind === "trainers") return [...base, { key: "trainer", label: "Trainer", render: (row) => row.trainer_name || "Unavailable" }, { key: "starts_on", label: "Assigned", render: (row) => dateOnly(row.starts_on) }, { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> }];
  if (kind === "measurements") return [...base, { key: "measured_on", label: "Measured", render: (row) => dateOnly(row.measured_on) }, { key: "metrics", label: "Measurements", render: (row) => Object.entries(row.metrics || {}).map(([key, value]) => `${sentence(key)}: ${value}`).join(" · ") || "No metrics" }, { key: "notes", label: "Notes", render: (row) => row.notes || "—" }];
  if (kind === "workouts") return [...base, { key: "name", label: "Plan" }, { key: "trainer", label: "Trainer", render: (row) => row.trainer_name || "Unassigned" }, { key: "starts_on", label: "Starts", render: (row) => dateOnly(row.starts_on) }, { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> }];
  return [...base, { key: "name", label: "Plan" }, { key: "starts_on", label: "Starts", render: (row) => dateOnly(row.starts_on) }, { key: "ends_on", label: "Ends", render: (row) => row.ends_on ? dateOnly(row.ends_on) : "Ongoing" }, { key: "notes", label: "Notes", render: (row) => row.notes || "—" }];
}


function EquipmentPanel({ query, canManage, onCreate }) {
  if (query.isError && !query.data) return <ErrorState title="Equipment could not be loaded" retry={query.refetch} />;
  return <div className="space-y-4"><div className="flex justify-end">{canManage && <Button onClick={onCreate}><Plus className="mr-2" />Add equipment</Button>}</div><DataTable loading={query.isLoading} rows={query.data || []} columns={[
    { key: "name", label: "Equipment", render: (row) => <div className="font-semibold">{row.name}<div className="mt-1 font-mono text-xs font-normal text-muted-foreground">{row.asset_code}</div></div> },
    { key: "location", label: "Location", render: (row) => row.location_name },
    { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
    { key: "next_service_on", label: "Next service", render: (row) => row.next_service_on ? dateOnly(row.next_service_on) : "Not scheduled" },
    { key: "notes", label: "Notes", render: (row) => row.notes || "—" },
  ]} empty={<EmptyState variant="page" alignment="left" icon={Wrench} title="Create the equipment register" description="Track assets and service dates before maintenance becomes urgent." primaryAction={canManage ? <Button onClick={onCreate}>Add equipment</Button> : null} steps={[{ title: "Add asset" }, { title: "Set service date" }, { title: "Track condition" }]} />} /></div>;
}


function LegacyMembershipDrawer({ open, onOpenChange, locationId }) {
  const clientsQuery = useGetClientsQuery({ locationId, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const plansQuery = useGetMembershipPlansQuery(undefined, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateMembershipMutation();
  const [form, setForm] = useState({ client_id: "", plan_id: "", starts_on: today(), payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false });
  const quoteQuery = useGetMembershipQuoteQuery({ planId: form.plan_id, clientId: form.client_id, kind: "activation", interstate: form.interstate }, { skip: !open || !form.client_id || !form.plan_id });
  const quote = quoteQuery.data;
  const paymentNeeded = ["full", "partial"].includes(form.payment_option);
  const validPartial = form.payment_option !== "partial" || (Number(form.partial_amount) > 0 && Math.round(Number(form.partial_amount) * 100) < (quote?.total_paise || 0));
  const submit = async (event) => {
    event.preventDefault();
    if (!form.payment_option || !validPartial) return;
    try {
      await create({
        client_id: form.client_id,
        plan_id: form.plan_id,
        starts_on: form.starts_on,
        location_id: locationId,
        payment_option: form.payment_option,
        partial_payment_paise: form.payment_option === "partial" ? Math.round(Number(form.partial_amount) * 100) : null,
        payment_method: paymentNeeded ? form.payment_method : null,
        payment_reference: form.payment_reference || null,
        interstate: form.interstate,
        idempotency_key: crypto.randomUUID(),
      }).unwrap();
      toast.success("Membership activated with linked invoice");
      setForm({ client_id: "", plan_id: "", starts_on: today(), payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false });
      onOpenChange(false);
    } catch (error) {
      toast.error(error?.data?.detail || "Membership could not be activated");
    }
  };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Activate membership" description="Confirm the authoritative charge and explicitly choose how its linked invoice will be paid."><form onSubmit={submit} className="space-y-5"><Field label="Client"><Select required value={form.client_id} onValueChange={(client_id) => setForm({ ...form, client_id })} disabled={clientsQuery.isLoading}><SelectTrigger><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name} / {client.client_number}</SelectItem>)}</SelectContent></Select></Field><Field label="Membership plan"><Select required value={form.plan_id} onValueChange={(plan_id) => setForm({ ...form, plan_id })} disabled={plansQuery.isLoading}><SelectTrigger><SelectValue placeholder="Choose plan" /></SelectTrigger><SelectContent>{(plansQuery.data || []).map((plan) => <SelectItem key={plan.id} value={plan.id}>{plan.name} / {money(plan.price_paise)}</SelectItem>)}</SelectContent></Select></Field><Field label="Starts on"><Input required min={today()} type="date" value={form.starts_on} onChange={(event) => setForm({ ...form, starts_on: event.target.value })} /></Field><MembershipCheckoutFields form={form} setForm={setForm} quote={quote} quoteLoading={quoteQuery.isFetching} validPartial={validPartial} /><Button disabled={state.isLoading || !quote || !form.payment_option || !validPartial} className="w-full">{state.isLoading ? "Activating..." : "Activate and issue invoice"}</Button></form></DrawerForm>;
}

function MembershipDrawer({ open, onOpenChange, locationId }) {
  const clientsQuery = useGetClientsQuery({ locationId, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const plansQuery = useGetMembershipPlansQuery(undefined, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateMembershipMutation();
  const idempotency = useStableIdempotencyKey();
  const formApi = useForm({
    resolver: zodResolver(membershipSchema),
    defaultValues: {
      client_id: "", plan_id: "", starts_on: today(), payment_option: "",
      partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false,
    },
    ...FORM_OPTIONS,
  });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  const form = watch();
  const quoteQuery = useGetMembershipQuoteQuery(
    { planId: form.plan_id, clientId: form.client_id, kind: "activation", interstate: form.interstate },
    { skip: !open || !form.client_id || !form.plan_id },
  );
  const quote = quoteQuery.data;
  const close = (next) => {
    if (!next && (formState.isSubmitting || state.isLoading)) return;
    if (!next) { reset(); clearErrors(); idempotency.reset(); }
    onOpenChange(next);
  };
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    if (!quote) {
      setError("root.server", { type: "quote", message: "Wait for the final membership charge to load" });
      return;
    }
    if (values.payment_option === "partial" && Math.round(values.partial_amount * 100) >= Number(quote.total_paise || 0)) {
      setError("partial_amount", { type: "maximum", message: "Partial payment must be below the invoice total" }, { shouldFocus: true });
      return;
    }
    try {
      await create({
        client_id: values.client_id,
        plan_id: values.plan_id,
        starts_on: values.starts_on,
        location_id: locationId,
        payment_option: values.payment_option,
        partial_payment_paise: values.payment_option === "partial" ? Math.round(values.partial_amount * 100) : null,
        payment_method: values.payment_option === "later" ? null : values.payment_method,
        payment_reference: values.payment_option === "later" ? null : values.payment_reference,
        interstate: values.interstate,
        idempotency_key: idempotency.current(),
      }).unwrap();
      toast.success("Membership activated with linked invoice");
      reset();
      idempotency.reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Membership could not be activated" });
      toast.error(normalized.message);
    }
  });
  const busy = formState.isSubmitting || state.isLoading;
  return <DrawerForm open={open} onOpenChange={close} title="Activate membership" description="Confirm the authoritative charge and explicitly choose how its linked invoice will be paid."><form noValidate onSubmit={submit} className="space-y-5"><Field label="Client" error={formState.errors.client_id}><Select value={form.client_id} onValueChange={(client_id) => setValue("client_id", client_id, { shouldDirty: true, shouldValidate: true })} disabled={clientsQuery.isLoading || busy}><SelectTrigger aria-invalid={Boolean(formState.errors.client_id)}><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name} / {client.client_number}</SelectItem>)}</SelectContent></Select></Field><Field label="Membership plan" error={formState.errors.plan_id}><Select value={form.plan_id} onValueChange={(plan_id) => setValue("plan_id", plan_id, { shouldDirty: true, shouldValidate: true })} disabled={plansQuery.isLoading || busy}><SelectTrigger aria-invalid={Boolean(formState.errors.plan_id)}><SelectValue placeholder="Choose plan" /></SelectTrigger><SelectContent>{(plansQuery.data || []).map((plan) => <SelectItem key={plan.id} value={plan.id}>{plan.name} / {money(plan.price_paise)}</SelectItem>)}</SelectContent></Select></Field><Field label="Starts on" error={formState.errors.starts_on}><Input min={today()} type="date" {...register("starts_on")} aria-invalid={Boolean(formState.errors.starts_on)} /></Field><ValidatedMembershipCheckoutFields form={form} register={register} setValue={setValue} errors={formState.errors} quote={quote} quoteLoading={quoteQuery.isFetching} disabled={busy} /><FormRootError error={formState.errors.root?.server} /><Button type="submit" loading={busy} loadingText="Activating membership..." disabled={!formState.isValid || !quote} className="w-full">Activate and issue invoice</Button></form></DrawerForm>;
}

function ValidatedMembershipCheckoutFields({ form, register, setValue, errors, quote, quoteLoading, disabled }) {
  const paymentNeeded = ["full", "partial"].includes(form.payment_option);
  return <>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form.interstate)} disabled={disabled} onChange={(event) => setValue("interstate", event.target.checked, { shouldDirty: true, shouldValidate: true })} />Use IGST for this invoice</label>
    <Surface className="overflow-hidden"><div className="border-b p-4"><div className="font-semibold">Charge summary</div><div className="mt-1 text-xs text-muted-foreground">Organization tax settings are preserved on the invoice.</div></div>{quoteLoading ? <div className="h-32 animate-pulse bg-secondary" /> : quote ? <div className="p-4"><CheckoutMoneyRow label="Membership fee" value={quote.base_fee_paise} /><CheckoutMoneyRow label="Joining fee" value={quote.joining_fee_paise} hidden={!quote.joining_fee_paise} /><CheckoutMoneyRow label={`Tax (${quote.tax_rate_bps / 100}%)`} value={quote.tax_paise} /><CheckoutMoneyRow label="Total" value={quote.total_paise} strong /></div> : <div className="p-4 text-sm text-muted-foreground">Choose a Client and plan to calculate the final charge.</div>}</Surface>
    <section><div className="text-sm font-semibold">Payment treatment</div><div className="mt-3 grid gap-2 sm:grid-cols-3">{[["full", "Full", "Settle now"], ["partial", "Partial", "Record some"], ["later", "Later", "Leave due"]].map(([value, label, copy]) => <label key={value} className={`cursor-pointer rounded-xl border p-3 ${form.payment_option === value ? "border-primary bg-primary/5" : "hover:bg-secondary"}`}><input className="sr-only" type="radio" name="payment-option" disabled={disabled} checked={form.payment_option === value} onChange={() => setValue("payment_option", value, { shouldDirty: true, shouldValidate: true })} /><span className="block text-sm font-semibold">{label}</span><span className="mt-1 block text-xs text-muted-foreground">{copy}</span></label>)}</div><FieldError error={errors.payment_option} className="mt-2" /></section>
    {form.payment_option === "partial" && <Field label="Amount received (INR)" error={errors.partial_amount}><Input inputMode="decimal" {...register("partial_amount")} aria-invalid={Boolean(errors.partial_amount)} /></Field>}
    {paymentNeeded && <><Field label="Payment method" error={errors.payment_method}><Select value={form.payment_method || ""} onValueChange={(payment_method) => setValue("payment_method", payment_method, { shouldDirty: true, shouldValidate: true })} disabled={disabled}><SelectTrigger aria-invalid={Boolean(errors.payment_method)}><SelectValue placeholder="Choose method" /></SelectTrigger><SelectContent>{["cash", "upi", "card", "bank"].map((method) => <SelectItem key={method} value={method}>{sentence(method)}</SelectItem>)}</SelectContent></Select></Field><Field label="Reference" error={errors.payment_reference}><Input {...register("payment_reference")} placeholder="Optional transaction reference" aria-invalid={Boolean(errors.payment_reference)} /></Field></>}
  </>;
}


function MembershipCheckoutFields({ form, setForm, quote, quoteLoading, validPartial }) {
  const paymentNeeded = ["full", "partial"].includes(form.payment_option);
  return <>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.interstate} onChange={(event) => setForm({ ...form, interstate: event.target.checked })} />Use IGST for this invoice</label>
    <Surface className="overflow-hidden"><div className="border-b p-4"><div className="font-semibold">Charge summary</div><div className="mt-1 text-xs text-muted-foreground">Organization tax settings are preserved on the invoice.</div></div>{quoteLoading ? <div className="h-32 animate-pulse bg-secondary" /> : quote ? <div className="p-4"><CheckoutMoneyRow label="Membership fee" value={quote.base_fee_paise} /><CheckoutMoneyRow label="Joining fee" value={quote.joining_fee_paise} hidden={!quote.joining_fee_paise} /><CheckoutMoneyRow label={`Tax (${quote.tax_rate_bps / 100}%)`} value={quote.tax_paise} /><CheckoutMoneyRow label="Total" value={quote.total_paise} strong /></div> : <div className="p-4 text-sm text-muted-foreground">Choose a Client and plan to calculate the final charge.</div>}</Surface>
    <section><div className="text-sm font-semibold">Payment treatment</div><div className="mt-3 grid gap-2 sm:grid-cols-3">{[["full", "Full", "Settle now"], ["partial", "Partial", "Record some"], ["later", "Later", "Leave due"]].map(([value, label, copy]) => <label key={value} className={`cursor-pointer rounded-xl border p-3 ${form.payment_option === value ? "border-primary bg-primary/5" : "hover:bg-secondary"}`}><input className="sr-only" type="radio" name="payment-option" checked={form.payment_option === value} onChange={() => setForm({ ...form, payment_option: value })} /><span className="block text-sm font-semibold">{label}</span><span className="mt-1 block text-xs text-muted-foreground">{copy}</span></label>)}</div></section>
    {form.payment_option === "partial" && <Field label="Amount received (INR)"><Input required type="number" min="0.01" max={(quote?.total_paise || 0) / 100 - 0.01} step="0.01" value={form.partial_amount} onChange={(event) => setForm({ ...form, partial_amount: event.target.value })} />{!validPartial && <p className="text-xs text-danger">Partial payment must be below the invoice total.</p>}</Field>}
    {paymentNeeded && <><Field label="Payment method"><Select value={form.payment_method} onValueChange={(payment_method) => setForm({ ...form, payment_method })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["cash", "upi", "card", "bank"].map((method) => <SelectItem key={method} value={method}>{sentence(method)}</SelectItem>)}</SelectContent></Select></Field><Field label="Reference"><Input maxLength={120} value={form.payment_reference} onChange={(event) => setForm({ ...form, payment_reference: event.target.value })} placeholder="Optional transaction reference" /></Field></>}
  </>;
}


function CheckoutMoneyRow({ label, value, strong, hidden }) {
  if (hidden) return null;
  return <div className={`flex items-center justify-between gap-4 py-1.5 text-sm ${strong ? "mt-2 border-t pt-4 font-display text-xl font-semibold" : ""}`}><span>{label}</span><span>{money(value)}</span></div>;
}


function LegacyPlanDrawer({ open, onOpenChange }) {
  const plansQuery = useGetMembershipPlansQuery(undefined, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateMembershipPlanMutation();
  const [form, setForm] = useState({ name: "", duration_days: "30", price: "", joining_fee: "", benefits: "" });
  const submit = async (event) => { event.preventDefault(); try { await create({ name: form.name.trim(), duration_days: Number(form.duration_days), price_paise: Math.round(Number(form.price) * 100), joining_fee_paise: Math.round(Number(form.joining_fee || 0) * 100), benefits: form.benefits.split(",").map((value) => value.trim()).filter(Boolean) }).unwrap(); toast.success("Membership plan created"); setForm({ name: "", duration_days: "30", price: "", joining_fee: "", benefits: "" }); } catch (error) { toast.error(error?.data?.detail || "Membership plan could not be created"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Membership plans" description="Plans define access duration and price. Client lifecycle actions remain separate."><div className="space-y-6"><div className="space-y-2">{(plansQuery.data || []).map((plan) => <Surface key={plan.id} className="p-4"><div className="flex justify-between gap-4"><div><div className="font-semibold">{plan.name}</div><div className="mt-1 text-xs text-muted-foreground">{plan.duration_days} days · {plan.benefits?.join(", ") || "No benefits listed"}</div></div><div className="font-display text-xl font-semibold">{money(plan.price_paise)}</div></div></Surface>)}</div><form onSubmit={submit} className="space-y-4 border-t pt-5"><h3 className="font-display text-xl font-semibold">Create a plan</h3><Field label="Plan name"><Input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field><div className="grid gap-4 sm:grid-cols-3"><Field label="Duration days"><Input required type="number" min="1" value={form.duration_days} onChange={(event) => setForm({ ...form, duration_days: event.target.value })} /></Field><Field label="Price (INR)"><Input required type="number" min="0" step="0.01" value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} /></Field><Field label="Joining fee"><Input type="number" min="0" step="0.01" value={form.joining_fee} onChange={(event) => setForm({ ...form, joining_fee: event.target.value })} /></Field></div><Field label="Benefits"><Input value={form.benefits} onChange={(event) => setForm({ ...form, benefits: event.target.value })} placeholder="Comma-separated benefits" /></Field><Button disabled={state.isLoading} className="w-full">{state.isLoading ? "Creating..." : "Create plan"}</Button></form></div></DrawerForm>;
}

function PlanDrawer({ open, onOpenChange }) {
  const plansQuery = useGetMembershipPlansQuery(undefined, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateMembershipPlanMutation();
  const formApi = useForm({ resolver: zodResolver(membershipPlanSchema), defaultValues: { name: "", duration_days: "30", price: "", joining_fee: "", benefits: "" }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError } = formApi;
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await create(values).unwrap();
      toast.success("Membership plan created");
      reset();
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Membership plan could not be created" });
      toast.error(normalized.message);
    }
  });
  const close = (next) => {
    if (!next && (formState.isSubmitting || state.isLoading)) return;
    onOpenChange(next);
  };
  return <DrawerForm open={open} onOpenChange={close} title="Membership plans" description="Plans define access duration and price. Client lifecycle actions remain separate."><div className="space-y-6"><div className="space-y-2">{(plansQuery.data || []).map((plan) => <Surface key={plan.id} className="p-4"><div className="flex justify-between gap-4"><div><div className="font-semibold">{plan.name}</div><div className="mt-1 text-xs text-muted-foreground">{plan.duration_days} days / {plan.benefits?.join(", ") || "No benefits listed"}</div></div><div className="font-display text-xl font-semibold">{money(plan.price_paise)}</div></div></Surface>)}</div><form noValidate onSubmit={submit} className="space-y-4 border-t pt-5"><h3 className="font-display text-xl font-semibold">Create a plan</h3><Field label="Plan name" error={formState.errors.name}><Input {...register("name")} aria-invalid={Boolean(formState.errors.name)} /></Field><div className="grid gap-4 sm:grid-cols-3"><Field label="Duration days" error={formState.errors.duration_days}><Input inputMode="numeric" {...register("duration_days")} aria-invalid={Boolean(formState.errors.duration_days)} /></Field><Field label="Price (INR)" error={formState.errors.price}><Input inputMode="decimal" {...register("price")} aria-invalid={Boolean(formState.errors.price)} /></Field><Field label="Joining fee" error={formState.errors.joining_fee}><Input inputMode="decimal" {...register("joining_fee")} aria-invalid={Boolean(formState.errors.joining_fee)} /></Field></div><Field label="Benefits" error={formState.errors.benefits}><Input {...register("benefits")} placeholder="Comma-separated benefits" aria-invalid={Boolean(formState.errors.benefits)} /></Field><FormRootError error={formState.errors.root?.server} /><Button type="submit" disabled={!formState.isValid} loading={formState.isSubmitting || state.isLoading} loadingText="Creating plan..." className="w-full">Create plan</Button></form></div></DrawerForm>;
}


function LegacyMembershipActionDrawer({ membership, onOpenChange }) {
  const [mode, setMode] = useState("overview");
  const [freezeForm, setFreezeForm] = useState({ frozen_from: today(), frozen_until: addDays(today(), 7) });
  const [cancelForm, setCancelForm] = useState({ reason: "", timing: "term_end", cancel_scheduled_renewal: true });
  const [renewForm, setRenewForm] = useState({ payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false });
  const [checkIn, checkState] = useCheckInMemberMutation();
  const [renew, renewState] = useRenewMembershipMutation();
  const [freeze, freezeState] = useFreezeMembershipMutation();
  const [resume, resumeState] = useResumeMembershipMutation();
  const [cancel, cancelState] = useCancelMembershipMutation();
  const [revoke, revokeState] = useRevokeMembershipCancellationMutation();
  const quoteQuery = useGetMembershipQuoteQuery({ planId: membership?.plan_id, clientId: membership?.client_id, kind: "renewal", interstate: renewForm.interstate }, { skip: !membership || mode !== "renew" });
  const validPartial = renewForm.payment_option !== "partial" || (Number(renewForm.partial_amount) > 0 && Math.round(Number(renewForm.partial_amount) * 100) < (quoteQuery.data?.total_paise || 0));
  const run = async (action) => { try { if (action === "checkin") await checkIn({ location_id: membership.location_id, membership_id: membership.id, method: "staff" }).unwrap(); if (action === "resume") await resume(membership.id).unwrap(); if (action === "revoke") await revoke({ membershipId: membership.id, version: membership.version }).unwrap(); toast.success(action === "checkin" ? "Client checked in" : action === "resume" ? "Membership resumed" : "Cancellation reversed"); onOpenChange(false); setMode("overview"); } catch (error) { toast.error(error?.data?.detail || "Membership action could not be completed"); } };
  const submitFreeze = async (event) => { event.preventDefault(); try { await freeze({ membershipId: membership.id, ...freezeForm, version: membership.version }).unwrap(); toast.success("Membership frozen"); onOpenChange(false); setMode("overview"); } catch (error) { toast.error(error?.data?.detail || "Membership could not be frozen"); } };
  const submitCancel = async (event) => { event.preventDefault(); try { await cancel({ membershipId: membership.id, reason: cancelForm.reason.trim(), version: membership.version, timing: membership.status === "scheduled" ? "now" : cancelForm.timing, cancel_scheduled_renewal: cancelForm.cancel_scheduled_renewal }).unwrap(); toast.success(cancelForm.timing === "term_end" && membership.status !== "scheduled" ? "Cancellation scheduled" : "Membership cancelled"); setCancelForm({ reason: "", timing: "term_end", cancel_scheduled_renewal: true }); onOpenChange(false); setMode("overview"); } catch (error) { toast.error(error?.data?.detail || "Membership could not be cancelled"); } };
  const submitRenew = async (event) => { event.preventDefault(); if (!renewForm.payment_option || !validPartial) return; const needsPayment = ["full", "partial"].includes(renewForm.payment_option); try { await renew({ membershipId: membership.id, plan_id: membership.plan_id, payment_option: renewForm.payment_option, partial_payment_paise: renewForm.payment_option === "partial" ? Math.round(Number(renewForm.partial_amount) * 100) : null, payment_method: needsPayment ? renewForm.payment_method : null, payment_reference: renewForm.payment_reference || null, interstate: renewForm.interstate, idempotency_key: crypto.randomUUID() }).unwrap(); toast.success("Renewal created with linked invoice"); setRenewForm({ payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false }); onOpenChange(false); setMode("overview"); } catch (error) { toast.error(error?.data?.detail || "Renewal could not be created"); } };
  const busy = checkState.isLoading || renewState.isLoading || resumeState.isLoading || revokeState.isLoading;
  return <DrawerForm open={Boolean(membership)} onOpenChange={(open) => { if (!open) setMode("overview"); onOpenChange(open); }} title={membership?.client?.display_name || "Membership"} description={membership ? `${membership.plan?.name || "Plan"} / ${membership.location_name}` : ""}>{membership && (mode === "freeze" ? <form onSubmit={submitFreeze} className="space-y-5"><Surface className="p-4"><Snowflake className="text-accent" /><p className="mt-3 text-sm text-muted-foreground">The membership becomes unavailable for check-in until it is resumed. The frozen period extends the expiry date on resume.</p></Surface><Field label="Freeze from"><Input required min={today()} type="date" value={freezeForm.frozen_from} onChange={(event) => setFreezeForm({ ...freezeForm, frozen_from: event.target.value })} /></Field><Field label="Freeze until"><Input required type="date" min={freezeForm.frozen_from} value={freezeForm.frozen_until} onChange={(event) => setFreezeForm({ ...freezeForm, frozen_until: event.target.value })} /></Field><Button disabled={freezeState.isLoading} className="w-full">Confirm freeze</Button></form> : mode === "renew" ? <form onSubmit={submitRenew} className="space-y-5"><Surface className="border-primary/30 bg-primary/5 p-4"><p className="text-sm leading-6">The current term remains active. The next term starts after it ends and receives its own invoice.</p></Surface><MembershipCheckoutFields form={renewForm} setForm={setRenewForm} quote={quoteQuery.data} quoteLoading={quoteQuery.isFetching} validPartial={validPartial} /><Button disabled={renewState.isLoading || !quoteQuery.data || !renewForm.payment_option || !validPartial} className="w-full">{renewState.isLoading ? "Creating renewal..." : "Create scheduled renewal"}</Button></form> : mode === "cancel" ? <form onSubmit={submitCancel} className="space-y-5">{membership.status !== "scheduled" && <Field label="When should access end?"><Select value={cancelForm.timing} onValueChange={(timing) => setCancelForm({ ...cancelForm, timing })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="term_end">At term end ({dateOnly(membership.ends_on)})</SelectItem><SelectItem value="now">Immediately</SelectItem></SelectContent></Select></Field>}<Surface className="border-danger/30 bg-danger/5 p-4"><p className="text-sm leading-6">{membership.status === "scheduled" ? "The scheduled term is cancelled and its fully unpaid invoice is voided. Paid renewals remain blocked until refunds are supported." : cancelForm.timing === "term_end" ? "Access continues through the term end and this cancellation can be reversed before it becomes effective." : "Access ends immediately. Existing invoices and payment history remain unchanged."}</p></Surface><Field label="Cancellation reason"><Textarea required minLength={3} value={cancelForm.reason} onChange={(event) => setCancelForm({ ...cancelForm, reason: event.target.value })} /></Field><Button disabled={cancelState.isLoading || cancelForm.reason.trim().length < 3} className="w-full bg-danger text-white hover:bg-danger/90">Confirm cancellation</Button></form> : <div className="space-y-5"><Surface className="p-5"><div className="flex items-start justify-between gap-3"><div><div className="overline">Membership state</div><div className="mt-2 font-display text-2xl font-semibold">{membership.plan?.name}</div></div><StatusBadge status={membership.status} /></div><div className="mt-5 grid grid-cols-2 gap-4 border-t pt-4 text-sm"><Meta label="Expires" value={dateOnly(membership.ends_on)} /><Meta label="Trainer" value={membership.trainer?.display_name || "Not assigned"} /></div>{membership.cancellation_effective_on && <div className="mt-4 rounded-xl bg-warning/10 p-3 text-sm text-warning">Cancellation takes effect {dateOnly(membership.cancellation_effective_on)}.</div>}</Surface><div className="grid gap-2 sm:grid-cols-2">{membership.status === "active" && !membership.inside_now && <Button disabled={busy} onClick={() => run("checkin")}>Check in now</Button>}{["active", "frozen", "cancelled", "expired"].includes(membership.status) && !membership.cancellation_effective_on && <Button disabled={busy} variant="outline" onClick={() => setMode("renew")}>Create renewal</Button>}{membership.status === "active" && !membership.cancellation_effective_on && <Button variant="outline" onClick={() => setMode("freeze")}>Freeze membership</Button>}{membership.status === "frozen" && <Button disabled={busy} variant="outline" onClick={() => run("resume")}>Resume membership</Button>}{membership.cancellation_effective_on && ["active", "frozen"].includes(membership.status) && <Button disabled={busy} variant="outline" onClick={() => run("revoke")}>Reverse cancellation</Button>}{["active", "frozen", "scheduled"].includes(membership.status) && <Button variant="ghost" className="text-danger" onClick={() => setMode("cancel")}>Cancel membership</Button>}</div></div>)}</DrawerForm>;
}

function MembershipActionDrawer({ membership, onOpenChange }) {
  const [mode, setMode] = useState("overview");
  const [checkIn, checkState] = useCheckInMemberMutation();
  const [renew, renewState] = useRenewMembershipMutation();
  const [freeze, freezeState] = useFreezeMembershipMutation();
  const [resume, resumeState] = useResumeMembershipMutation();
  const [cancel, cancelState] = useCancelMembershipMutation();
  const [revoke, revokeState] = useRevokeMembershipCancellationMutation();
  const renewalKey = useStableIdempotencyKey();
  const freezeApi = useForm({ resolver: zodResolver(freezeMembershipSchema), defaultValues: { frozen_from: today(), frozen_until: addDays(today(), 7), reason: "", version: 1 }, ...FORM_OPTIONS });
  const cancelApi = useForm({ resolver: zodResolver(cancellationSchema), defaultValues: { reason: "", timing: "term_end", cancel_scheduled_renewal: true, version: 1 }, ...FORM_OPTIONS });
  const renewApi = useForm({ resolver: zodResolver(membershipRenewalSchema), defaultValues: { payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false }, ...FORM_OPTIONS });
  const renewForm = renewApi.watch();
  const cancelTiming = cancelApi.watch("timing");
  const quoteQuery = useGetMembershipQuoteQuery(
    { planId: membership?.plan_id, clientId: membership?.client_id, kind: "renewal", interstate: renewForm.interstate },
    { skip: !membership || mode !== "renew" },
  );
  useEffect(() => {
    if (!membership) return;
    freezeApi.reset({ frozen_from: today(), frozen_until: addDays(today(), 7), reason: "", version: membership.version });
    cancelApi.reset({ reason: "", timing: membership.status === "scheduled" ? "now" : "term_end", cancel_scheduled_renewal: true, version: membership.version });
    renewApi.reset({ payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false });
    renewalKey.reset();
    setMode("overview");
  }, [membership?.id]);

  const run = async (action) => {
    try {
      if (action === "checkin") await checkIn({ location_id: membership.location_id, membership_id: membership.id, method: "staff" }).unwrap();
      if (action === "resume") await resume(membership.id).unwrap();
      if (action === "revoke") await revoke({ membershipId: membership.id, version: membership.version }).unwrap();
      toast.success(action === "checkin" ? "Client checked in" : action === "resume" ? "Membership resumed" : "Cancellation reversed");
      onOpenChange(false);
      setMode("overview");
    } catch (error) {
      toast.error(error?.data?.detail || "Membership action could not be completed");
    }
  };
  const submitFreeze = freezeApi.handleSubmit(async (values) => {
    freezeApi.clearErrors("root.server");
    try {
      await freeze({ membershipId: membership.id, ...values }).unwrap();
      toast.success("Membership frozen");
      onOpenChange(false);
      setMode("overview");
    } catch (error) {
      const normalized = applyApiErrors(error, freezeApi.setError, { fallback: "Membership could not be frozen" });
      toast.error(normalized.message);
    }
  });
  const submitCancel = cancelApi.handleSubmit(async (values) => {
    cancelApi.clearErrors("root.server");
    try {
      await cancel({
        membershipId: membership.id,
        ...values,
        timing: membership.status === "scheduled" ? "now" : values.timing,
      }).unwrap();
      toast.success(values.timing === "term_end" && membership.status !== "scheduled" ? "Cancellation scheduled" : "Membership cancelled");
      onOpenChange(false);
      setMode("overview");
    } catch (error) {
      const normalized = applyApiErrors(error, cancelApi.setError, { fallback: "Membership could not be cancelled" });
      toast.error(normalized.message);
    }
  });
  const submitRenew = renewApi.handleSubmit(async (values) => {
    renewApi.clearErrors("root.server");
    if (!quoteQuery.data) {
      renewApi.setError("root.server", { type: "quote", message: "Wait for the renewal charge to load" });
      return;
    }
    if (values.payment_option === "partial" && Math.round(values.partial_amount * 100) >= Number(quoteQuery.data.total_paise || 0)) {
      renewApi.setError("partial_amount", { type: "maximum", message: "Partial payment must be below the invoice total" }, { shouldFocus: true });
      return;
    }
    try {
      await renew({
        membershipId: membership.id,
        plan_id: membership.plan_id,
        payment_option: values.payment_option,
        partial_payment_paise: values.payment_option === "partial" ? Math.round(values.partial_amount * 100) : null,
        payment_method: values.payment_option === "later" ? null : values.payment_method,
        payment_reference: values.payment_option === "later" ? null : values.payment_reference,
        interstate: values.interstate,
        idempotency_key: renewalKey.current(),
      }).unwrap();
      toast.success("Renewal created with linked invoice");
      renewalKey.reset();
      onOpenChange(false);
      setMode("overview");
    } catch (error) {
      const normalized = applyApiErrors(error, renewApi.setError, { fallback: "Renewal could not be created" });
      toast.error(normalized.message);
    }
  });
  const busy = checkState.isLoading || renewState.isLoading || resumeState.isLoading || revokeState.isLoading || freezeState.isLoading || cancelState.isLoading || freezeApi.formState.isSubmitting || cancelApi.formState.isSubmitting || renewApi.formState.isSubmitting;
  const close = (open) => {
    if (!open && busy) return;
    if (!open) setMode("overview");
    onOpenChange(open);
  };
  return <DrawerForm open={Boolean(membership)} onOpenChange={close} title={membership?.client?.display_name || "Membership"} description={membership ? `${membership.plan?.name || "Plan"} / ${membership.location_name}` : ""}>{membership && (mode === "freeze" ? <form noValidate onSubmit={submitFreeze} className="space-y-5"><Surface className="p-4"><Snowflake className="text-accent" /><p className="mt-3 text-sm text-muted-foreground">The membership becomes unavailable for check-in until it is resumed. The frozen period extends the expiry date on resume.</p></Surface><Field label="Freeze from" error={freezeApi.formState.errors.frozen_from}><Input min={today()} type="date" {...freezeApi.register("frozen_from")} aria-invalid={Boolean(freezeApi.formState.errors.frozen_from)} /></Field><Field label="Freeze until" error={freezeApi.formState.errors.frozen_until}><Input type="date" min={freezeApi.watch("frozen_from")} {...freezeApi.register("frozen_until")} aria-invalid={Boolean(freezeApi.formState.errors.frozen_until)} /></Field><Field label="Reason" error={freezeApi.formState.errors.reason}><Textarea {...freezeApi.register("reason")} placeholder="Optional operational note" aria-invalid={Boolean(freezeApi.formState.errors.reason)} /></Field><FormRootError error={freezeApi.formState.errors.root?.server} /><Button type="submit" disabled={!freezeApi.formState.isValid} loading={freezeState.isLoading || freezeApi.formState.isSubmitting} loadingText="Freezing membership..." className="w-full">Confirm freeze</Button></form> : mode === "renew" ? <form noValidate onSubmit={submitRenew} className="space-y-5"><Surface className="border-primary/30 bg-primary/5 p-4"><p className="text-sm leading-6">The current term remains active. The next term starts after it ends and receives its own invoice.</p></Surface><ValidatedMembershipCheckoutFields form={renewForm} register={renewApi.register} setValue={renewApi.setValue} errors={renewApi.formState.errors} quote={quoteQuery.data} quoteLoading={quoteQuery.isFetching} disabled={busy} /><FormRootError error={renewApi.formState.errors.root?.server} /><Button type="submit" loading={renewState.isLoading || renewApi.formState.isSubmitting} loadingText="Creating renewal..." disabled={!renewApi.formState.isValid || !quoteQuery.data} className="w-full">Create scheduled renewal</Button></form> : mode === "cancel" ? <form noValidate onSubmit={submitCancel} className="space-y-5">{membership.status !== "scheduled" && <Field label="When should access end?" error={cancelApi.formState.errors.timing}><Select value={cancelTiming} onValueChange={(timing) => cancelApi.setValue("timing", timing, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(cancelApi.formState.errors.timing)}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="term_end">At term end ({dateOnly(membership.ends_on)})</SelectItem><SelectItem value="now">Immediately</SelectItem></SelectContent></Select></Field>}<Surface className="border-danger/30 bg-danger/5 p-4"><p className="text-sm leading-6">{membership.status === "scheduled" ? "The scheduled term is cancelled and its fully unpaid invoice is voided. Paid renewals remain blocked until refunds are supported." : cancelTiming === "term_end" ? "Access continues through the term end and this cancellation can be reversed before it becomes effective." : "Access ends immediately. Existing invoices and payment history remain unchanged."}</p></Surface><Field label="Cancellation reason" error={cancelApi.formState.errors.reason}><Textarea {...cancelApi.register("reason")} aria-invalid={Boolean(cancelApi.formState.errors.reason)} /></Field><FormRootError error={cancelApi.formState.errors.root?.server} /><Button type="submit" disabled={!cancelApi.formState.isValid} loading={cancelState.isLoading || cancelApi.formState.isSubmitting} loadingText="Cancelling membership..." className="w-full bg-danger text-white hover:bg-danger/90">Confirm cancellation</Button></form> : <div className="space-y-5"><Surface className="p-5"><div className="flex items-start justify-between gap-3"><div><div className="overline">Membership state</div><div className="mt-2 font-display text-2xl font-semibold">{membership.plan?.name}</div></div><StatusBadge status={membership.status} /></div><div className="mt-5 grid grid-cols-2 gap-4 border-t pt-4 text-sm"><Meta label="Expires" value={dateOnly(membership.ends_on)} /><Meta label="Trainer" value={membership.trainer?.display_name || "Not assigned"} /></div>{membership.cancellation_effective_on && <div className="mt-4 rounded-xl bg-warning/10 p-3 text-sm text-warning">Cancellation takes effect {dateOnly(membership.cancellation_effective_on)}.</div>}</Surface><div className="grid gap-2 sm:grid-cols-2">{membership.status === "active" && !membership.inside_now && <Button loading={checkState.isLoading} disabled={busy && !checkState.isLoading} onClick={() => run("checkin")}>Check in now</Button>}{["active", "frozen", "cancelled", "expired"].includes(membership.status) && !membership.cancellation_effective_on && <Button disabled={busy} variant="outline" onClick={() => setMode("renew")}>Create renewal</Button>}{membership.status === "active" && !membership.cancellation_effective_on && <Button disabled={busy} variant="outline" onClick={() => setMode("freeze")}>Freeze membership</Button>}{membership.status === "frozen" && <Button loading={resumeState.isLoading} disabled={busy && !resumeState.isLoading} variant="outline" onClick={() => run("resume")}>Resume membership</Button>}{membership.cancellation_effective_on && ["active", "frozen"].includes(membership.status) && <Button loading={revokeState.isLoading} disabled={busy && !revokeState.isLoading} variant="outline" onClick={() => run("revoke")}>Reverse cancellation</Button>}{["active", "frozen", "scheduled"].includes(membership.status) && <Button disabled={busy} variant="ghost" className="text-danger" onClick={() => setMode("cancel")}>Cancel membership</Button>}</div></div>)}</DrawerForm>;
}


function LegacyCheckinDrawer({ open, onOpenChange, locationId, memberships }) {
  const [membershipId, setMembershipId] = useState("");
  const [checkIn, state] = useCheckInMemberMutation();
  const eligible = memberships.filter((row) => row.status === "active" && !row.inside_now && row.location_id === locationId);
  const submit = async (event) => { event.preventDefault(); try { await checkIn({ location_id: locationId, membership_id: membershipId, method: "staff" }).unwrap(); toast.success("Check-in recorded"); setMembershipId(""); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Check-in could not be recorded"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Check in Client" description="Only an active membership at this location can create a timestamped visit."><form onSubmit={submit} className="space-y-5"><Field label="Active membership"><Select required value={membershipId} onValueChange={setMembershipId}><SelectTrigger><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{eligible.map((row) => <SelectItem key={row.id} value={row.id}>{row.client?.display_name} · {row.plan?.name}</SelectItem>)}</SelectContent></Select></Field>{!eligible.length && <EmptyState compact icon={CheckCircle} title="No one is ready to check in" description="Clients already inside, frozen memberships, and memberships from other locations are excluded." />}<Button disabled={state.isLoading || !membershipId} className="w-full">{state.isLoading ? "Checking in..." : "Record check-in"}</Button></form></DrawerForm>;
}


function LegacyCoachingDrawer({ kind, onOpenChange }) {
  const clientsQuery = useGetClientsQuery({ locationId: undefined, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !kind));
  const employeesQuery = useGetEmployeesQuery({ limit: 100 }, withSkip(QUERY_POLICIES.reference, !kind || !["trainers", "workouts"].includes(kind)));
  const [assign, assignState] = useAssignTrainerMutation();
  const [measure, measureState] = useAddMeasurementMutation();
  const [workout, workoutState] = useAddWorkoutPlanMutation();
  const [diet, dietState] = useAddDietPlanMutation();
  const [form, setForm] = useState({ client_id: "", trainer_employee_id: "", name: "", details: "", weight: "", height: "", body_fat: "", notes: "" });
  const submit = async (event) => { event.preventDefault(); try { if (kind === "trainers") await assign({ client_id: form.client_id, trainer_employee_id: form.trainer_employee_id, starts_on: today() }).unwrap(); if (kind === "measurements") await measure({ client_id: form.client_id, measured_on: today(), metrics: cleanMetrics({ weight_kg: form.weight, height_cm: form.height, body_fat_percent: form.body_fat }), notes: form.notes || null }).unwrap(); if (kind === "workouts") await workout({ client_id: form.client_id, trainer_employee_id: form.trainer_employee_id || null, name: form.name, schedule: [{ day: "Plan", exercises: form.details }], starts_on: today() }).unwrap(); if (kind === "diets") await diet({ client_id: form.client_id, name: form.name, meals: [{ plan: form.details }], notes: form.notes || null, starts_on: today() }).unwrap(); toast.success(`${sentence(singular(kind))} saved`); setForm({ client_id: "", trainer_employee_id: "", name: "", details: "", weight: "", height: "", body_fat: "", notes: "" }); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Coaching record could not be saved"); } };
  const busy = assignState.isLoading || measureState.isLoading || workoutState.isLoading || dietState.isLoading;
  return <DrawerForm open={Boolean(kind)} onOpenChange={onOpenChange} title={`Add ${singular(kind)}`} description="This record is linked to the Client and attributed to the person creating it."><form onSubmit={submit} className="space-y-5"><Field label="Client"><Select required value={form.client_id} onValueChange={(client_id) => setForm({ ...form, client_id })}><SelectTrigger><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name}</SelectItem>)}</SelectContent></Select></Field>{["trainers", "workouts"].includes(kind) && <Field label="Trainer"><Select required={kind === "trainers"} value={form.trainer_employee_id} onValueChange={(trainer_employee_id) => setForm({ ...form, trainer_employee_id })}><SelectTrigger><SelectValue placeholder="Choose trainer" /></SelectTrigger><SelectContent>{(employeesQuery.data?.items || []).map((employee) => <SelectItem key={employee.id} value={employee.id}>{employee.first_name} {employee.last_name}</SelectItem>)}</SelectContent></Select></Field>}{kind === "measurements" ? <><div className="grid gap-4 sm:grid-cols-3"><Field label="Weight kg"><Input type="number" step="0.1" value={form.weight} onChange={(event) => setForm({ ...form, weight: event.target.value })} /></Field><Field label="Height cm"><Input type="number" step="0.1" value={form.height} onChange={(event) => setForm({ ...form, height: event.target.value })} /></Field><Field label="Body fat %"><Input type="number" step="0.1" value={form.body_fat} onChange={(event) => setForm({ ...form, body_fat: event.target.value })} /></Field></div><Field label="Notes"><Textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field></> : kind !== "trainers" && <><Field label="Plan name"><Input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field><Field label={kind === "workouts" ? "Exercises and guidance" : "Meals and guidance"}><Textarea required value={form.details} onChange={(event) => setForm({ ...form, details: event.target.value })} /></Field><Field label="Notes"><Textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field></>}<Button disabled={busy || !form.client_id} className="w-full">{busy ? "Saving..." : `Save ${singular(kind)}`}</Button></form></DrawerForm>;
}


function CheckinDrawer({ open, onOpenChange, locationId, memberships }) {
  const [checkIn, state] = useCheckInMemberMutation();
  const eligible = memberships.filter((row) => row.status === "active" && !row.inside_now && row.location_id === locationId);
  const formApi = useForm({ resolver: zodResolver(gymCheckinSchema), defaultValues: { membership_id: "" }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, reset, setError, setValue, watch } = formApi;
  const membershipId = watch("membership_id");
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await checkIn({ location_id: locationId, membership_id: values.membership_id, method: "staff" }).unwrap();
      toast.success("Check-in recorded");
      reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Check-in could not be recorded" });
      toast.error(normalized.message);
    }
  });
  const busy = state.isLoading || formState.isSubmitting;
  const close = (next) => { if (!next && busy) return; onOpenChange(next); };
  return <DrawerForm open={open} onOpenChange={close} title="Check in Client" description="Only an active membership at this location can create a timestamped visit."><form noValidate onSubmit={submit} className="space-y-5"><Field label="Active membership" error={formState.errors.membership_id}><Select value={membershipId} onValueChange={(value) => setValue("membership_id", value, { shouldDirty: true, shouldValidate: true })} disabled={busy || !eligible.length}><SelectTrigger aria-invalid={Boolean(formState.errors.membership_id)}><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{eligible.map((row) => <SelectItem key={row.id} value={row.id}>{row.client?.display_name} / {row.plan?.name}</SelectItem>)}</SelectContent></Select></Field>{!eligible.length && <EmptyState compact icon={CheckCircle} title="No one is ready to check in" description="Clients already inside, frozen memberships, and memberships from other locations are excluded." />}<FormRootError error={formState.errors.root?.server} /><Button type="submit" loading={busy} loadingText="Checking in..." disabled={!formState.isValid || !eligible.length} className="w-full">Record check-in</Button></form></DrawerForm>;
}


function CoachingDrawer({ kind, onOpenChange }) {
  const clientsQuery = useGetClientsQuery({ locationId: undefined, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !kind));
  const employeesQuery = useGetEmployeesQuery({ limit: 100 }, withSkip(QUERY_POLICIES.reference, !kind || !["trainers", "workouts"].includes(kind)));
  const [assign, assignState] = useAssignTrainerMutation();
  const [measure, measureState] = useAddMeasurementMutation();
  const [workout, workoutState] = useAddWorkoutPlanMutation();
  const [diet, dietState] = useAddDietPlanMutation();
  const formApi = useForm({ resolver: zodResolver(gymCoachingSchema), defaultValues: emptyCoaching(kind), ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  const clientId = watch("client_id");
  const trainerId = watch("trainer_employee_id");
  useEffect(() => { reset(emptyCoaching(kind)); }, [kind, reset]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      if (values.kind === "trainers") {
        await assign({ client_id: values.client_id, trainer_employee_id: values.trainer_employee_id, starts_on: today() }).unwrap();
      } else if (values.kind === "measurements") {
        await measure({
          client_id: values.client_id,
          measured_on: today(),
          metrics: Object.fromEntries(Object.entries({ weight_kg: values.weight, height_cm: values.height, body_fat_percent: values.body_fat }).filter(([, value]) => value != null)),
          notes: values.notes,
        }).unwrap();
      } else if (values.kind === "workouts") {
        await workout({ client_id: values.client_id, trainer_employee_id: values.trainer_employee_id, name: values.name, schedule: [{ day: "Plan", exercises: values.details }], starts_on: today() }).unwrap();
      } else {
        await diet({ client_id: values.client_id, name: values.name, meals: [{ plan: values.details }], notes: values.notes, starts_on: today() }).unwrap();
      }
      toast.success(`${sentence(singular(values.kind))} saved`);
      reset(emptyCoaching(null));
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Coaching record could not be saved" });
      toast.error(normalized.message);
    }
  });
  const mutationBusy = assignState.isLoading || measureState.isLoading || workoutState.isLoading || dietState.isLoading;
  const busy = mutationBusy || formState.isSubmitting;
  const close = (next) => { if (!next && busy) return; onOpenChange(next); };
  return <DrawerForm open={Boolean(kind)} onOpenChange={close} title={`Add ${singular(kind)}`} description="This record is linked to the Client and attributed to the person creating it."><form noValidate onSubmit={submit} className="space-y-5"><Field label="Client" error={formState.errors.client_id}><Select value={clientId} onValueChange={(value) => setValue("client_id", value, { shouldDirty: true, shouldValidate: true })} disabled={clientsQuery.isLoading || busy}><SelectTrigger aria-invalid={Boolean(formState.errors.client_id)}><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name}</SelectItem>)}</SelectContent></Select></Field>{["trainers", "workouts"].includes(kind) && <Field label="Trainer" error={formState.errors.trainer_employee_id}><Select value={trainerId || "none"} onValueChange={(value) => setValue("trainer_employee_id", value === "none" ? null : value, { shouldDirty: true, shouldValidate: true })} disabled={employeesQuery.isLoading || busy}><SelectTrigger aria-invalid={Boolean(formState.errors.trainer_employee_id)}><SelectValue placeholder="Choose trainer" /></SelectTrigger><SelectContent>{kind === "workouts" && <SelectItem value="none">Unassigned</SelectItem>}{(employeesQuery.data?.items || []).map((employee) => <SelectItem key={employee.id} value={employee.id}>{employee.first_name} {employee.last_name}</SelectItem>)}</SelectContent></Select></Field>}{kind === "measurements" ? <><div className="grid gap-4 sm:grid-cols-3"><Field label="Weight kg" error={formState.errors.weight}><Input inputMode="decimal" {...register("weight")} aria-invalid={Boolean(formState.errors.weight)} /></Field><Field label="Height cm" error={formState.errors.height}><Input inputMode="decimal" {...register("height")} aria-invalid={Boolean(formState.errors.height)} /></Field><Field label="Body fat %" error={formState.errors.body_fat}><Input inputMode="decimal" {...register("body_fat")} aria-invalid={Boolean(formState.errors.body_fat)} /></Field></div><Field label="Notes" error={formState.errors.notes}><Textarea {...register("notes")} aria-invalid={Boolean(formState.errors.notes)} /></Field></> : kind !== "trainers" && <><Field label="Plan name" error={formState.errors.name}><Input {...register("name")} aria-invalid={Boolean(formState.errors.name)} /></Field><Field label={kind === "workouts" ? "Exercises and guidance" : "Meals and guidance"} error={formState.errors.details}><Textarea {...register("details")} aria-invalid={Boolean(formState.errors.details)} /></Field><Field label="Notes" error={formState.errors.notes}><Textarea {...register("notes")} aria-invalid={Boolean(formState.errors.notes)} /></Field></>}<FormRootError error={formState.errors.root?.server} /><Button type="submit" disabled={!formState.isValid} loading={busy} loadingText="Saving coaching record..." className="w-full">Save {singular(kind)}</Button></form></DrawerForm>;
}


function emptyCoaching(kind) {
  return { kind: kind || "trainers", client_id: "", trainer_employee_id: null, name: "", details: "", weight: "", height: "", body_fat: "", notes: "" };
}


function LegacyClassDrawer({ open, onOpenChange, locationId }) {
  const employeesQuery = useGetEmployeesQuery({ limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateGymClassMutation();
  const [form, setForm] = useState({ name: "", trainer_employee_id: "none", starts_at: nextHour(), ends_at: nextHour(1), capacity: "12" });
  const submit = async (event) => { event.preventDefault(); try { await create({ location_id: locationId, name: form.name, trainer_employee_id: form.trainer_employee_id === "none" ? null : form.trainer_employee_id, starts_at: new Date(form.starts_at).toISOString(), ends_at: new Date(form.ends_at).toISOString(), capacity: Number(form.capacity) }).unwrap(); toast.success("Class scheduled"); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Class could not be scheduled"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Schedule class" description="Capacity is locked during booking so the class cannot be oversold."><form onSubmit={submit} className="space-y-5"><Field label="Class name"><Input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field><Field label="Trainer"><Select value={form.trainer_employee_id} onValueChange={(trainer_employee_id) => setForm({ ...form, trainer_employee_id })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{(employeesQuery.data?.items || []).map((employee) => <SelectItem key={employee.id} value={employee.id}>{employee.first_name} {employee.last_name}</SelectItem>)}</SelectContent></Select></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Starts"><Input required type="datetime-local" value={form.starts_at} onChange={(event) => setForm({ ...form, starts_at: event.target.value })} /></Field><Field label="Ends"><Input required type="datetime-local" value={form.ends_at} onChange={(event) => setForm({ ...form, ends_at: event.target.value })} /></Field></div><Field label="Capacity"><Input required type="number" min="1" value={form.capacity} onChange={(event) => setForm({ ...form, capacity: event.target.value })} /></Field><Button disabled={state.isLoading} className="w-full">{state.isLoading ? "Scheduling..." : "Schedule class"}</Button></form></DrawerForm>;
}

function ClassDrawer({ open, onOpenChange, locationId }) {
  const employeesQuery = useGetEmployeesQuery({ limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateGymClassMutation();
  const formApi = useForm({ resolver: zodResolver(gymClassSchema), defaultValues: { name: "", trainer_employee_id: null, starts_at: nextHour(), ends_at: nextHour(1), capacity: "12" }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  const trainer = watch("trainer_employee_id");
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await create({ ...values, location_id: locationId, trainer_employee_id: values.trainer_employee_id || null, starts_at: new Date(values.starts_at).toISOString(), ends_at: new Date(values.ends_at).toISOString() }).unwrap();
      toast.success("Class scheduled");
      reset({ name: "", trainer_employee_id: null, starts_at: nextHour(), ends_at: nextHour(1), capacity: "12" });
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Class could not be scheduled" });
      toast.error(normalized.message);
    }
  });
  const close = (next) => { if (!next && (formState.isSubmitting || state.isLoading)) return; onOpenChange(next); };
  return <DrawerForm open={open} onOpenChange={close} title="Schedule class" description="Capacity is locked during booking so the class cannot be oversold."><form noValidate onSubmit={submit} className="space-y-5"><Field label="Class name" error={formState.errors.name}><Input {...register("name")} aria-invalid={Boolean(formState.errors.name)} /></Field><Field label="Trainer" error={formState.errors.trainer_employee_id}><Select value={trainer || "none"} onValueChange={(value) => setValue("trainer_employee_id", value === "none" ? null : value, { shouldDirty: true, shouldValidate: true })} disabled={employeesQuery.isLoading}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{(employeesQuery.data?.items || []).map((employee) => <SelectItem key={employee.id} value={employee.id}>{employee.first_name} {employee.last_name}</SelectItem>)}</SelectContent></Select></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Starts" error={formState.errors.starts_at}><Input type="datetime-local" {...register("starts_at")} aria-invalid={Boolean(formState.errors.starts_at)} /></Field><Field label="Ends" error={formState.errors.ends_at}><Input type="datetime-local" {...register("ends_at")} aria-invalid={Boolean(formState.errors.ends_at)} /></Field></div><Field label="Capacity" error={formState.errors.capacity}><Input inputMode="numeric" {...register("capacity")} aria-invalid={Boolean(formState.errors.capacity)} /></Field><FormRootError error={formState.errors.root?.server} /><Button type="submit" disabled={!formState.isValid} loading={formState.isSubmitting || state.isLoading} loadingText="Scheduling class..." className="w-full">Schedule class</Button></form></DrawerForm>;
}


function LegacyClassBookingDrawer({ gymClass, onOpenChange, locationId }) {
  const clientsQuery = useGetClientsQuery({ locationId, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !gymClass));
  const [clientId, setClientId] = useState("");
  const [book, state] = useBookGymClassMutation();
  const submit = async (event) => { event.preventDefault(); try { await book({ classId: gymClass.id, client_id: clientId }).unwrap(); toast.success("Class booking confirmed"); setClientId(""); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Class booking could not be completed"); } };
  return <DrawerForm open={Boolean(gymClass)} onOpenChange={onOpenChange} title={gymClass?.name || "Book class"} description={gymClass ? `${gymClass.available} of ${gymClass.capacity} spots available` : ""}><form onSubmit={submit} className="space-y-5"><Field label="Client"><Select required value={clientId} onValueChange={setClientId}><SelectTrigger><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name}</SelectItem>)}</SelectContent></Select></Field><Button disabled={state.isLoading || !clientId} className="w-full">{state.isLoading ? "Booking..." : "Confirm class booking"}</Button></form></DrawerForm>;
}


function ClassBookingDrawer({ gymClass, onOpenChange, locationId }) {
  const clientsQuery = useGetClientsQuery({ locationId, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !gymClass));
  const [book, state] = useBookGymClassMutation();
  const formApi = useForm({ resolver: zodResolver(gymClassBookingSchema), defaultValues: { client_id: "" }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, reset, setError, setValue, watch } = formApi;
  const clientId = watch("client_id");
  useEffect(() => { reset({ client_id: "" }); }, [gymClass?.id, reset]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await book({ classId: gymClass.id, client_id: values.client_id }).unwrap();
      toast.success("Class booking confirmed");
      reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Class booking could not be completed" });
      toast.error(normalized.message);
    }
  });
  const busy = state.isLoading || formState.isSubmitting;
  const close = (next) => { if (!next && busy) return; onOpenChange(next); };
  return <DrawerForm open={Boolean(gymClass)} onOpenChange={close} title={gymClass?.name || "Book class"} description={gymClass ? `${gymClass.available} of ${gymClass.capacity} spots available` : ""}><form noValidate onSubmit={submit} className="space-y-5"><Field label="Client" error={formState.errors.client_id}><Select value={clientId} onValueChange={(value) => setValue("client_id", value, { shouldDirty: true, shouldValidate: true })} disabled={clientsQuery.isLoading || busy}><SelectTrigger aria-invalid={Boolean(formState.errors.client_id)}><SelectValue placeholder="Choose Client" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name}</SelectItem>)}</SelectContent></Select></Field><FormRootError error={formState.errors.root?.server} /><Button type="submit" loading={busy} loadingText="Booking class..." disabled={!formState.isValid || !gymClass || gymClass.available <= 0} className="w-full">Confirm class booking</Button></form></DrawerForm>;
}


function LegacyEquipmentDrawer({ open, onOpenChange, locationId }) {
  const [create, state] = useCreateGymEquipmentMutation();
  const [form, setForm] = useState({ name: "", asset_code: "", purchased_on: "", next_service_on: "", notes: "" });
  const submit = async (event) => { event.preventDefault(); try { await create({ ...form, location_id: locationId, purchased_on: form.purchased_on || null, next_service_on: form.next_service_on || null, notes: form.notes || null }).unwrap(); toast.success("Equipment added"); setForm({ name: "", asset_code: "", purchased_on: "", next_service_on: "", notes: "" }); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Equipment could not be added"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Add equipment" description="Record the asset and its next maintenance date before it enters service."><form onSubmit={submit} className="space-y-5"><Field label="Equipment name"><Input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field><Field label="Asset code"><Input required value={form.asset_code} onChange={(event) => setForm({ ...form, asset_code: event.target.value })} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Purchased on"><Input type="date" value={form.purchased_on} onChange={(event) => setForm({ ...form, purchased_on: event.target.value })} /></Field><Field label="Next service"><Input type="date" value={form.next_service_on} onChange={(event) => setForm({ ...form, next_service_on: event.target.value })} /></Field></div><Field label="Notes"><Textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} /></Field><Button disabled={state.isLoading} className="w-full">{state.isLoading ? "Adding..." : "Add equipment"}</Button></form></DrawerForm>;
}

function EquipmentDrawer({ open, onOpenChange, locationId }) {
  const [create, state] = useCreateGymEquipmentMutation();
  const formApi = useForm({ resolver: zodResolver(equipmentSchema), defaultValues: { name: "", asset_code: "", purchased_on: "", next_service_on: "", notes: "" }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError } = formApi;
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await create({ ...values, location_id: locationId }).unwrap();
      toast.success("Equipment added");
      reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Equipment could not be added" });
      toast.error(normalized.message);
    }
  });
  const close = (next) => { if (!next && (formState.isSubmitting || state.isLoading)) return; onOpenChange(next); };
  return <DrawerForm open={open} onOpenChange={close} title="Add equipment" description="Record the asset and its next maintenance date before it enters service."><form noValidate onSubmit={submit} className="space-y-5"><Field label="Equipment name" error={formState.errors.name}><Input {...register("name")} aria-invalid={Boolean(formState.errors.name)} /></Field><Field label="Asset code" error={formState.errors.asset_code}><Input {...register("asset_code")} aria-invalid={Boolean(formState.errors.asset_code)} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Purchased on" error={formState.errors.purchased_on}><Input type="date" {...register("purchased_on")} aria-invalid={Boolean(formState.errors.purchased_on)} /></Field><Field label="Next service" error={formState.errors.next_service_on}><Input type="date" {...register("next_service_on")} aria-invalid={Boolean(formState.errors.next_service_on)} /></Field></div><Field label="Notes" error={formState.errors.notes}><Textarea {...register("notes")} aria-invalid={Boolean(formState.errors.notes)} /></Field><FormRootError error={formState.errors.root?.server} /><Button type="submit" disabled={!formState.isValid} loading={formState.isSubmitting || state.isLoading} loadingText="Adding equipment..." className="w-full">Add equipment</Button></form></DrawerForm>;
}


function PanelHeader({ title, copy, action }) { return <div className="flex items-center justify-between gap-4 border-b p-5"><div><h2 className="font-display text-2xl font-semibold">{title}</h2><p className="mt-1 text-sm text-muted-foreground">{copy}</p></div>{action}</div>; }
function Field({ label, children, error }) { return <div className="space-y-2"><Label>{label}</Label>{children}<FieldError error={error} /></div>; }
function Meta({ label, value }) { return <div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 font-medium">{value}</div></div>; }
function money(value) { return formatMetric(value, "money"); }
function dateOnly(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`)) : "Not set"; }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)) : "Not set"; }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function singular(kind) { return ({ trainers: "trainer assignment", measurements: "measurement", workouts: "workout plan", diets: "diet plan" }[kind] || "record"); }
function managePermission(kind) { return ({ trainers: "gym.coaching.manage", measurements: "gym.measurements.manage", workouts: "gym.workouts.manage", diets: "gym.diets.manage" }[kind]); }
function today() { return new Date().toLocaleDateString("en-CA"); }
function addDays(value, days) { const result = new Date(`${value}T00:00:00`); result.setDate(result.getDate() + days); return result.toLocaleDateString("en-CA"); }
function daysRemaining(value) { return Math.max(Math.ceil((new Date(`${value}T23:59:59`) - new Date()) / 86400000), 0); }
function duration(start, end) { return Math.max(Math.round((new Date(end) - new Date(start)) / 60000), 0); }
function isToday(value) { return new Date(value).toDateString() === new Date().toDateString(); }
function nextHour(offset = 0) { const value = new Date(); value.setMinutes(0, 0, 0); value.setHours(value.getHours() + 1 + offset); const local = new Date(value.getTime() - value.getTimezoneOffset() * 60000); return local.toISOString().slice(0, 16); }
function cleanMetrics(metrics) { return Object.fromEntries(Object.entries(metrics).filter(([, value]) => value !== "").map(([key, value]) => [key, Number(value)])); }
