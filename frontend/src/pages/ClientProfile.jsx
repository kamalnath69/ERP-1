import React, { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowClockwise, ArrowLeft, Barbell, CalendarBlank, Camera, CaretRight, CheckCircle,
  Clock, DotsThree, Envelope, FileArrowUp, GraduationCap, Heartbeat, IdentificationCard,
  MapPin, NotePencil, Phone, Plus, Receipt, Snowflake, TrendUp, Wallet,
  WarningCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import api from "@/lib/api";
import { clientLabel } from "@/app/routeManifest";
import {
  CursorListFooter, DrawerForm, EmptyState, ErrorState, PageShell, StatusBadge, Surface, formatMetric,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { FieldError, FormRootError } from "@/components/ui/form";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  useAddClientCommitmentMutation, useAddClientMemoryMutation,
  useCheckInClientMutation, useCheckOutClientMutation, useDeleteClientMediaMutation,
  useGetClientMediaQuery, useGetClientTimelineQuery, useGetClientWorkspaceQuery,
  useUpdateClientMutation, useUpdateClientSignalMutation, useUploadClientMediaMutation,
} from "@/features/clients/clientApi";
import {
  useAddMeasurementMutation, useCancelMembershipMutation, useCreateMembershipMutation,
  useFreezeMembershipMutation, useGetMembershipPlansQuery, useGetMembershipQuoteQuery,
  useRenewMembershipMutation, useResumeMembershipMutation,
  useRevokeMembershipCancellationMutation,
} from "@/features/gym/gymApi";
import { PaymentDrawer, VoidInvoiceDrawer } from "@/features/sales/InvoiceActions";
import CollegeStudentProfile from "@/components/college/CollegeStudentProfile";
import { useGetCollegeStudentPlacementProfileQuery } from "@/features/college/collegeApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import useCursorPagination from "@/hooks/useCursorPagination";
import { usePendingAction, useStableIdempotencyKey } from "@/hooks/usePendingAction";
import {
  applyApiErrors, cancellationSchema, clientCommitmentSchema, clientMeasurementSchema,
  clientMemorySchema, clientProfileEditSchema, FORM_OPTIONS, membershipSchema,
  profileFreezeSchema, validateFile,
} from "@/lib/validation";


const EMPTY_ACTION = { type: "", values: {} };


export default function ClientProfile() {
  const { clientId } = useParams();
  const navigate = useNavigate();
  const { can } = useAuth();
  const { locationId, industry: businessIndustry } = useBusiness();
  const [activeTab, setActiveTab] = useState("overview");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [action, setAction] = useState(EMPTY_ACTION);
  const [checkout, setCheckout] = useState(null);
  const [cancelling, setCancelling] = useState(null);
  const [paying, setPaying] = useState(null);
  const [voiding, setVoiding] = useState(null);
  const [photoUrl, setPhotoUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const fileActions = usePendingAction();

  const workspaceQuery = useGetClientWorkspaceQuery({ clientId, range: "30d" }, QUERY_POLICIES.operational);
  const { data: workspace } = workspaceQuery;
  const collegeStudentProfileId = workspace?.industry === "college" ? workspace.industry_data?.profile?.id : null;
  const collegePlacementQuery = useGetCollegeStudentPlacementProfileQuery(
    collegeStudentProfileId,
    withSkip(QUERY_POLICIES.operational, !collegeStudentProfileId),
  );
  const timelinePaging = useCursorPagination(JSON.stringify({ clientId, activity: true }));
  const timelineQuery = useGetClientTimelineQuery(
    { clientId, cursor: timelinePaging.cursor, limit: 50 },
    withSkip(QUERY_POLICIES.reference, activeTab !== "activity" || workspace?.industry === "college"),
  );
  const mediaQuery = useGetClientMediaQuery(
    clientId,
    withSkip(QUERY_POLICIES.reference, !detailsOpen || !workspace?.actions?.view_media),
  );
  const plansQuery = useGetMembershipPlansQuery(undefined, withSkip(QUERY_POLICIES.reference, workspace?.industry !== "gym"));

  const [updateClient] = useUpdateClientMutation();
  const [addMemory] = useAddClientMemoryMutation();
  const [addCommitment] = useAddClientCommitmentMutation();
  const [patchSignal] = useUpdateClientSignalMutation();
  const [uploadMedia] = useUploadClientMediaMutation();
  const [deleteMedia] = useDeleteClientMediaMutation();
  const [checkIn] = useCheckInClientMutation();
  const [checkOut] = useCheckOutClientMutation();
  const [addMeasurement] = useAddMeasurementMutation();
  const [freezeMembership] = useFreezeMembershipMutation();
  const [resumeMembership] = useResumeMembershipMutation();
  const [revokeCancellation] = useRevokeMembershipCancellationMutation();

  const { accept: acceptTimeline } = timelinePaging;
  useEffect(() => { acceptTimeline(timelineQuery.data); }, [acceptTimeline, timelineQuery.data]);

  useEffect(() => {
    let objectUrl = "";
    if (!workspace?.profile_photo_url) {
      setPhotoUrl("");
      return undefined;
    }
    api.get(workspace.profile_photo_url, { responseType: "blob" }).then(({ data }) => {
      objectUrl = URL.createObjectURL(data);
      setPhotoUrl(objectUrl);
    }).catch(() => setPhotoUrl(""));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [workspace?.profile_photo_url]);

  if (workspaceQuery.isLoading && !workspace) return <ProfileSkeleton />;
  if (workspaceQuery.isError && !workspace) return <PageShell><ErrorState title={`${clientLabel(businessIndustry, false)} unavailable`} description={workspaceQuery.error?.data?.detail} retry={workspaceQuery.refetch} /></PageShell>;

  const client = workspace.client;
  const singularLabel = clientLabel(workspace.industry, false);
  const pluralLabel = clientLabel(workspace.industry);
  const industry = workspace.industry_data || {};
  const currentMembership = industry.current_membership || industry.active_membership;
  const scheduledMembership = industry.scheduled_membership;
  const fullName = `${client.first_name} ${client.last_name}`.trim();
  const identityNumber = workspace.industry === "college"
    ? industry.profile?.admission_number || client.client_number
    : client.client_number;
  const progressVisible = workspace.industry === "gym" && Boolean(
    industry.measurements?.length || industry.goals?.length || industry.workout_sessions?.length || workspace.actions.manage_measurements,
  );

  const markAttendance = async () => {
    setBusy(true);
    try {
      if (industry.open_checkin) await checkOut({ clientId }).unwrap();
      else await checkIn({ clientId, location_id: locationId || client.home_location_id, notes: null }).unwrap();
      toast.success(industry.open_checkin ? "Client checked out" : "Client checked in");
    } catch (error) {
      toast.error(errorMessage(error, "Attendance could not be updated"));
    } finally {
      setBusy(false);
    }
  };

  const runMembershipAction = async (kind) => {
    setBusy(true);
    try {
      if (kind === "resume") await resumeMembership(currentMembership.id).unwrap();
      if (kind === "revoke") await revokeCancellation({ membershipId: currentMembership.id, version: currentMembership.version }).unwrap();
      toast.success(kind === "resume" ? "Membership resumed" : "Cancellation reversed");
    } catch (error) {
      toast.error(errorMessage(error, "Membership could not be updated"));
    } finally {
      setBusy(false);
    }
  };

  const updateSignal = async (signal, actionName) => {
    try {
      await patchSignal({ signalId: signal.id, action: actionName, version: signal.version, note: actionName === "resolve" ? "Handled from Client profile" : null }).unwrap();
      toast.success(actionName === "resolve" ? "Marked as resolved" : "Snoozed for seven days");
    } catch (error) {
      toast.error(errorMessage(error, "Attention item could not be updated"));
    }
  };

  const submitAction = async (type, values) => {
    setBusy(true);
    try {
      if (type === "edit") await updateClient({
        clientId,
        first_name: values.first_name,
        last_name: values.last_name,
        phone: values.phone || null,
        email: values.email || null,
        address: values.address || null,
        notes: values.notes || null,
        status: values.status,
        whatsapp_consent: Boolean(values.whatsapp_consent),
        email_consent: Boolean(values.email_consent),
        version: values.version,
      }).unwrap();
      if (type === "memory") await addMemory({ clientId, category: values.category, label: values.label, value: values.value, visibility: values.visibility }).unwrap();
      if (type === "commitment") await addCommitment({ clientId, title: values.title, description: values.description || null, due_at: values.due_at ? new Date(values.due_at).toISOString() : null }).unwrap();
      if (type === "measurement") await addMeasurement({ client_id: clientId, measured_on: values.measured_on, metrics: compactMetrics(values), notes: values.notes || null }).unwrap();
      if (type === "freeze") await freezeMembership({ membershipId: currentMembership.id, frozen_from: values.frozen_from, frozen_until: values.frozen_until, version: currentMembership.version }).unwrap();
      toast.success("Update saved");
      setAction(EMPTY_ACTION);
    } catch (error) {
      toast.error(errorMessage(error, "This update could not be saved"));
      throw error;
    } finally {
      setBusy(false);
    }
  };

  const uploadClientFile = async (event, kind = "attachment") => {
    const input = event.target;
    const file = event.target.files?.[0];
    if (!file) return;
    const profilePhoto = kind === "profile_photo";
    const maximum = profilePhoto ? 5 * 1024 * 1024 : file.type.startsWith("video/") ? 100 * 1024 * 1024 : 20 * 1024 * 1024;
    const validation = validateFile(file, {
      label: profilePhoto ? "Profile photo" : "Private file",
      maxBytes: maximum,
      extensions: profilePhoto ? [".jpg", ".jpeg", ".png", ".webp"] : [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".pdf", ".docx", ".txt"],
      mimeTypes: profilePhoto ? ["image/jpeg", "image/png", "image/webp"] : ["image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"],
    });
    if (validation) { toast.error(validation); input.value = ""; return; }
    await fileActions.run(`upload:${kind}`, async () => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("media_kind", kind);
      formData.append("visibility", "team");
      try {
        await uploadMedia({ clientId, formData }).unwrap();
        toast.success(profilePhoto ? "Profile photo updated" : "Private file uploaded");
      } catch (error) {
        toast.error(errorMessage(error, "Upload failed"));
      } finally {
        input.value = "";
      }
    });
  };

  const openPrivateFile = async (item) => {
    try {
      const { data } = await api.get(item.content_url, { responseType: "blob" });
      const objectUrl = URL.createObjectURL(data);
      window.open(objectUrl, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    } catch {
      toast.error("This private file could not be opened");
    }
  };

  const primaryActions = [
    client.phone && <Button key="call" asChild variant="outline"><a href={`tel:${client.phone}`}><Phone className="mr-2" />Call</a></Button>,
    workspace.industry === "gym" && workspace.actions.mark_attendance && currentMembership && <Button key="attendance" disabled={busy || currentMembership.status === "frozen"} onClick={markAttendance}><CheckCircle className="mr-2" />{industry.open_checkin ? "Check out" : "Check in"}</Button>,
  ].filter(Boolean);

  return <PageShell className="reveal">
    <div className="flex items-center justify-between gap-3">
      <Button asChild variant="ghost" className="-ml-3"><Link to="/app/clients"><ArrowLeft className="mr-2" />{pluralLabel}</Link></Button>
      <span className="text-xs text-muted-foreground">{workspace.industry === "college" ? "Student profile" : "Operational profile"}</span>
    </div>

    <Surface className="overflow-hidden">
      <div className="detail-hero flex flex-col gap-5 p-5 sm:p-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          <div className="relative shrink-0">
            <div className="grid h-16 w-16 place-items-center overflow-hidden rounded-2xl border bg-secondary sm:h-20 sm:w-20">
              {photoUrl ? <img src={photoUrl} alt={fullName} className="h-full w-full object-cover" /> : <span className="font-display text-3xl">{client.first_name?.[0]}</span>}
            </div>
            {workspace.actions.manage_media && <label aria-busy={fileActions.isPending("upload:profile_photo")} className={`absolute -bottom-1 -right-1 grid h-7 w-7 place-items-center rounded-lg bg-accent text-accent-foreground shadow ${fileActions.isPending("upload:profile_photo") ? "cursor-wait opacity-60" : "cursor-pointer"}`}><Camera size={15} /><input hidden disabled={fileActions.isPending("upload:profile_photo")} type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => uploadClientFile(event, "profile_photo")} /></label>}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><span className="overline">{identityNumber}</span><StatusBadge status={industry.profile?.status || client.status} /></div>
            <h1 className="mt-1 truncate font-display text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">{fullName}</h1>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
              {workspace.location?.name && <span className="inline-flex items-center gap-1"><MapPin />{workspace.location.name}</span>}
              {client.phone && <span>{client.phone}</span>}
              {client.email && <span>{client.email}</span>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {primaryActions}
          <ProfileMenu
            workspace={workspace}
            current={currentMembership}
            scheduled={scheduledMembership}
            openDetails={() => setDetailsOpen(true)}
            openAction={(type, values = {}) => setAction({ type, values })}
            openCheckout={(mode, membership) => setCheckout({ mode, membership })}
            openCancellation={setCancelling}
            resume={() => runMembershipAction("resume")}
            revoke={() => runMembershipAction("revoke")}
          />
        </div>
      </div>
    </Surface>

    {workspace.industry === "college" ? <CollegeStudentProfile query={collegePlacementQuery} canReviewFees={can("college.clearance.view") || can("college.fees.view") || can("college.fees.manage")} onReviewFees={() => navigate("/app/college?section=clearance")} /> : <Tabs value={activeTab} onValueChange={setActiveTab}>
      <TabsList className="premium-scrollbar h-auto max-w-full justify-start overflow-x-auto rounded-xl p-1">
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="operations">{operationsLabel(workspace.industry)}</TabsTrigger>
        <TabsTrigger value="billing">Billing{workspace.billing?.summary?.outstanding_paise > 0 ? ` (${money(workspace.billing.summary.outstanding_paise)})` : ""}</TabsTrigger>
        <TabsTrigger value="activity">Activity</TabsTrigger>
        {progressVisible && <TabsTrigger value="progress">Progress</TabsTrigger>}
      </TabsList>

      <TabsContent value="overview" className="mt-5">
        <Overview
          workspace={workspace}
          current={currentMembership}
          scheduled={scheduledMembership}
          openCheckout={(mode, membership) => setCheckout({ mode, membership })}
          openCancellation={setCancelling}
          openBilling={() => setActiveTab("billing")}
          updateSignal={updateSignal}
        />
      </TabsContent>
      <TabsContent value="operations" className="mt-5"><Operations workspace={workspace} navigate={navigate} /></TabsContent>
      <TabsContent value="billing" className="mt-5"><Billing workspace={workspace} navigate={navigate} setPaying={setPaying} setVoiding={setVoiding} /></TabsContent>
      <TabsContent value="activity" className="mt-5"><Activity
        rows={timelinePaging.items}
        loading={timelineQuery.isLoading && !timelinePaging.items.length}
        fetching={timelineQuery.isFetching}
        error={timelineQuery.isError}
        hasMore={Boolean(timelineQuery.data?.has_more)}
        loadMore={() => timelinePaging.loadMore(timelineQuery.data?.next_cursor)}
        retry={timelineQuery.refetch}
      /></TabsContent>
      {progressVisible && <TabsContent value="progress" className="mt-5"><Progress data={industry} canAdd={workspace.actions.manage_measurements} add={() => setAction({ type: "measurement", values: {} })} /></TabsContent>}
    </Tabs>}

    <DetailsDrawer
      open={detailsOpen}
      onOpenChange={setDetailsOpen}
      workspace={workspace}
      media={mediaQuery.data}
      mediaLoading={mediaQuery.isLoading}
      uploadPending={fileActions.isPending("upload:attachment")}
      openAction={(type, values = {}) => { setDetailsOpen(false); setAction({ type, values }); }}
      upload={uploadClientFile}
      entityLabel={singularLabel}
      openFile={openPrivateFile}
      removeFile={async (item) => {
        try { await deleteMedia({ mediaId: item.id, clientId }).unwrap(); toast.success("File removed"); }
        catch (error) { toast.error(errorMessage(error, "File could not be removed")); }
      }}
    />
    <ActionDrawer key={`${action.type}:${action.values?.id || "new"}`} action={action} client={client} entityLabel={singularLabel} busy={busy} close={() => setAction(EMPTY_ACTION)} submit={submitAction} />
    <MembershipCheckout
      checkout={checkout}
      onOpenChange={(open) => !open && setCheckout(null)}
      client={client}
      plans={plansQuery.data || []}
      locationId={locationId || client.home_location_id}
    />
    <CancellationDrawer
      membership={cancelling}
      scheduled={scheduledMembership && scheduledMembership.id !== cancelling?.id ? scheduledMembership : null}
      onOpenChange={(open) => !open && setCancelling(null)}
    />
    <PaymentDrawer invoice={paying} onOpenChange={(open) => !open && setPaying(null)} />
    <VoidInvoiceDrawer invoice={voiding} onOpenChange={(open) => !open && setVoiding(null)} />
  </PageShell>;
}


function ProfileMenu({ workspace, current, scheduled, openDetails, openAction, openCheckout, openCancellation, resume, revoke }) {
  const client = workspace.client;
  const isCollege = workspace.industry === "college";
  return <DropdownMenu>
    <DropdownMenuTrigger asChild><Button variant="outline"><DotsThree className="mr-2" />More</Button></DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-56">
      <DropdownMenuItem onSelect={openDetails}><IdentificationCard />Details, notes and files</DropdownMenuItem>
      {workspace.actions.edit_client && <DropdownMenuItem onSelect={() => openAction("edit", client)}><NotePencil />Edit profile</DropdownMenuItem>}
      {workspace.actions.manage_memory && <DropdownMenuItem onSelect={() => openAction("memory")}><Plus />Add {isCollege ? "student" : "relationship"} note</DropdownMenuItem>}
      {workspace.actions.manage_memory && <DropdownMenuItem onSelect={() => openAction("commitment")}><Clock />Add follow-up</DropdownMenuItem>}
      {workspace.industry === "gym" && workspace.actions.manage_membership && <DropdownMenuSeparator />}
      {workspace.industry === "gym" && workspace.actions.manage_membership && !current && !scheduled && <DropdownMenuItem onSelect={() => openCheckout("activation", null)}><Wallet />Activate membership</DropdownMenuItem>}
      {workspace.industry === "gym" && workspace.actions.manage_membership && current && !scheduled && <DropdownMenuItem onSelect={() => openCheckout("renewal", current)}><ArrowClockwise />Create renewal</DropdownMenuItem>}
      {current?.status === "active" && workspace.actions.manage_membership && <DropdownMenuItem onSelect={() => openAction("freeze")}><Snowflake />Freeze membership</DropdownMenuItem>}
      {current?.status === "frozen" && workspace.actions.manage_membership && <DropdownMenuItem onSelect={resume}><CheckCircle />Resume membership</DropdownMenuItem>}
      {current?.cancellation_pending && workspace.actions.manage_membership && <DropdownMenuItem onSelect={revoke}><ArrowClockwise />Reverse cancellation</DropdownMenuItem>}
      {current && workspace.actions.manage_membership && <DropdownMenuItem className="text-danger" onSelect={() => openCancellation(current)}><WarningCircle />Cancel membership</DropdownMenuItem>}
      {scheduled && workspace.actions.manage_membership && <DropdownMenuItem className="text-danger" onSelect={() => openCancellation(scheduled)}><WarningCircle />Cancel scheduled renewal</DropdownMenuItem>}
    </DropdownMenuContent>
  </DropdownMenu>;
}


function Overview({ workspace, current, scheduled, openCheckout, openCancellation, openBilling, updateSignal }) {
  const appointments = workspace.appointments || [];
  const upcoming = appointments.filter((item) => ["scheduled", "confirmed"].includes(item.status) && new Date(item.starts_at) >= new Date()).sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))[0];
  const signals = workspace.signals || [];
  const isGym = workspace.industry === "gym";
  const isCollege = workspace.industry === "college";
  const academics = workspace.industry_data || {};
  return <div className="grid items-start gap-5 xl:grid-cols-12">
    {isCollege && academics.profile && <Surface className="overflow-hidden xl:col-span-12">
      <PanelHeader title="Academic position" subtitle="Current enrollment and attendance at a glance." />
      <div className="grid gap-px bg-border sm:grid-cols-2 xl:grid-cols-5">
        <MetaCell label="Program" value={academics.program?.name || "Not assigned"} />
        <MetaCell label="Cohort" value={academics.cohort?.name || "Not assigned"} />
        <MetaCell label="Semester" value={academics.profile.current_semester || "-"} />
        <MetaCell label="Attendance" value={academics.attendance_summary?.percentage == null ? "No classes yet" : `${academics.attendance_summary.percentage}%`} />
        <MetaCell label="Active courses" value={academics.courses?.length || 0} />
      </div>
    </Surface>}
    {isGym && <div className={`space-y-4 ${signals.length ? "xl:col-span-7" : "xl:col-span-12"}`}>
      <MembershipCard membership={current} kind="current" canManage={workspace.actions.manage_membership} onCheckout={() => openCheckout(current ? "renewal" : "activation", current)} onCancel={() => current && openCancellation(current)} />
      {scheduled && <MembershipCard membership={scheduled} kind="scheduled" canManage={workspace.actions.manage_membership} onCancel={() => openCancellation(scheduled)} />}
    </div>}
    {signals.length > 0 && <Surface className={`${isGym ? "xl:col-span-5" : upcoming ? "xl:col-span-6" : "xl:col-span-12"} overflow-hidden`}>
      <PanelHeader title="Needs attention" subtitle="Only current, actionable signals are shown." />
      <div className="divide-y">{signals.map((signal) => <div key={signal.id} className="p-5"><div className="flex items-start gap-3"><span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-warning/10 text-warning"><Heartbeat /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{signal.title}</h3><StatusBadge status={signal.pulse_state} /></div><p className="mt-1 text-sm leading-6 text-muted-foreground">{signal.explanation}</p>{workspace.actions.manage_signals && <div className="mt-3 flex gap-2"><Button size="sm" variant="outline" onClick={() => updateSignal(signal, "resolve")}>Resolve</Button><Button size="sm" variant="ghost" onClick={() => updateSignal(signal, "snooze")}>Snooze</Button></div>}</div></div></div>)}</div>
    </Surface>}
    {upcoming && <Surface className={`${isGym ? "xl:col-span-5" : signals.length ? "xl:col-span-6" : "xl:col-span-12"} overflow-hidden`}>
      <PanelHeader title="Next interaction" subtitle="The nearest scheduled client touchpoint." />
      <div className="p-5"><div className="flex gap-3"><span className="state-icon"><CalendarBlank /></span><div><div className="font-semibold">Appointment</div><div className="mt-1 text-sm text-muted-foreground">{dateTime(upcoming.starts_at)}</div><StatusBadge status={upcoming.status} className="mt-3" /></div></div></div>
    </Surface>}
    <Surface className={`${isGym && upcoming ? "xl:col-span-7" : "xl:col-span-12"} overflow-hidden`}>
      <PanelHeader title={isCollege ? "Fee position" : "Billing position"} subtitle={isCollege ? "Student fee invoices and the amount still due." : "Invoice-backed values, not a profile score."} action={workspace.billing?.capabilities?.view && <Button size="sm" variant="outline" onClick={openBilling}>Open {isCollege ? "fees" : "billing"}<CaretRight className="ml-1" /></Button>} />
      {workspace.billing?.summary ? <div className="grid grid-cols-1 divide-y p-5 sm:grid-cols-3 sm:divide-x sm:divide-y-0"><MoneyStat label="Invoiced" value={workspace.billing.summary.invoiced_paise} /><MoneyStat label="Paid" value={workspace.billing.summary.paid_paise} /><MoneyStat label="Outstanding" value={workspace.billing.summary.outstanding_paise} warning={workspace.billing.summary.outstanding_paise > 0} /></div> : <div className="p-5 text-sm text-muted-foreground">Financial details are outside this role's access.</div>}
    </Surface>
  </div>;
}


function MembershipCard({ membership, kind, canManage, onCheckout, onCancel }) {
  if (!membership) return <Surface className="overflow-hidden"><PanelHeader title="Membership" subtitle="No current or scheduled term." /><EmptyState variant="section" alignment="left" icon={Wallet} title="No active membership" description="Activate a plan and choose how its invoice will be paid." action={canManage && <Button onClick={onCheckout}>Activate membership</Button>} className="m-4" /></Surface>;
  const invoice = membership.invoice;
  return <Surface className="overflow-hidden">
    <div className="border-b p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div><div className="overline">{kind === "scheduled" ? "Scheduled next term" : "Current membership"}</div><h2 className="mt-1 font-display text-2xl font-semibold">{membership.plan?.name || "Legacy membership"}</h2><div className="mt-2 flex flex-wrap gap-2"><StatusBadge status={membership.status} />{membership.cancellation_pending && <StatusBadge status="warning" label={`Cancels ${dateOnly(membership.cancellation_effective_on)}`} />}{membership.legacy_unlinked && <StatusBadge status="neutral" label="Legacy / unlinked" />}</div></div>
        {canManage && <div className="flex flex-wrap gap-2">{kind === "current" && !membership.cancellation_pending && <Button size="sm" onClick={onCheckout}><ArrowClockwise className="mr-2" />Renew</Button>}<Button size="sm" variant="outline" className="text-danger" onClick={onCancel}>Cancel</Button></div>}
      </div>
    </div>
    <div className="grid gap-px bg-border sm:grid-cols-4">
      <MetaCell label="Valid from" value={dateOnly(membership.starts_on)} />
      <MetaCell label="Valid through" value={dateOnly(membership.ends_on)} />
      <MetaCell label={kind === "current" ? "Days remaining" : "Duration"} value={kind === "current" ? membership.days_remaining : `${membership.plan?.duration_days || "-"} days`} />
      <MetaCell label="Term charge" value={money(membership.term_charge_paise)} />
    </div>
    <div className="flex flex-col gap-3 border-t p-5 sm:flex-row sm:items-center sm:justify-between">
      {invoice ? <><div><div className="text-sm font-semibold">Invoice {invoice.invoice_number}</div><div className="mt-1 text-xs text-muted-foreground">{invoice.item_names?.join(", ") || "Membership charge"}</div></div><div className="flex items-center gap-3"><StatusBadge status={invoice.status} /><span className="text-sm font-semibold">{money(invoice.balance_paise)} due</span></div></> : <p className="text-sm text-muted-foreground">This historical term is intentionally not linked to a guessed invoice.</p>}
    </div>
  </Surface>;
}


function Operations({ workspace, navigate }) {
  const data = workspace.industry_data || {};
  if (workspace.industry === "college") {
    if (!data.academic_access) return <EmptyState variant="section" alignment="left" icon={GraduationCap} title="Academic context is outside your access" description="Student enrollment, attendance, and results require an authorized College role." />;
    if (!data.profile) return <EmptyState variant="section" alignment="left" icon={GraduationCap} title="Enrollment is not connected" description="This identity exists, but it is not linked to a College admission record." primaryAction={<Button onClick={() => navigate("/app/college?section=students&new=1")}>Open admissions</Button>} />;
    const attendance = data.attendance_summary || {};
    return <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label="Current semester" value={data.profile.current_semester} format="plain" />
        <SummaryCard label="Courses" value={data.courses?.length || 0} format="plain" />
        <SummaryCard label="Classes recorded" value={attendance.total_classes || 0} format="plain" />
        <SummaryCard label="Attendance" value={attendance.percentage == null ? "-" : `${attendance.percentage}%`} format="plain" warning={attendance.percentage != null && attendance.percentage < 75} />
      </div>
      <div className="grid items-start gap-5 xl:grid-cols-2">
        <Surface className="p-5">
          <div className="flex items-center gap-3"><span className="state-icon"><GraduationCap /></span><div><h2 className="font-display text-xl font-semibold">Enrollment</h2><p className="mt-0.5 text-xs text-muted-foreground">Admission and current academic placement</p></div></div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <Info label="Admission number" value={data.profile.admission_number} />
            <Info label="Roll number" value={data.profile.roll_number || "Not assigned"} />
            <Info label="Program" value={data.program?.name || "Not assigned"} />
            <Info label="Department" value={data.department?.name || "Not assigned"} />
            <Info label="Cohort" value={data.cohort?.name || "Not assigned"} />
            <Info label="Admitted on" value={dateOnly(data.profile.admitted_on)} />
          </div>
        </Surface>
        {data.courses?.length > 0 && <ListPanel title="Current courses" rows={data.courses} render={(row) => ({ title: `${row.course_code} / ${row.course_name}`, meta: `${row.term_name} / ${row.academic_year}` })} />}
        {data.attendance?.length > 0 && <ListPanel title="Recent attendance" rows={data.attendance.slice(0, 10)} render={(row) => ({ title: `${row.course_code} / ${row.course_name}`, meta: `${dateOnly(row.held_on)} / ${sentence(row.status)}` })} />}
        {data.assessments?.length > 0 && <ListPanel title="Assessment results" rows={data.assessments.slice(0, 10)} render={(row) => ({ title: `${row.course_code} / ${row.title}`, meta: row.marks_awarded == null ? "Not graded" : `${row.marks_awarded} of ${row.max_marks}${row.grade ? ` / ${row.grade}` : ""}` })} />}
      </div>
      {!data.courses?.length && !data.attendance?.length && !data.assessments?.length && <EmptyState variant="inline" icon={GraduationCap} title="Academic activity will appear here" description="Course allocation, attendance, and published assessment results are connected automatically." />}
    </div>;
  }
  if (workspace.industry === "gym") {
    const hasRows = data.checkins?.length || data.trainers?.length || data.workouts?.length || data.diets?.length;
    if (!hasRows) return <EmptyState variant="section" alignment="left" icon={Barbell} title="No gym activity yet" description="Attendance, assigned coaching, workouts, and diet plans will appear after they are recorded." />;
    return <div className="grid items-start gap-5 xl:grid-cols-2">
      {data.open_checkin && <Surface className="border-positive/30 bg-positive/5 p-5"><div className="flex items-center gap-3"><CheckCircle className="text-positive" size={24} /><div><div className="font-semibold">Currently inside</div><div className="text-sm text-muted-foreground">Checked in {dateTime(data.open_checkin.checked_in_at)}</div></div></div></Surface>}
      {data.checkins?.length > 0 && <ListPanel title="Recent visits" rows={data.checkins.slice(0, 8)} render={(row) => ({ title: dateTime(row.checked_in_at), meta: row.checked_out_at ? `Checked out ${dateTime(row.checked_out_at)}` : "Currently inside" })} />}
      {data.trainers?.length > 0 && <ListPanel title="Trainer assignments" rows={data.trainers} render={(row) => ({ title: `${row.employee?.first_name || ""} ${row.employee?.last_name || ""}`.trim() || "Trainer", meta: `${dateOnly(row.starts_on)} / ${sentence(row.status)}` })} />}
      {data.workouts?.length > 0 && <ListPanel title="Workout plans" rows={data.workouts} render={(row) => ({ title: row.name, meta: `${dateOnly(row.starts_on)} / ${sentence(row.status)}` })} />}
      {data.diets?.length > 0 && <ListPanel title="Diet plans" rows={data.diets} render={(row) => ({ title: row.name, meta: dateOnly(row.starts_on) })} />}
    </div>;
  }
  if (workspace.industry === "salon") {
    const profile = data.profile;
    return <div className="grid items-start gap-5 xl:grid-cols-2">
      {profile && <Surface className="p-5"><h2 className="font-display text-xl font-semibold">Service preferences</h2><div className="mt-5 grid gap-4 sm:grid-cols-2">{profile.preferred_services?.length > 0 && <Info label="Preferred services" value={profile.preferred_services.join(", ")} />}{profile.sensitivities && <Info label="Sensitivities" value={profile.sensitivities} />}{profile.formulas && <Info label="Formula memory" value={profile.formulas} />}{profile.preferences?.notes && <Info label="Service notes" value={profile.preferences.notes} />}</div></Surface>}
      {data.upcoming && <ListPanel title="Upcoming booking" rows={[data.upcoming]} render={(row) => ({ title: row.service?.name || "Appointment", meta: dateTime(row.starts_at) })} />}
      {data.visits?.length > 0 && <ListPanel title="Service history" rows={data.visits.slice(0, 10)} render={(row) => ({ title: row.service?.name || "Service", meta: `${dateTime(row.starts_at)} / ${sentence(row.status)}` })} />}
      {!profile && !data.upcoming && !data.visits?.length && <EmptyState variant="section" alignment="left" icon={CalendarBlank} title="No salon operations yet" description="Preferences and completed services will appear here." />}
    </div>;
  }
  if (!data.clinical_access) return <EmptyState variant="section" alignment="left" icon={WarningCircle} title="Clinical context is protected" description="This role can use the shared client identity but cannot read clinical records." />;
  return <div className="grid items-start gap-5 xl:grid-cols-2">
    <Surface className="p-5"><h2 className="font-display text-xl font-semibold">Patient context</h2><div className="mt-5 grid gap-4 sm:grid-cols-2">{data.patient?.blood_group && <Info label="Blood group" value={data.patient.blood_group} />}{data.patient?.abha_number && <Info label="ABHA" value={data.patient.abha_number} />}{data.allergies?.length > 0 && <Info label="Active allergies" value={data.allergies.map((item) => item.substance).join(", ")} />}</div></Surface>
    <Surface className="p-5"><h2 className="font-display text-xl font-semibold">Care records</h2><div className="mt-5 grid grid-cols-3 gap-3"><Count label="Encounters" value={data.encounters?.length || 0} /><Count label="Prescriptions" value={data.prescriptions?.length || 0} /><Count label="Lab orders" value={data.labs?.length || 0} /></div><Button className="mt-5 w-full" onClick={() => navigate(`/app/clinic?client=${workspace.client.id}`)}>Open clinical workspace</Button></Surface>
  </div>;
}


function Billing({ workspace, navigate, setPaying, setVoiding }) {
  const billing = workspace.billing;
  if (!billing?.capabilities?.view) return <EmptyState variant="section" alignment="left" icon={Receipt} title="Billing is outside your access" description="Only authorized financial roles can view invoices and payments." />;
  const summary = billing.summary;
  return <div className="space-y-5">
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><SummaryCard label="Invoiced all time" value={summary.invoiced_paise} /><SummaryCard label="Paid all time" value={summary.paid_paise} /><SummaryCard label="Outstanding now" value={summary.outstanding_paise} warning={summary.outstanding_paise > 0} /></div>
    <Surface className="overflow-hidden"><PanelHeader title="Outstanding invoices" subtitle="Every balance is tied to its source invoice and items." />{billing.open_invoices.length ? <div className="divide-y">{billing.open_invoices.map((invoice) => <InvoiceRow key={invoice.id} invoice={invoice} capabilities={billing.capabilities} open={() => navigate(`/app/sales/${invoice.id}`)} pay={() => setPaying(invoice)} voidInvoice={() => setVoiding(invoice)} />)}</div> : <EmptyState variant="inline" icon={CheckCircle} title="Nothing outstanding" description="All open invoices are fully settled or voided." className="m-4" />}</Surface>
    {billing.recent_invoices.length > 0 && <Surface className="overflow-hidden"><PanelHeader title="Recent invoice history" subtitle="Paid, open, and audited void records remain visible." /><div className="divide-y">{billing.recent_invoices.map((invoice) => <button type="button" key={invoice.id} onClick={() => navigate(`/app/sales/${invoice.id}`)} className="flex w-full items-center gap-4 p-4 text-left transition-colors hover:bg-surface-hover sm:p-5"><span className="state-icon shrink-0"><Receipt /></span><span className="min-w-0 flex-1"><span className="block font-mono text-sm font-semibold">{invoice.invoice_number}</span><span className="mt-1 block truncate text-xs text-muted-foreground">{invoice.item_names?.join(", ") || "No item description"} / {dateTime(invoice.created_at)}</span></span><StatusBadge status={invoice.status} /><span className="hidden font-semibold sm:block">{money(invoice.total_paise)}</span><CaretRight /></button>)}</div></Surface>}
  </div>;
}


function InvoiceRow({ invoice, capabilities, open, pay, voidInvoice }) {
  return <article className="p-4 sm:p-5">
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-semibold">{invoice.invoice_number}</span><StatusBadge status={invoice.status} /></div><div className="mt-2 text-sm">{invoice.item_names?.join(", ") || "No item description"}</div><div className="mt-1 text-xs text-muted-foreground">Issued {dateTime(invoice.issued_at || invoice.created_at)}</div></div>
      <div className="grid grid-cols-3 gap-4 text-sm lg:min-w-[23rem]"><Info label="Total" value={money(invoice.total_paise)} /><Info label="Paid" value={money(invoice.paid_paise)} /><Info label="Balance" value={money(invoice.balance_paise)} warning /></div>
      <div className="flex flex-wrap gap-2">{capabilities.record_payment && invoice.balance_paise > 0 && !["draft", "void", "refunded"].includes(invoice.status) && <Button size="sm" onClick={pay}><Wallet className="mr-2" />Record payment</Button>}<Button size="sm" variant="outline" onClick={open}>Open invoice</Button>{capabilities.void_invoice && invoice.voidable && <Button size="sm" variant="ghost" className="text-danger" onClick={voidInvoice}>Void</Button>}</div>
    </div>
  </article>;
}


function Activity({ rows, loading, fetching, error, hasMore, loadMore, retry }) {
  if (loading) return <div className="space-y-3">{[1, 2, 3, 4].map((item) => <div key={item} className="h-20 animate-pulse rounded-2xl bg-secondary" />)}</div>;
  if (error && !rows?.length) return <ErrorState title="Activity could not be loaded" retry={retry} />;
  if (!rows?.length) return <EmptyState variant="section" alignment="left" icon={Clock} title="No activity yet" description="Membership, invoice, payment, visit, and appointment activity will appear here." />;
  return <Surface className="overflow-hidden"><PanelHeader title="Operational activity" subtitle="Normalized events with status, context, and responsible staff." /><ol className="divide-y">{rows.map((item) => <li key={item.id} className="flex gap-4 p-4 sm:p-5"><span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary">{activityIcon(item.type)}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{item.title}</h3>{item.status && <StatusBadge status={item.status} />}</div>{item.detail && <p className="mt-1 text-sm text-muted-foreground">{item.detail}</p>}<div className="mt-2 flex flex-wrap gap-x-3 text-xs text-muted-foreground"><span>{dateTime(item.occurred_at)}</span>{item.actor?.name && <span>By {item.actor.name}</span>}{item.amount_paise != null && <span>{money(item.amount_paise)}</span>}</div></div></li>)}</ol><CursorListFooter count={rows.length} noun="events" hasMore={hasMore} loading={fetching} error={error} onLoadMore={loadMore} onRetry={retry} /></Surface>;
}


function Progress({ data, canAdd, add }) {
  const hasData = data.measurements?.length || data.goals?.length || data.workout_sessions?.length;
  if (!hasData) return <EmptyState variant="section" alignment="left" icon={TrendUp} title="No progress records yet" description="Add a measurement when there is meaningful progress data to track." action={canAdd && <Button onClick={add}><Plus className="mr-2" />Add measurement</Button>} />;
  return <div className="grid items-start gap-5 xl:grid-cols-2">
    {data.measurements?.length > 0 && <Surface className="overflow-hidden"><PanelHeader title="Measurements" subtitle="Latest first; no chart is shown without useful history." action={canAdd && <Button size="sm" variant="outline" onClick={add}><Plus />Add</Button>} /><div className="divide-y">{data.measurements.slice(0, 10).map((row) => <div key={row.id} className="p-4 sm:p-5"><div className="text-sm font-semibold">{dateOnly(row.measured_on)}</div><div className="mt-2 flex flex-wrap gap-2">{Object.entries(row.metrics || {}).map(([key, value]) => <span key={key} className="rounded-lg bg-secondary px-2.5 py-1 text-xs">{sentence(key)}: {value}</span>)}</div>{row.notes && <p className="mt-2 text-sm text-muted-foreground">{row.notes}</p>}</div>)}</div></Surface>}
    {data.goals?.length > 0 && <Surface className="overflow-hidden"><PanelHeader title="Goals" /><div className="divide-y">{data.goals.map((goal) => <div key={goal.id} className="p-4 sm:p-5"><div className="flex items-center justify-between gap-3"><div className="font-semibold">{goal.label}</div><StatusBadge status={goal.status} /></div><div className="mt-2 text-sm text-muted-foreground">Current {goal.current_value ?? goal.baseline_value ?? "-"} {goal.unit} / target {goal.target_value} {goal.unit}</div></div>)}</div></Surface>}
    {data.workout_sessions?.length > 0 && <ListPanel title="Recent workout sessions" rows={data.workout_sessions.slice(0, 8)} render={(row) => ({ title: dateTime(row.scheduled_for), meta: `${sentence(row.status)}${row.effort_rating ? ` / effort ${row.effort_rating}/10` : ""}` })} />}
  </div>;
}


function DetailsDrawer({ open, onOpenChange, workspace, media, mediaLoading, uploadPending, openAction, upload, openFile, removeFile, entityLabel }) {
  const client = workspace.client;
  const isCollege = workspace.industry === "college";
  const hasContact = client.phone || client.email || client.address;
  return <DrawerForm open={open} onOpenChange={onOpenChange} title={`${entityLabel} details`} description={isCollege ? "Identity, contact details, notes, consent, and private files stay secondary to academic and placement work." : "Identity, relationship context, consent, and private files stay secondary to daily operations."}>
    <div className="space-y-6">
      {hasContact && <section><SectionTitle title="Contact" action={workspace.actions.edit_client && <Button size="sm" variant="outline" onClick={() => openAction("edit", client)}>Edit</Button>} /><Surface className="mt-3 divide-y p-4">{client.phone && <DetailRow icon={Phone} label="Phone" value={client.phone} />}{client.email && <DetailRow icon={Envelope} label="Email" value={client.email} />}{client.address && <DetailRow icon={MapPin} label="Address" value={client.address} />}</Surface></section>}
      <section><SectionTitle title="Communication consent" /><Surface className="mt-3 p-4"><div className="flex items-center justify-between gap-4"><div><div className="text-sm font-semibold">WhatsApp reminders</div><div className="mt-1 text-xs text-muted-foreground">{client.whatsapp_consent ? "Consent recorded" : "Not enabled"}</div></div><StatusBadge status={client.whatsapp_consent ? "active" : "inactive"} label={client.whatsapp_consent ? "On" : "Off"} /></div><div className="mt-4 flex items-center justify-between gap-4 border-t pt-4"><div><div className="text-sm font-semibold">Email communication</div><div className="mt-1 text-xs text-muted-foreground">{client.email_consent ? "Consent recorded" : "Not enabled"}</div></div><StatusBadge status={client.email_consent ? "active" : "inactive"} label={client.email_consent ? "On" : "Off"} /></div></Surface></section>
      {client.notes && <section><SectionTitle title="Profile note" /><Surface className="mt-3 p-4"><p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{client.notes}</p></Surface></section>}
      {(workspace.memory.length > 0 || workspace.actions.manage_memory) && <section><SectionTitle title={isCollege ? "Student notes" : "Relationship memory"} action={workspace.actions.manage_memory && <Button size="sm" variant="outline" onClick={() => openAction("memory")}><Plus />Add</Button>} />{workspace.memory.length ? <div className="mt-3 space-y-2">{workspace.memory.map((item) => <Surface key={item.id} className="p-4"><div className="overline">{sentence(item.category)}</div><div className="mt-2 font-semibold">{item.label}</div><p className="mt-1 text-sm text-muted-foreground">{item.value}</p></Surface>)}</div> : <p className="mt-3 text-sm text-muted-foreground">No {isCollege ? "student" : "relationship"} notes recorded.</p>}</section>}
      {(workspace.commitments.length > 0 || workspace.actions.manage_memory) && <section><SectionTitle title="Follow-ups" action={workspace.actions.manage_memory && <Button size="sm" variant="outline" onClick={() => openAction("commitment")}><Plus />Add</Button>} />{workspace.commitments.length ? <div className="mt-3 space-y-2">{workspace.commitments.map((item) => <Surface key={item.id} className="p-4"><div className="flex items-center justify-between gap-3"><div className="font-semibold">{item.title}</div><StatusBadge status={item.status} /></div>{item.due_at && <div className="mt-2 text-xs text-muted-foreground">Due {dateTime(item.due_at)}</div>}</Surface>)}</div> : <p className="mt-3 text-sm text-muted-foreground">No follow-ups recorded.</p>}</section>}
      {workspace.actions.view_media && <section><SectionTitle title="Private files" action={workspace.actions.manage_media && <label aria-busy={uploadPending} className={`inline-flex items-center rounded-xl border px-3 py-2 text-sm ${uploadPending ? "cursor-wait opacity-60" : "cursor-pointer"}`}><FileArrowUp className="mr-2" />{uploadPending ? "Uploading..." : "Upload"}<input hidden disabled={uploadPending} type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,.pdf,.docx,.txt" onChange={upload} /></label>} />{mediaLoading ? <div className="mt-3 h-24 animate-pulse rounded-xl bg-secondary" /> : media?.length ? <div className="mt-3 space-y-2">{media.map((item) => <Surface key={item.id} className="flex items-center gap-3 p-4"><span className="state-icon shrink-0"><FileArrowUp /></span><div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{item.caption || item.document.name}</div><div className="mt-1 text-xs text-muted-foreground">{sentence(item.media_kind)} / {Math.ceil(item.document.size_bytes / 1024)} KB</div></div><Button size="sm" variant="outline" onClick={() => openFile(item)}>Open</Button>{workspace.actions.manage_media && <Button size="sm" variant="ghost" className="text-danger" onClick={() => removeFile(item)}>Remove</Button>}</Surface>)}</div> : <p className="mt-3 text-sm text-muted-foreground">No private files uploaded.</p>}</section>}
    </div>
  </DrawerForm>;
}


function LegacyActionDrawer({ action, client, entityLabel, busy, close, submit }) {
  const [values, setValues] = useState({});
  useEffect(() => {
    if (!action.type) return;
    if (action.type === "edit") setValues({ ...client, ...action.values });
    if (action.type === "memory") setValues({ category: "preference", label: "", value: "", visibility: "team" });
    if (action.type === "commitment") setValues({ title: "", description: "", due_at: "" });
    if (action.type === "measurement") setValues({ measured_on: today(), weight_kg: "", height_cm: "", body_fat_percent: "", waist_cm: "", notes: "" });
    if (action.type === "freeze") setValues({ frozen_from: today(), frozen_until: today() });
  }, [action, client]);
  const title = { edit: `Edit ${entityLabel.toLowerCase()}`, memory: `Add ${entityLabel === "Student" ? "student" : "relationship"} note`, commitment: "Add follow-up", measurement: "Add measurement", freeze: "Freeze membership" }[action.type] || "Update";
  const save = (event) => { event.preventDefault(); submit(action.type, values); };
  return <DrawerForm open={Boolean(action.type)} onOpenChange={(open) => !open && close()} title={title} description={action.type === "freeze" ? "Check-in access pauses and the term is extended when the membership resumes." : "Save only information that is useful to the team."}>
    <form onSubmit={save} className="space-y-5">
      {action.type === "edit" && <><div className="grid gap-4 sm:grid-cols-2"><Field label="First name"><Input required value={values.first_name || ""} onChange={field(setValues, "first_name")} /></Field><Field label="Last name"><Input value={values.last_name || ""} onChange={field(setValues, "last_name")} /></Field><Field label="Phone"><Input value={values.phone || ""} onChange={field(setValues, "phone")} /></Field><Field label="Email"><Input type="email" value={values.email || ""} onChange={field(setValues, "email")} /></Field></div><Field label="Address"><Textarea value={values.address || ""} onChange={field(setValues, "address")} /></Field><Field label="Internal profile note"><Textarea value={values.notes || ""} onChange={field(setValues, "notes")} /></Field><Field label="Status"><Select value={values.status || "active"} onValueChange={(status) => setValues({ ...values, status })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["active", "inactive", "blocked"].map((status) => <SelectItem key={status} value={status}>{sentence(status)}</SelectItem>)}</SelectContent></Select></Field><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(values.whatsapp_consent)} onChange={(event) => setValues({ ...values, whatsapp_consent: event.target.checked })} />WhatsApp consent recorded</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(values.email_consent)} onChange={(event) => setValues({ ...values, email_consent: event.target.checked })} />Email consent recorded</label></>}
      {action.type === "memory" && <><Field label="Type"><Select value={values.category} onValueChange={(category) => setValues({ ...values, category })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["preference", "goal", "language", "concern", "service_preference", "communication"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></Field><Field label="Short label"><Input required value={values.label || ""} onChange={field(setValues, "label")} /></Field><Field label="What should the team remember?"><Textarea required rows={5} value={values.value || ""} onChange={field(setValues, "value")} /></Field><Field label="Visibility"><Select value={values.visibility} onValueChange={(visibility) => setValues({ ...values, visibility })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["team", "managers", "assigned_staff", "author_only", "clinical"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></Field></>}
      {action.type === "commitment" && <><Field label="Follow-up"><Input required value={values.title || ""} onChange={field(setValues, "title")} /></Field><Field label="Details"><Textarea value={values.description || ""} onChange={field(setValues, "description")} /></Field><Field label="Due date and time"><Input type="datetime-local" value={values.due_at || ""} onChange={field(setValues, "due_at")} /></Field></>}
      {action.type === "measurement" && <><Field label="Measured on"><Input required type="date" value={values.measured_on || today()} onChange={field(setValues, "measured_on")} /></Field><div className="grid grid-cols-2 gap-4">{[["weight_kg", "Weight kg"], ["height_cm", "Height cm"], ["body_fat_percent", "Body fat %"], ["waist_cm", "Waist cm"]].map(([key, label]) => <Field key={key} label={label}><Input type="number" step="0.1" value={values[key] || ""} onChange={field(setValues, key)} /></Field>)}</div><Field label="Notes"><Textarea value={values.notes || ""} onChange={field(setValues, "notes")} /></Field></>}
      {action.type === "freeze" && <><Field label="Freeze from"><Input required type="date" min={today()} value={values.frozen_from || ""} onChange={field(setValues, "frozen_from")} /></Field><Field label="Freeze until"><Input required type="date" min={values.frozen_from || today()} value={values.frozen_until || ""} onChange={field(setValues, "frozen_until")} /></Field></>}
      <Button disabled={busy} className="w-full">{busy ? "Saving..." : "Save update"}</Button>
    </form>
  </DrawerForm>;
}

function ActionDrawer({ action, client, entityLabel, busy, close, submit }) {
  const schemas = {
    edit: clientProfileEditSchema,
    memory: clientMemorySchema,
    commitment: clientCommitmentSchema,
    measurement: clientMeasurementSchema,
    freeze: profileFreezeSchema,
  };
  const defaults = {
    edit: {
      first_name: client?.first_name || "", last_name: client?.last_name || "", phone: client?.phone || "",
      email: client?.email || "", address: client?.address || "", notes: client?.notes || "",
      status: client?.status || "active", whatsapp_consent: Boolean(client?.whatsapp_consent),
      email_consent: Boolean(client?.email_consent), version: client?.version || 1, ...action.values,
    },
    memory: { category: "preference", label: "", value: "", visibility: "team", ...action.values },
    commitment: { title: "", description: "", due_at: "", ...action.values },
    measurement: { measured_on: today(), weight_kg: "", height_cm: "", body_fat_percent: "", waist_cm: "", notes: "", ...action.values },
    freeze: { frozen_from: today(), frozen_until: today(), ...action.values },
  };
  const formApi = useForm({ resolver: zodResolver(schemas[action.type] || clientMemorySchema), defaultValues: defaults[action.type] || defaults.memory, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, setError, setValue, watch } = formApi;
  const values = watch();
  const title = { edit: `Edit ${entityLabel.toLowerCase()}`, memory: `Add ${entityLabel === "Student" ? "student" : "relationship"} note`, commitment: "Add follow-up", measurement: "Add measurement", freeze: "Freeze membership" }[action.type] || "Update";
  const save = handleSubmit(async (validated) => {
    clearErrors("root.server");
    try {
      await submit(action.type, validated);
    } catch (error) {
      applyApiErrors(error, setError, { fallback: "This update could not be saved" });
    }
  });
  const closeDrawer = (open) => { if (!open && (busy || formState.isSubmitting)) return; if (!open) close(); };
  return <DrawerForm open={Boolean(action.type)} onOpenChange={closeDrawer} title={title} description={action.type === "freeze" ? "Check-in access pauses and the term is extended when the membership resumes." : "Save only information that is useful to the team."}>
    <form noValidate onSubmit={save} className="space-y-5">
      {action.type === "edit" && <><div className="grid gap-4 sm:grid-cols-2"><Field label="First name" error={formState.errors.first_name}><Input {...register("first_name")} aria-invalid={Boolean(formState.errors.first_name)} /></Field><Field label="Last name" error={formState.errors.last_name}><Input {...register("last_name")} aria-invalid={Boolean(formState.errors.last_name)} /></Field><Field label="Phone" error={formState.errors.phone}><Input inputMode="tel" {...register("phone")} aria-invalid={Boolean(formState.errors.phone)} /></Field><Field label="Email" error={formState.errors.email}><Input type="email" {...register("email")} aria-invalid={Boolean(formState.errors.email)} /></Field></div><Field label="Address" error={formState.errors.address}><Textarea {...register("address")} aria-invalid={Boolean(formState.errors.address)} /></Field><Field label="Internal profile note" error={formState.errors.notes}><Textarea {...register("notes")} aria-invalid={Boolean(formState.errors.notes)} /></Field><Field label="Status" error={formState.errors.status}><Select value={values.status || "active"} onValueChange={(status) => setValue("status", status, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(formState.errors.status)}><SelectValue /></SelectTrigger><SelectContent>{["active", "inactive", "blocked"].map((status) => <SelectItem key={status} value={status}>{sentence(status)}</SelectItem>)}</SelectContent></Select></Field><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(values.whatsapp_consent)} onChange={(event) => setValue("whatsapp_consent", event.target.checked, { shouldDirty: true, shouldValidate: true })} />WhatsApp consent recorded</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(values.email_consent)} onChange={(event) => setValue("email_consent", event.target.checked, { shouldDirty: true })} />Email consent recorded</label></>}
      {action.type === "memory" && <><Field label="Type" error={formState.errors.category}><Select value={values.category} onValueChange={(category) => setValue("category", category, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(formState.errors.category)}><SelectValue /></SelectTrigger><SelectContent>{["preference", "goal", "language", "concern", "service_preference", "communication"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></Field><Field label="Short label" error={formState.errors.label}><Input {...register("label")} aria-invalid={Boolean(formState.errors.label)} /></Field><Field label="What should the team remember?" error={formState.errors.value}><Textarea rows={5} {...register("value")} aria-invalid={Boolean(formState.errors.value)} /></Field><Field label="Visibility" error={formState.errors.visibility}><Select value={values.visibility} onValueChange={(visibility) => setValue("visibility", visibility, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(formState.errors.visibility)}><SelectValue /></SelectTrigger><SelectContent>{["team", "managers", "assigned_staff", "author_only", "clinical"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select></Field></>}
      {action.type === "commitment" && <><Field label="Follow-up" error={formState.errors.title}><Input {...register("title")} aria-invalid={Boolean(formState.errors.title)} /></Field><Field label="Details" error={formState.errors.description}><Textarea {...register("description")} aria-invalid={Boolean(formState.errors.description)} /></Field><Field label="Due date and time" error={formState.errors.due_at}><Input type="datetime-local" {...register("due_at")} aria-invalid={Boolean(formState.errors.due_at)} /></Field></>}
      {action.type === "measurement" && <><Field label="Measured on" error={formState.errors.measured_on}><Input type="date" {...register("measured_on")} aria-invalid={Boolean(formState.errors.measured_on)} /></Field><div className="grid grid-cols-2 gap-4">{[["weight_kg", "Weight kg"], ["height_cm", "Height cm"], ["body_fat_percent", "Body fat %"], ["waist_cm", "Waist cm"]].map(([key, label]) => <Field key={key} label={label} error={formState.errors[key]}><Input inputMode="decimal" {...register(key)} aria-invalid={Boolean(formState.errors[key])} /></Field>)}</div><Field label="Notes" error={formState.errors.notes}><Textarea {...register("notes")} aria-invalid={Boolean(formState.errors.notes)} /></Field></>}
      {action.type === "freeze" && <><Field label="Freeze from" error={formState.errors.frozen_from}><Input type="date" min={today()} {...register("frozen_from")} aria-invalid={Boolean(formState.errors.frozen_from)} /></Field><Field label="Freeze until" error={formState.errors.frozen_until}><Input type="date" min={values.frozen_from || today()} {...register("frozen_until")} aria-invalid={Boolean(formState.errors.frozen_until)} /></Field></>}
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" disabled={!formState.isValid} loading={busy || formState.isSubmitting} loadingText="Saving update..." className="w-full">Save update</Button>
    </form>
  </DrawerForm>;
}


function LegacyMembershipCheckout({ checkout, onOpenChange, client, plans, locationId }) {
  const [form, setForm] = useState({ plan_id: "", starts_on: today(), payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false });
  const [createMembership, createState] = useCreateMembershipMutation();
  const [renewMembership, renewState] = useRenewMembershipMutation();
  const open = Boolean(checkout);
  const renewal = checkout?.mode === "renewal";
  useEffect(() => {
    if (!open) return;
    setForm({ plan_id: checkout.membership?.plan_id || plans[0]?.id || "", starts_on: today(), payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false });
  }, [open, checkout, plans]);
  const quoteQuery = useGetMembershipQuoteQuery({ planId: form.plan_id, clientId: client.id, kind: renewal ? "renewal" : "activation", interstate: form.interstate }, { skip: !open || !form.plan_id });
  const quote = quoteQuery.data;
  const paymentNeeded = ["full", "partial"].includes(form.payment_option);
  const validPartial = form.payment_option !== "partial" || (Number(form.partial_amount) > 0 && Math.round(Number(form.partial_amount) * 100) < (quote?.total_paise || 0));
  const submit = async (event) => {
    event.preventDefault();
    if (!form.payment_option || !validPartial || (paymentNeeded && !form.payment_method)) return;
    const payload = {
      plan_id: form.plan_id,
      payment_option: form.payment_option,
      partial_payment_paise: form.payment_option === "partial" ? Math.round(Number(form.partial_amount) * 100) : null,
      payment_method: paymentNeeded ? form.payment_method : null,
      payment_reference: form.payment_reference || null,
      interstate: form.interstate,
      idempotency_key: crypto.randomUUID(),
    };
    try {
      if (renewal) await renewMembership({ membershipId: checkout.membership.id, ...payload }).unwrap();
      else await createMembership({ ...payload, client_id: client.id, location_id: locationId, starts_on: form.starts_on }).unwrap();
      toast.success(renewal ? "Renewal scheduled with linked invoice" : "Membership activated with linked invoice");
      onOpenChange(false);
    } catch (error) {
      toast.error(errorMessage(error, "Membership checkout could not be completed"));
    }
  };
  const saving = createState.isLoading || renewState.isLoading;
  return <DrawerForm open={open} onOpenChange={onOpenChange} title={renewal ? "Renew membership" : "Activate membership"} description={renewal ? "The current term remains active. This creates the next term and its invoice." : "Review the authoritative charge and explicitly choose how payment is handled."}>
    <form onSubmit={submit} className="space-y-6">
      <Field label="Plan"><Select required value={form.plan_id} onValueChange={(plan_id) => setForm({ ...form, plan_id })}><SelectTrigger><SelectValue placeholder="Choose plan" /></SelectTrigger><SelectContent>{plans.map((plan) => <SelectItem key={plan.id} value={plan.id}>{plan.name} / {money(plan.price_paise)}</SelectItem>)}</SelectContent></Select></Field>
      {!renewal && <Field label="Starts on"><Input required type="date" min={today()} value={form.starts_on} onChange={field(setForm, "starts_on")} /></Field>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.interstate} onChange={(event) => setForm({ ...form, interstate: event.target.checked })} />Use IGST for this invoice</label>
      <Surface className="overflow-hidden"><div className="border-b p-4"><div className="font-semibold">Charge summary</div><div className="mt-1 text-xs text-muted-foreground">Tax settings are snapshotted onto the invoice.</div></div>{quoteQuery.isFetching ? <div className="h-36 animate-pulse bg-secondary" /> : quote ? <div className="p-4"><MoneyRow label="Base membership fee" value={quote.base_fee_paise} /><MoneyRow label="Joining fee" value={quote.joining_fee_paise} hidden={!quote.joining_fee_paise} /><MoneyRow label="Tax" value={quote.tax_paise} detail={`${quote.tax_rate_bps / 100}% ${quote.prices_include_tax ? "included" : "added"}`} /><MoneyRow label="Total" value={quote.total_paise} strong /></div> : <div className="p-4 text-sm text-muted-foreground">Choose a plan to calculate the charge.</div>}</Surface>
      <section><div className="text-sm font-semibold">How will this invoice be paid?</div><div className="mt-3 grid gap-2 sm:grid-cols-3">{[["full", "Full payment", "Settle now"], ["partial", "Partial", "Record some now"], ["later", "Pay later", "Leave outstanding"]].map(([value, label, copy]) => <label key={value} className={`cursor-pointer rounded-xl border p-3 transition-colors ${form.payment_option === value ? "border-primary bg-primary/5" : "hover:bg-secondary"}`}><input className="sr-only" type="radio" name="payment" value={value} checked={form.payment_option === value} onChange={() => setForm({ ...form, payment_option: value })} /><span className="block text-sm font-semibold">{label}</span><span className="mt-1 block text-xs text-muted-foreground">{copy}</span></label>)}</div></section>
      {form.payment_option === "partial" && <Field label="Amount received now (INR)"><Input required type="number" min="0.01" max={(quote?.total_paise || 0) / 100 - 0.01} step="0.01" value={form.partial_amount} onChange={field(setForm, "partial_amount")} />{!validPartial && <p className="text-xs text-danger">Partial payment must be below the invoice total.</p>}</Field>}
      {paymentNeeded && <><Field label="Payment method"><Select value={form.payment_method} onValueChange={(payment_method) => setForm({ ...form, payment_method })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["cash", "upi", "card", "bank"].map((method) => <SelectItem key={method} value={method}>{sentence(method)}</SelectItem>)}</SelectContent></Select></Field><Field label="Reference"><Input maxLength={120} value={form.payment_reference} onChange={field(setForm, "payment_reference")} placeholder="Optional transaction reference" /></Field></>}
      <Button className="w-full" disabled={saving || !quote || !form.payment_option || !validPartial}>{saving ? "Completing checkout..." : renewal ? "Create scheduled renewal" : "Activate membership"}</Button>
    </form>
  </DrawerForm>;
}

function MembershipCheckout({ checkout, onOpenChange, client, plans, locationId }) {
  const [createMembership, createState] = useCreateMembershipMutation();
  const [renewMembership, renewState] = useRenewMembershipMutation();
  const idempotency = useStableIdempotencyKey();
  const open = Boolean(checkout);
  const renewal = checkout?.mode === "renewal";
  const formApi = useForm({
    resolver: zodResolver(membershipSchema),
    defaultValues: { client_id: client.id, plan_id: "", starts_on: today(), payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false },
    ...FORM_OPTIONS,
  });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  const form = watch();
  useEffect(() => {
    if (!open) return;
    reset({ client_id: client.id, plan_id: checkout.membership?.plan_id || plans[0]?.id || "", starts_on: today(), payment_option: "", partial_amount: "", payment_method: "upi", payment_reference: "", interstate: false });
    idempotency.reset();
  }, [open, checkout?.membership?.id, plans[0]?.id, client.id]);
  const quoteQuery = useGetMembershipQuoteQuery({ planId: form.plan_id, clientId: client.id, kind: renewal ? "renewal" : "activation", interstate: form.interstate }, { skip: !open || !form.plan_id });
  const quote = quoteQuery.data;
  const paymentNeeded = ["full", "partial"].includes(form.payment_option);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    if (!quote) {
      setError("root.server", { type: "quote", message: "Wait for the authoritative charge to load" });
      return;
    }
    if (values.payment_option === "partial" && Math.round(values.partial_amount * 100) >= Number(quote.total_paise || 0)) {
      setError("partial_amount", { type: "maximum", message: "Partial payment must be below the invoice total" }, { shouldFocus: true });
      return;
    }
    const payload = {
      plan_id: values.plan_id,
      payment_option: values.payment_option,
      partial_payment_paise: values.payment_option === "partial" ? Math.round(values.partial_amount * 100) : null,
      payment_method: values.payment_option === "later" ? null : values.payment_method,
      payment_reference: values.payment_option === "later" ? null : values.payment_reference,
      interstate: values.interstate,
      idempotency_key: idempotency.current(),
    };
    try {
      if (renewal) await renewMembership({ membershipId: checkout.membership.id, ...payload }).unwrap();
      else await createMembership({ ...payload, client_id: client.id, location_id: locationId, starts_on: values.starts_on }).unwrap();
      toast.success(renewal ? "Renewal scheduled with linked invoice" : "Membership activated with linked invoice");
      idempotency.reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Membership checkout could not be completed" });
      toast.error(normalized.message);
    }
  });
  const saving = createState.isLoading || renewState.isLoading || formState.isSubmitting;
  const close = (next) => { if (!next && saving) return; onOpenChange(next); };
  return <DrawerForm open={open} onOpenChange={close} title={renewal ? "Renew membership" : "Activate membership"} description={renewal ? "The current term remains active. This creates the next term and its invoice." : "Review the authoritative charge and explicitly choose how payment is handled."}>
    <form noValidate onSubmit={submit} className="space-y-6">
      <Field label="Plan" error={formState.errors.plan_id}><Select value={form.plan_id} onValueChange={(plan_id) => setValue("plan_id", plan_id, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(formState.errors.plan_id)}><SelectValue placeholder="Choose plan" /></SelectTrigger><SelectContent>{plans.map((plan) => <SelectItem key={plan.id} value={plan.id}>{plan.name} / {money(plan.price_paise)}</SelectItem>)}</SelectContent></Select></Field>
      {!renewal && <Field label="Starts on" error={formState.errors.starts_on}><Input type="date" min={today()} {...register("starts_on")} aria-invalid={Boolean(formState.errors.starts_on)} /></Field>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form.interstate)} onChange={(event) => setValue("interstate", event.target.checked, { shouldDirty: true, shouldValidate: true })} />Use IGST for this invoice</label>
      <Surface className="overflow-hidden"><div className="border-b p-4"><div className="font-semibold">Charge summary</div><div className="mt-1 text-xs text-muted-foreground">Tax settings are snapshotted onto the invoice.</div></div>{quoteQuery.isFetching ? <div className="h-36 animate-pulse bg-secondary" /> : quote ? <div className="p-4"><MoneyRow label="Base membership fee" value={quote.base_fee_paise} /><MoneyRow label="Joining fee" value={quote.joining_fee_paise} hidden={!quote.joining_fee_paise} /><MoneyRow label="Tax" value={quote.tax_paise} detail={`${quote.tax_rate_bps / 100}% ${quote.prices_include_tax ? "included" : "added"}`} /><MoneyRow label="Total" value={quote.total_paise} strong /></div> : <div className="p-4 text-sm text-muted-foreground">Choose a plan to calculate the charge.</div>}</Surface>
      <section><div className="text-sm font-semibold">How will this invoice be paid?</div><div className="mt-3 grid gap-2 sm:grid-cols-3">{[["full", "Full payment", "Settle now"], ["partial", "Partial", "Record some now"], ["later", "Pay later", "Leave outstanding"]].map(([value, label, copy]) => <label key={value} className={`cursor-pointer rounded-xl border p-3 transition-colors ${form.payment_option === value ? "border-primary bg-primary/5" : "hover:bg-secondary"}`}><input className="sr-only" type="radio" name="payment" value={value} checked={form.payment_option === value} onChange={() => setValue("payment_option", value, { shouldDirty: true, shouldValidate: true })} /><span className="block text-sm font-semibold">{label}</span><span className="mt-1 block text-xs text-muted-foreground">{copy}</span></label>)}</div><FieldError error={formState.errors.payment_option} className="mt-2" /></section>
      {form.payment_option === "partial" && <Field label="Amount received now (INR)" error={formState.errors.partial_amount}><Input inputMode="decimal" {...register("partial_amount")} aria-invalid={Boolean(formState.errors.partial_amount)} /></Field>}
      {paymentNeeded && <><Field label="Payment method" error={formState.errors.payment_method}><Select value={form.payment_method || ""} onValueChange={(payment_method) => setValue("payment_method", payment_method, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(formState.errors.payment_method)}><SelectValue /></SelectTrigger><SelectContent>{["cash", "upi", "card", "bank"].map((method) => <SelectItem key={method} value={method}>{sentence(method)}</SelectItem>)}</SelectContent></Select></Field><Field label="Reference" error={formState.errors.payment_reference}><Input {...register("payment_reference")} placeholder="Optional transaction reference" aria-invalid={Boolean(formState.errors.payment_reference)} /></Field></>}
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" loading={saving} loadingText="Completing checkout..." disabled={!formState.isValid || !quote} className="w-full">{renewal ? "Create scheduled renewal" : "Activate membership"}</Button>
    </form>
  </DrawerForm>;
}


function LegacyCancellationDrawer({ membership, scheduled, onOpenChange }) {
  const [form, setForm] = useState({ timing: "now", reason: "", cancel_scheduled_renewal: true });
  const [cancelMembership, state] = useCancelMembershipMutation();
  const isScheduled = membership?.status === "scheduled";
  useEffect(() => { if (membership) setForm({ timing: isScheduled ? "now" : "term_end", reason: "", cancel_scheduled_renewal: true }); }, [membership, isScheduled]);
  const submit = async (event) => {
    event.preventDefault();
    if (form.reason.trim().length < 3) return;
    try {
      await cancelMembership({ membershipId: membership.id, reason: form.reason.trim(), version: membership.version, timing: form.timing, cancel_scheduled_renewal: form.cancel_scheduled_renewal }).unwrap();
      toast.success(form.timing === "term_end" && !isScheduled ? "Cancellation scheduled" : "Membership cancelled");
      onOpenChange(false);
    } catch (error) {
      toast.error(errorMessage(error, "Membership could not be cancelled"));
    }
  };
  return <DrawerForm open={Boolean(membership)} onOpenChange={onOpenChange} title={isScheduled ? "Cancel scheduled renewal" : "Cancel membership"} description="Review the operational and financial impact before confirming.">
    <form onSubmit={submit} className="space-y-5">
      {!isScheduled && <Field label="When should access end?"><Select value={form.timing} onValueChange={(timing) => setForm({ ...form, timing })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="term_end">At term end ({dateOnly(membership?.ends_on)})</SelectItem><SelectItem value="now">Immediately</SelectItem></SelectContent></Select></Field>}
      <Surface className="border-warning/30 bg-warning/5 p-4"><div className="flex gap-3"><WarningCircle className="mt-0.5 shrink-0 text-warning" /><div className="text-sm leading-6">{isScheduled ? "The scheduled term will be cancelled. Its fully unpaid invoice will be voided with an audit entry; a paid or partially paid renewal is blocked until refunds are supported." : form.timing === "now" ? "Check-in access ends immediately. The current term's invoice and payment history remain unchanged." : `Access remains active through ${dateOnly(membership?.ends_on)}. You can reverse this cancellation before it becomes effective.`}</div></div></Surface>
      {scheduled && <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={form.cancel_scheduled_renewal} onChange={(event) => setForm({ ...form, cancel_scheduled_renewal: event.target.checked })} /><span>Also cancel the scheduled renewal and void its unpaid invoice <strong>{scheduled.invoice?.invoice_number}</strong>.</span></label>}
      <Field label="Mandatory reason"><Textarea required minLength={3} maxLength={500} rows={5} value={form.reason} onChange={field(setForm, "reason")} /></Field>
      <Button disabled={state.isLoading || form.reason.trim().length < 3} className="w-full bg-danger text-white hover:bg-danger/90">{state.isLoading ? "Cancelling..." : "Confirm cancellation"}</Button>
    </form>
  </DrawerForm>;
}

function CancellationDrawer({ membership, scheduled, onOpenChange }) {
  const [cancelMembership, state] = useCancelMembershipMutation();
  const isScheduled = membership?.status === "scheduled";
  const formApi = useForm({ resolver: zodResolver(cancellationSchema), defaultValues: { timing: "term_end", reason: "", cancel_scheduled_renewal: true, version: 1 }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  const form = watch();
  useEffect(() => {
    if (membership) reset({ timing: isScheduled ? "now" : "term_end", reason: "", cancel_scheduled_renewal: true, version: membership.version });
  }, [membership?.id, membership?.version, isScheduled]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await cancelMembership({ membershipId: membership.id, ...values, timing: isScheduled ? "now" : values.timing }).unwrap();
      toast.success(values.timing === "term_end" && !isScheduled ? "Cancellation scheduled" : "Membership cancelled");
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Membership could not be cancelled" });
      toast.error(normalized.message);
    }
  });
  const busy = state.isLoading || formState.isSubmitting;
  const close = (next) => { if (!next && busy) return; onOpenChange(next); };
  return <DrawerForm open={Boolean(membership)} onOpenChange={close} title={isScheduled ? "Cancel scheduled renewal" : "Cancel membership"} description="Review the operational and financial impact before confirming.">
    <form noValidate onSubmit={submit} className="space-y-5">
      {!isScheduled && <Field label="When should access end?" error={formState.errors.timing}><Select value={form.timing} onValueChange={(timing) => setValue("timing", timing, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(formState.errors.timing)}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="term_end">At term end ({dateOnly(membership?.ends_on)})</SelectItem><SelectItem value="now">Immediately</SelectItem></SelectContent></Select></Field>}
      <Surface className="border-warning/30 bg-warning/5 p-4"><div className="flex gap-3"><WarningCircle className="mt-0.5 shrink-0 text-warning" /><div className="text-sm leading-6">{isScheduled ? "The scheduled term will be cancelled. Its fully unpaid invoice will be voided with an audit entry; a paid or partially paid renewal is blocked until refunds are supported." : form.timing === "now" ? "Check-in access ends immediately. The current term's invoice and payment history remain unchanged." : `Access remains active through ${dateOnly(membership?.ends_on)}. You can reverse this cancellation before it becomes effective.`}</div></div></Surface>
      {scheduled && <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={Boolean(form.cancel_scheduled_renewal)} onChange={(event) => setValue("cancel_scheduled_renewal", event.target.checked, { shouldDirty: true })} /><span>Also cancel the scheduled renewal and void its unpaid invoice <strong>{scheduled.invoice?.invoice_number}</strong>.</span></label>}
      <Field label="Mandatory reason" error={formState.errors.reason}><Textarea rows={5} {...register("reason")} aria-invalid={Boolean(formState.errors.reason)} /></Field>
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" disabled={!formState.isValid} loading={busy} loadingText="Cancelling membership..." className="w-full bg-danger text-white hover:bg-danger/90">Confirm cancellation</Button>
    </form>
  </DrawerForm>;
}


function PanelHeader({ title, subtitle, action }) { return <div className="flex items-start justify-between gap-4 border-b p-4 sm:p-5"><div><h2 className="font-display text-lg font-semibold sm:text-xl">{title}</h2>{subtitle && <p className="mt-1 text-xs leading-5 text-muted-foreground">{subtitle}</p>}</div>{action}</div>; }
function ListPanel({ title, rows, render }) { return <Surface className="overflow-hidden"><PanelHeader title={title} /><div className="divide-y">{rows.map((row) => { const item = render(row); return <div key={row.id} className="p-4 sm:p-5"><div className="font-semibold">{item.title}</div>{item.meta && <div className="mt-1 text-xs text-muted-foreground">{item.meta}</div>}</div>; })}</div></Surface>; }
function SummaryCard({ label, value, warning, format = "money" }) { return <Surface className={warning ? "border-warning/40 p-5" : "p-5"}><div className="text-xs font-semibold text-muted-foreground">{label}</div><div className={`mt-3 font-display text-2xl font-semibold ${warning ? "text-warning" : ""}`}>{format === "money" ? money(value) : value}</div></Surface>; }
function MoneyStat({ label, value, warning }) { return <div className="min-w-0 px-3 text-center"><div className="text-[11px] text-muted-foreground">{label}</div><div className={`mt-2 truncate font-display text-lg font-semibold sm:text-xl ${warning ? "text-warning" : ""}`}>{money(value)}</div></div>; }
function MetaCell({ label, value }) { return <div className="bg-card p-4"><div className="text-[11px] text-muted-foreground">{label}</div><div className="mt-1.5 text-sm font-semibold">{value}</div></div>; }
function Count({ label, value }) { return <div className="rounded-xl bg-secondary p-3 text-center"><div className="font-display text-2xl font-semibold">{value}</div><div className="mt-1 text-[11px] text-muted-foreground">{label}</div></div>; }
function operationsLabel(industry) { return industry === "gym" ? "Gym operations" : industry === "salon" ? "Salon operations" : industry === "college" ? "Academics" : "Care operations"; }
function Info({ label, value, warning }) { return <div><div className="text-[11px] text-muted-foreground">{label}</div><div className={`mt-1 text-sm font-semibold ${warning ? "text-warning" : ""}`}>{value}</div></div>; }
function SectionTitle({ title, action }) { return <div className="flex items-center justify-between gap-3"><h3 className="font-display text-lg font-semibold">{title}</h3>{action}</div>; }
function DetailRow({ icon: Icon, label, value }) { return <div className="flex gap-3 py-3 first:pt-0 last:pb-0"><Icon className="mt-0.5 shrink-0 text-muted-foreground" /><div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-sm">{value}</div></div></div>; }
function Field({ label, children, error }) { return <div className="space-y-2"><Label>{label}</Label>{children}<FieldError error={error} /></div>; }
function MoneyRow({ label, value, detail, strong, hidden }) { if (hidden) return null; return <div className={`flex items-center justify-between gap-4 py-2 text-sm ${strong ? "mt-2 border-t pt-4 font-display text-xl font-semibold" : ""}`}><span>{label}{detail && <span className="ml-2 text-xs font-normal text-muted-foreground">{detail}</span>}</span><span>{money(value)}</span></div>; }
function ProfileSkeleton() { return <PageShell><div className="h-28 animate-pulse rounded-2xl bg-secondary" /><div className="h-12 w-96 max-w-full animate-pulse rounded-xl bg-secondary" /><div className="grid gap-5 xl:grid-cols-2"><div className="h-80 animate-pulse rounded-2xl bg-secondary" /><div className="h-80 animate-pulse rounded-2xl bg-secondary" /></div></PageShell>; }
function activityIcon(type) { if (["invoice", "invoice_void", "payment"].includes(type)) return <Receipt />; if (["membership", "renewal", "cancellation", "cancellation_reversal"].includes(type)) return <Wallet />; if (type === "visit") return <CheckCircle />; return <CalendarBlank />; }
function field(setter, key) { return (event) => setter((current) => ({ ...current, [key]: event.target.value })); }
function compactMetrics(values) { return Object.fromEntries(["weight_kg", "height_cm", "body_fat_percent", "waist_cm"].filter((key) => values[key] !== "" && values[key] != null).map((key) => [key, Number(values[key])])); }
function errorMessage(error, fallback) { return error?.data?.detail || error?.response?.data?.detail || fallback; }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function money(value) { return formatMetric(value || 0, "money"); }
function dateOnly(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${String(value).slice(0, 10)}T12:00:00`)) : "Not set"; }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)) : "Not set"; }
function today() { return new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
