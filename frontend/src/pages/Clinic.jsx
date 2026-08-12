import React, { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight, Books, CalendarBlank, FirstAid, Flask, Heartbeat, Pill, Plus,
  ShieldCheck, Stethoscope, UserCircle, UsersThree,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import {
  DataTable, DrawerForm, EmptyState, ErrorState, MetricCard, MetricStrip, PageHeader, PageShell,
  StatusBadge, Surface,
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
  useAddDiagnosisMutation, useCreateEncounterMutation, useCreateLabOrderMutation,
  useCreateLabTestMutation, useCreatePatientProfileMutation, useCreatePrescriptionMutation,
  useDispensePrescriptionMutation, useGetClinicEncountersQuery, useGetClinicLabOrdersQuery,
  useGetClinicLabTestsQuery, useGetClinicPatientsQuery, useGetClinicPrescriptionsQuery,
  useGetClinicQueueQuery, useGetClinicSummaryQuery, useSignEncounterMutation,
  useSignLabOrderMutation, useSignPrescriptionMutation, useUpdateEncounterMutation,
} from "@/features/clinic/clinicApi";
import {
  useGetCatalogItemsQuery, useGetClientsQuery, useGetEmployeesQuery, useGetInventoryWorkspaceQuery,
} from "@/store/api/workspaceApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { usePendingAction } from "@/hooks/usePendingAction";
import {
  applyApiErrors, clinicalEncounterDraftSchema, diagnosisSchema, dispenseSchema, encounterSchema,
  FORM_OPTIONS, labOrderSchema, labTestSchema, patientSchema, prescriptionDraftSchema,
} from "@/lib/validation";


const allSections = [
  { id: "overview", label: "Overview" },
  { id: "queue", label: "Queue" },
  { id: "patients", label: "Patients", permission: "clinical.view" },
  { id: "encounters", label: "Encounters", permission: "clinical.view" },
  { id: "prescriptions", label: "Prescriptions", permission: "clinical.view" },
  { id: "labs", label: "Labs", permission: "clinical.view" },
  { id: "pharmacy", label: "Pharmacy", permission: "pharmacy.dispense" },
  { id: "documents", label: "Documents", permission: "documents.view" },
  { id: "audit", label: "Audit", permission: "settings.audit.view" },
];


export default function Clinic() {
  const { can } = useAuth();
  const { locationId } = useBusiness();
  const route = useLocation();
  const navigate = useNavigate();
  const sections = allSections.filter((section) => !section.permission || can(section.permission));
  const pathSection = route.pathname.split("/").filter(Boolean).pop();
  const active = sections.some((section) => section.id === pathSection) ? pathSection : "overview";
  const [patientOpen, setPatientOpen] = useState(false);
  const [encounterOpen, setEncounterOpen] = useState(false);
  const [record, setRecord] = useState(null);
  const [labOpen, setLabOpen] = useState(false);
  const [dispense, setDispense] = useState(null);
  const clinical = can("clinical.view");

  const summaryQuery = useGetClinicSummaryQuery({ locationId }, withSkip(QUERY_POLICIES.live, !locationId));
  const queueNeeded = ["overview", "queue"].includes(active) || encounterOpen;
  const queueQuery = useGetClinicQueueQuery({ locationId }, withSkip(QUERY_POLICIES.live, !locationId || !queueNeeded));
  const patientsNeeded = active === "patients" || encounterOpen || labOpen;
  const patientsQuery = useGetClinicPatientsQuery({ locationId }, withSkip(QUERY_POLICIES.collaborative, !locationId || !clinical || !patientsNeeded));
  const encountersNeeded = active === "encounters" || labOpen;
  const encountersQuery = useGetClinicEncountersQuery({ locationId }, withSkip(QUERY_POLICIES.operational, !locationId || !clinical || !encountersNeeded));
  const prescriptionsNeeded = active === "prescriptions" || active === "pharmacy";
  const prescriptionsQuery = useGetClinicPrescriptionsQuery({ locationId }, withSkip(QUERY_POLICIES.operational, !locationId || !clinical || !prescriptionsNeeded));
  const testsQuery = useGetClinicLabTestsQuery(undefined, withSkip(QUERY_POLICIES.reference, !clinical || (active !== "labs" && !labOpen)));
  const ordersQuery = useGetClinicLabOrdersQuery({ locationId }, withSkip(QUERY_POLICIES.operational, !locationId || !clinical || active !== "labs"));
  const medicinesQuery = useGetCatalogItemsQuery(undefined, withSkip(QUERY_POLICIES.reference, !record && active !== "pharmacy"));
  const inventoryQuery = useGetInventoryWorkspaceQuery({ locationId, q: "", state: undefined }, withSkip(QUERY_POLICIES.operational, !locationId || active !== "pharmacy"));

  const summary = summaryQuery.data;
  const metrics = summary ? [
    { id: "appointments", label: "Appointments today", value: summary.appointments_today },
    { id: "waiting", label: "Waiting now", value: summary.waiting, tone: summary.waiting ? "warning" : "neutral" },
    ...(summary.open_encounters == null ? [] : [{ id: "encounters", label: "Open encounters", value: summary.open_encounters }]),
    ...(summary.lab_orders_pending == null ? [] : [{ id: "labs", label: "Labs pending", value: summary.lab_orders_pending, tone: summary.lab_orders_pending ? "warning" : "neutral" }]),
  ] : [];
  const changeSection = (section) => navigate(section === "overview" ? "/app/clinic" : `/app/clinic/${section}`);

  return <PageShell className="reveal">
    <PageHeader
      eyebrow="Outpatient clinic"
      title="Care, clearly coordinated"
      description="A role-safe workspace for appointments, queue movement, encounters, prescriptions, laboratory work, and dispensing."
      actions={<>{can("appointments.manage") && <Button variant="outline" onClick={() => navigate("/app/calendar?new=1")}><CalendarBlank className="mr-2" />Book Patient</Button>}{can("clinical.write") && <Button onClick={() => setEncounterOpen(true)}><FirstAid className="mr-2" />Start encounter</Button>}</>}
    />
    <Tabs value={active} onValueChange={changeSection}>
      <TabsList className="premium-scrollbar h-auto w-full justify-start overflow-x-auto rounded-xl bg-secondary/60 p-1">{sections.map((section) => <TabsTrigger className="whitespace-nowrap" key={section.id} value={section.id}>{section.label}</TabsTrigger>)}</TabsList>
      <TabsContent value="overview" className="mt-6 space-y-6">
        {summaryQuery.isError && !summary ? <ErrorState title="Clinic summary could not be loaded" description={summaryQuery.error?.data?.detail} retry={summaryQuery.refetch} /> : <MetricStrip metrics={metrics} loading={summaryQuery.isLoading && !summary} />}
        <QueuePanel rows={queueQuery.data || []} loading={queueQuery.isLoading} error={queueQuery.isError} retry={queueQuery.refetch} compact onOpenPatient={(id) => navigate(`/app/clients/${id}`)} onOpenAll={() => changeSection("queue")} />
        <div className="grid gap-5 lg:grid-cols-3"><Destination icon={UsersThree} title="Patient records" description="Identity, encounters, allergies, prescriptions, and labs remain separated by clinical permission." action={clinical ? <Button variant="outline" onClick={() => changeSection("patients")}>Open Patients<ArrowRight className="ml-2" /></Button> : null} /><Destination icon={Pill} title="Medication work" description="Only signed prescriptions become eligible for dispensing and stock reduction." action={can("pharmacy.dispense") ? <Button variant="outline" onClick={() => changeSection("pharmacy")}>Open pharmacy<ArrowRight className="ml-2" /></Button> : null} /><Destination icon={ShieldCheck} title="Clinical safeguards" description="Signed records are immutable and every sensitive read or write remains attributable." action={can("settings.audit.view") ? <Button variant="outline" onClick={() => changeSection("audit")}>Review audit<ArrowRight className="ml-2" /></Button> : null} /></div>
      </TabsContent>
      <TabsContent value="queue" className="mt-6"><QueuePanel rows={queueQuery.data || []} loading={queueQuery.isLoading} error={queueQuery.isError} retry={queueQuery.refetch} onOpenPatient={(id) => navigate(`/app/clients/${id}`)} /></TabsContent>
      <TabsContent value="patients" className="mt-6"><PatientsPanel query={patientsQuery} canCreate={can("clinic.manage")} onCreate={() => setPatientOpen(true)} onOpen={(id) => navigate(`/app/clients/${id}`)} /></TabsContent>
      <TabsContent value="encounters" className="mt-6"><EncountersPanel query={encountersQuery} canCreate={can("clinical.write")} onCreate={() => setEncounterOpen(true)} onOpen={setRecord} /></TabsContent>
      <TabsContent value="prescriptions" className="mt-6"><PrescriptionsPanel query={prescriptionsQuery} canSign={can("clinical.sign")} /></TabsContent>
      <TabsContent value="labs" className="mt-6"><LabsPanel ordersQuery={ordersQuery} canManage={can("clinic.manage")} canWrite={can("clinical.write")} canSign={can("clinical.sign")} onCreate={() => setLabOpen(true)} /></TabsContent>
      <TabsContent value="pharmacy" className="mt-6"><PharmacyPanel prescriptions={prescriptionsQuery.data || []} prescriptionsLoading={prescriptionsQuery.isLoading} inventory={inventoryQuery.data} inventoryLoading={inventoryQuery.isLoading} onDispense={setDispense} /></TabsContent>
      <TabsContent value="documents" className="mt-6"><Destination icon={Books} title="Medical documents" description="Upload, classify, and securely preview Patient-linked files from the Documents workspace." action={<Button onClick={() => navigate("/app/documents")}>Open documents<ArrowRight className="ml-2" /></Button>} /></TabsContent>
      <TabsContent value="audit" className="mt-6"><Destination icon={ShieldCheck} title="Clinical audit history" description="Sensitive record access and signed changes are retained in the organization audit trail." action={<Button onClick={() => navigate("/app/settings?section=audit")}>Open audit history<ArrowRight className="ml-2" /></Button>} /></TabsContent>
    </Tabs>
    <PatientDrawer open={patientOpen} onOpenChange={setPatientOpen} locationId={locationId} />
    <EncounterDrawer open={encounterOpen} onOpenChange={setEncounterOpen} locationId={locationId} patients={patientsQuery.data || []} patientsLoading={patientsQuery.isLoading} queue={queueQuery.data || []} />
    <ClinicalRecordDrawer record={record} onOpenChange={(open) => !open && setRecord(null)} medicines={(medicinesQuery.data || []).filter((item) => item.item_type === "medicine" && item.is_active)} canWrite={can("clinical.write")} canSign={can("clinical.sign")} />
    <LabDrawer open={labOpen} onOpenChange={setLabOpen} encounters={encountersQuery.data || []} tests={testsQuery.data || []} canManage={can("clinic.manage")} canWrite={can("clinical.write")} />
    <DispenseDrawer prescription={dispense} onOpenChange={(open) => !open && setDispense(null)} locationId={locationId} levels={inventoryQuery.data?.levels || []} />
  </PageShell>;
}


function QueuePanel({ rows, loading, error, retry, compact, onOpenPatient, onOpenAll }) {
  if (error && !rows.length) return <ErrorState title="Patient queue could not be loaded" retry={retry} />;
  const visible = compact ? rows.slice(0, 6) : rows;
  return <Surface className="overflow-hidden"><div className="flex items-center justify-between border-b p-5"><div><h2 className="font-display text-2xl font-semibold">Today&apos;s queue</h2><p className="mt-1 text-sm text-muted-foreground">Live arrival order and care status for this location.</p></div>{onOpenAll && <Button variant="ghost" onClick={onOpenAll}>View queue<ArrowRight className="ml-2" /></Button>}</div><DataTable className="rounded-none border-0 shadow-none" loading={loading} rows={visible} columns={queueColumns(onOpenPatient)} empty={<EmptyState variant="inline" icon={Stethoscope} title="The queue is clear" description="Scheduled and checked-in Patients appear here in organization local time." className="m-4" />} /></Surface>;
}

function queueColumns(onOpenPatient) { return [
  { key: "patient", label: "Patient", render: (row) => <button className="text-left font-semibold hover:text-accent" onClick={(event) => { event.stopPropagation(); if (row.patient?.client_id) onOpenPatient(row.patient.client_id); }}>{row.patient?.display_name || "Patient"}<span className="mt-1 block text-xs font-normal text-muted-foreground">{row.patient?.client_number}</span></button> },
  { key: "time", label: "Time", render: (row) => dateTime(row.starts_at, { timeOnly: true }) },
  { key: "service", label: "Visit", render: (row) => row.service_name || "General consultation" },
  { key: "practitioner", label: "Practitioner", render: (row) => row.practitioner_name || "Unassigned" },
  { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
]; }


function PatientsPanel({ query, canCreate, onCreate, onOpen }) {
  if (query.isError && !query.data) return <ErrorState title="Patients could not be loaded" description={query.error?.data?.detail} retry={query.refetch} />;
  const columns = [
    { key: "patient", label: "Patient", render: (row) => <div><div className="font-semibold">{row.client?.display_name || "Patient"}</div><div className="mt-1 text-xs text-muted-foreground">{row.client?.client_number} · {row.client?.phone || "No phone"}</div></div> },
    { key: "blood_group", label: "Blood group", render: (row) => row.blood_group || "Not recorded" },
    { key: "abha_number", label: "ABHA", render: (row) => row.abha_number || "Not linked" },
    { key: "status", label: "Relationship", render: (row) => <StatusBadge status={row.client?.status || "active"} /> },
  ];
  return <div className="space-y-4"><div className="flex justify-end">{canCreate && <Button onClick={onCreate}><Plus className="mr-2" />Create Patient profile</Button>}</div><DataTable loading={query.isLoading} rows={query.data || []} columns={columns} onRowClick={(row) => onOpen(row.client_id)} empty={<EmptyState variant="page" alignment="left" icon={UsersThree} title="Create the first Patient profile" description="Connect an existing identity to protected clinical context before starting care." primaryAction={canCreate ? <Button onClick={onCreate}>Create Patient profile</Button> : null} steps={[{ title: "Choose identity" }, { title: "Add clinical context" }, { title: "Begin care" }]} />} /></div>;
}


function EncountersPanel({ query, canCreate, onCreate, onOpen }) {
  if (query.isError && !query.data) return <ErrorState title="Encounters could not be loaded" description={query.error?.data?.detail} retry={query.refetch} />;
  const columns = [
    { key: "patient", label: "Patient", render: (row) => <div><div className="font-semibold">{row.patient?.display_name || "Patient"}</div><div className="mt-1 text-xs text-muted-foreground">{row.chief_complaint || "No complaint recorded"}</div></div> },
    { key: "practitioner", label: "Practitioner", render: (row) => row.practitioner_name || "Unavailable" },
    { key: "created_at", label: "Opened", render: (row) => dateTime(row.created_at) },
    { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
    { key: "follow_up_on", label: "Follow-up", render: (row) => row.follow_up_on ? dateOnly(row.follow_up_on) : "Not set" },
  ];
  return <div className="space-y-4"><div className="flex justify-end">{canCreate && <Button onClick={onCreate}><FirstAid className="mr-2" />Start encounter</Button>}</div><DataTable loading={query.isLoading} rows={query.data || []} columns={columns} onRowClick={onOpen} empty={<EmptyState variant="page" alignment="left" icon={Heartbeat} title="No encounters yet" description="Start an encounter only when an authorized practitioner is ready to document care." primaryAction={canCreate ? <Button onClick={onCreate}>Start encounter</Button> : null} steps={[{ title: "Select Patient" }, { title: "Document care" }, { title: "Review and sign" }]} />} /></div>;
}


function PrescriptionsPanel({ query, canSign }) {
  const [sign] = useSignPrescriptionMutation();
  const pending = usePendingAction();
  const doSign = (row) => pending.run(`sign:${row.id}`, async () => { try { await sign(row.id).unwrap(); toast.success("Prescription signed and locked"); } catch (error) { toast.error(error?.data?.detail || "Prescription could not be signed"); } });
  if (query.isError && !query.data) return <ErrorState title="Prescriptions could not be loaded" retry={query.refetch} />;
  const columns = [
    { key: "patient", label: "Patient", render: (row) => row.patient?.display_name || "Patient" },
    { key: "items", label: "Medication", render: (row) => <div>{row.items.map((item) => item.medicine_name).join(", ") || "No items"}<div className="mt-1 text-xs text-muted-foreground">{row.items.map((item) => `${item.dosage} · ${item.frequency}`).join("; ")}</div></div> },
    { key: "created_at", label: "Created", render: (row) => dateTime(row.created_at) },
    { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
    { key: "action", label: "", render: (row) => row.status === "draft" && canSign ? <Button loading={pending.isPending(`sign:${row.id}`)} size="sm" onClick={(event) => { event.stopPropagation(); return doSign(row); }}>Review and sign</Button> : null },
  ];
  return <DataTable loading={query.isLoading} rows={query.data || []} columns={columns} empty={<EmptyState variant="section" alignment="left" icon={Pill} title="No prescriptions" description="Practitioners create prescription drafts from an open encounter, then explicitly review and sign them." />} />;
}


function LabsPanel({ ordersQuery, canManage, canWrite, canSign, onCreate }) {
  const [sign] = useSignLabOrderMutation();
  const pending = usePendingAction();
  const doSign = (row) => pending.run(`sign:${row.id}`, async () => { try { await sign(row.id).unwrap(); toast.success("Lab order signed"); } catch (error) { toast.error(error?.data?.detail || "Lab order could not be signed"); } });
  if (ordersQuery.isError && !ordersQuery.data) return <ErrorState title="Lab orders could not be loaded" retry={ordersQuery.refetch} />;
  const columns = [
    { key: "patient", label: "Patient", render: (row) => row.patient?.display_name || "Patient" },
    { key: "test", label: "Test", render: (row) => <div className="font-semibold">{row.test?.name || "Lab test"}<div className="mt-1 text-xs font-normal text-muted-foreground">{row.test?.code}</div></div> },
    { key: "created_at", label: "Ordered", render: (row) => dateTime(row.created_at) },
    { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
    { key: "action", label: "", render: (row) => !row.signed_at && canSign ? <Button loading={pending.isPending(`sign:${row.id}`)} size="sm" onClick={(event) => { event.stopPropagation(); return doSign(row); }}>Sign order</Button> : null },
  ];
  return <div className="space-y-4"><div className="flex justify-end">{(canManage || canWrite) && <Button onClick={onCreate}><Plus className="mr-2" />New lab work</Button>}</div><DataTable loading={ordersQuery.isLoading} rows={ordersQuery.data || []} columns={columns} empty={<EmptyState variant="section" alignment="left" icon={Flask} title="No lab orders" description="Authorized practitioners can order tests from an open encounter." primaryAction={(canManage || canWrite) ? <Button onClick={onCreate}>Create lab order</Button> : null} />} /></div>;
}


function PharmacyPanel({ prescriptions, prescriptionsLoading, inventory, inventoryLoading, onDispense }) {
  const ready = prescriptions.filter((row) => row.status === "signed");
  const medicineLevels = (inventory?.levels || []).filter((row) => row.item.item_type === "medicine");
  const low = medicineLevels.filter((row) => row.quantity_milli <= row.reorder_level_milli);
  return <div className="space-y-6"><div className="grid gap-3 sm:grid-cols-3"><MetricCard loading={prescriptionsLoading} metric={{ label: "Ready to dispense", value: ready.length }} /><MetricCard loading={inventoryLoading} metric={{ label: "Medicine batches", value: medicineLevels.length }} /><MetricCard loading={inventoryLoading} metric={{ label: "Low-stock batches", value: low.length, tone: low.length ? "warning" : "neutral" }} /></div><Surface className="overflow-hidden"><div className="border-b p-5"><h2 className="font-display text-2xl font-semibold">Dispensing queue</h2><p className="mt-1 text-sm text-muted-foreground">Only practitioner-signed prescriptions can reduce medicine stock.</p></div><DataTable className="rounded-none border-0 shadow-none" loading={prescriptionsLoading} rows={ready} columns={[
    { key: "patient", label: "Patient", render: (row) => row.patient?.display_name || "Patient" },
    { key: "items", label: "Medicines", render: (row) => row.items.map((item) => item.medicine_name).join(", ") },
    { key: "signed_at", label: "Signed", render: (row) => dateTime(row.signed_at) },
    { key: "action", label: "", render: (row) => <Button size="sm" onClick={(event) => { event.stopPropagation(); onDispense(row); }}>Dispense</Button> },
  ]} empty={<EmptyState compact icon={Pill} title="No prescriptions awaiting dispensing" description="Signed medication orders appear here automatically." />} /></Surface></div>;
}


function LegacyPatientDrawer({ open, onOpenChange, locationId }) {
  const clientsQuery = useGetClientsQuery({ locationId, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreatePatientProfileMutation();
  const [form, setForm] = useState({ client_id: "", abha_number: "", blood_group: "", emergency_phone: "" });
  const submit = async (event) => { event.preventDefault(); try { await create({ client_id: form.client_id, abha_number: form.abha_number || null, blood_group: form.blood_group || null, emergency_contact: form.emergency_phone ? { phone: form.emergency_phone } : {}, consent: { records: true } }).unwrap(); toast.success("Patient profile created"); setForm({ client_id: "", abha_number: "", blood_group: "", emergency_phone: "" }); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Patient profile could not be created"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Create Patient profile" description="Link an existing identity to the protected clinical record. Clinical access remains separately controlled."><form onSubmit={submit} className="space-y-5"><Field label="Identity"><Select required value={form.client_id} onValueChange={(client_id) => setForm({ ...form, client_id })} disabled={clientsQuery.isLoading}><SelectTrigger><SelectValue placeholder="Choose Patient identity" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name} · {client.client_number}</SelectItem>)}</SelectContent></Select></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="ABHA number"><Input value={form.abha_number} onChange={(event) => setForm({ ...form, abha_number: event.target.value })} /></Field><Field label="Blood group"><Input value={form.blood_group} onChange={(event) => setForm({ ...form, blood_group: event.target.value })} /></Field></div><Field label="Emergency phone"><Input value={form.emergency_phone} onChange={(event) => setForm({ ...form, emergency_phone: event.target.value })} /></Field><Button disabled={state.isLoading || !form.client_id} className="w-full">{state.isLoading ? "Creating..." : "Create Patient profile"}</Button></form></DrawerForm>;
}

function PatientDrawer({ open, onOpenChange, locationId }) {
  const clientsQuery = useGetClientsQuery({ locationId, q: "", limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreatePatientProfileMutation();
  const formApi = useForm({ resolver: zodResolver(patientSchema), defaultValues: { client_id: "", abha_number: "", blood_group: "", emergency_phone: "" }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  const clientId = watch("client_id");
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await create({ client_id: values.client_id, abha_number: values.abha_number, blood_group: values.blood_group, emergency_contact: values.emergency_phone ? { phone: values.emergency_phone } : {}, consent: { records: true } }).unwrap();
      toast.success("Patient profile created");
      reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { aliases: { "emergency_contact.phone": "emergency_phone" }, fallback: "Patient profile could not be created" });
      toast.error(normalized.message);
    }
  });
  const close = (next) => { if (!next && (formState.isSubmitting || state.isLoading)) return; onOpenChange(next); };
  return <DrawerForm open={open} onOpenChange={close} title="Create Patient profile" description="Link an existing identity to the protected clinical record. Clinical access remains separately controlled."><form noValidate onSubmit={submit} className="space-y-5"><Field label="Identity" error={formState.errors.client_id}><Select value={clientId} onValueChange={(value) => setValue("client_id", value, { shouldDirty: true, shouldValidate: true })} disabled={clientsQuery.isLoading}><SelectTrigger aria-invalid={Boolean(formState.errors.client_id)}><SelectValue placeholder="Choose Patient identity" /></SelectTrigger><SelectContent>{(clientsQuery.data?.items || []).map((client) => <SelectItem key={client.id} value={client.id}>{client.first_name} {client.last_name} / {client.client_number}</SelectItem>)}</SelectContent></Select></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="ABHA number" error={formState.errors.abha_number}><Input {...register("abha_number")} aria-invalid={Boolean(formState.errors.abha_number)} /></Field><Field label="Blood group" error={formState.errors.blood_group}><Input {...register("blood_group")} aria-invalid={Boolean(formState.errors.blood_group)} /></Field></div><Field label="Emergency phone" error={formState.errors.emergency_phone}><Input inputMode="tel" {...register("emergency_phone")} aria-invalid={Boolean(formState.errors.emergency_phone)} /></Field><FormRootError error={formState.errors.root?.server} /><Button type="submit" loading={formState.isSubmitting || state.isLoading} loadingText="Creating profile..." className="w-full">Create Patient profile</Button></form></DrawerForm>;
}


function LegacyEncounterDrawer({ open, onOpenChange, locationId, patients, patientsLoading, queue }) {
  const employeesQuery = useGetEmployeesQuery({ limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateEncounterMutation();
  const [form, setForm] = useState({ patient_id: "", practitioner_employee_id: "", appointment_id: "none", chief_complaint: "" });
  const submit = async (event) => { event.preventDefault(); try { await create({ ...form, location_id: locationId, appointment_id: form.appointment_id === "none" ? null : form.appointment_id }).unwrap(); toast.success("Encounter opened"); setForm({ patient_id: "", practitioner_employee_id: "", appointment_id: "none", chief_complaint: "" }); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Encounter could not be opened"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Start encounter" description="The Patient, practitioner, appointment, and location are validated together before a clinical record opens."><form onSubmit={submit} className="space-y-5"><Field label="Patient"><Select required value={form.patient_id} onValueChange={(patient_id) => setForm({ ...form, patient_id })} disabled={patientsLoading}><SelectTrigger><SelectValue placeholder="Choose Patient" /></SelectTrigger><SelectContent>{patients.map((patient) => <SelectItem key={patient.id} value={patient.id}>{patient.client?.display_name || "Patient"}</SelectItem>)}</SelectContent></Select></Field><Field label="Practitioner"><Select required value={form.practitioner_employee_id} onValueChange={(practitioner_employee_id) => setForm({ ...form, practitioner_employee_id })} disabled={employeesQuery.isLoading}><SelectTrigger><SelectValue placeholder="Choose practitioner" /></SelectTrigger><SelectContent>{(employeesQuery.data?.items || []).map((employee) => <SelectItem key={employee.id} value={employee.id}>{employee.first_name} {employee.last_name} · {employee.designation || "Team"}</SelectItem>)}</SelectContent></Select></Field><Field label="Queue appointment"><Select value={form.appointment_id} onValueChange={(appointment_id) => setForm({ ...form, appointment_id })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">No linked appointment</SelectItem>{queue.map((row) => <SelectItem key={row.id} value={row.id}>{row.patient?.display_name || "Patient"} · {dateTime(row.starts_at, { timeOnly: true })}</SelectItem>)}</SelectContent></Select></Field><Field label="Chief complaint"><Textarea required value={form.chief_complaint} onChange={(event) => setForm({ ...form, chief_complaint: event.target.value })} placeholder="Record the Patient's presenting concern" /></Field><Button disabled={state.isLoading || !form.patient_id || !form.practitioner_employee_id} className="w-full">{state.isLoading ? "Opening securely..." : "Open encounter"}</Button></form></DrawerForm>;
}

function EncounterDrawer({ open, onOpenChange, locationId, patients, patientsLoading, queue }) {
  const employeesQuery = useGetEmployeesQuery({ limit: 100 }, withSkip(QUERY_POLICIES.reference, !open));
  const [create, state] = useCreateEncounterMutation();
  const formApi = useForm({ resolver: zodResolver(encounterSchema), defaultValues: { location_id: locationId || "", patient_id: "", practitioner_employee_id: "", appointment_id: null, chief_complaint: "" }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError, setValue, watch } = formApi;
  useEffect(() => { setValue("location_id", locationId || "", { shouldValidate: Boolean(locationId) }); }, [locationId, setValue]);
  const patientId = watch("patient_id");
  const practitionerId = watch("practitioner_employee_id");
  const appointmentId = watch("appointment_id");
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await create(values).unwrap();
      toast.success("Encounter opened");
      reset({ location_id: locationId || "", patient_id: "", practitioner_employee_id: "", appointment_id: null, chief_complaint: "" });
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Encounter could not be opened" });
      toast.error(normalized.message);
    }
  });
  const close = (next) => { if (!next && (formState.isSubmitting || state.isLoading)) return; onOpenChange(next); };
  return <DrawerForm open={open} onOpenChange={close} title="Start encounter" description="The Patient, practitioner, appointment, and location are validated together before a clinical record opens."><form noValidate onSubmit={submit} className="space-y-5"><Field label="Patient" error={formState.errors.patient_id}><Select value={patientId} onValueChange={(value) => setValue("patient_id", value, { shouldDirty: true, shouldValidate: true })} disabled={patientsLoading}><SelectTrigger aria-invalid={Boolean(formState.errors.patient_id)}><SelectValue placeholder="Choose Patient" /></SelectTrigger><SelectContent>{patients.map((patient) => <SelectItem key={patient.id} value={patient.id}>{patient.client?.display_name || "Patient"}</SelectItem>)}</SelectContent></Select></Field><Field label="Practitioner" error={formState.errors.practitioner_employee_id}><Select value={practitionerId} onValueChange={(value) => setValue("practitioner_employee_id", value, { shouldDirty: true, shouldValidate: true })} disabled={employeesQuery.isLoading}><SelectTrigger aria-invalid={Boolean(formState.errors.practitioner_employee_id)}><SelectValue placeholder="Choose practitioner" /></SelectTrigger><SelectContent>{(employeesQuery.data?.items || []).map((employee) => <SelectItem key={employee.id} value={employee.id}>{employee.first_name} {employee.last_name} / {employee.designation || "Team"}</SelectItem>)}</SelectContent></Select></Field><Field label="Queue appointment" error={formState.errors.appointment_id}><Select value={appointmentId || "none"} onValueChange={(value) => setValue("appointment_id", value === "none" ? null : value, { shouldDirty: true, shouldValidate: true })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">No linked appointment</SelectItem>{queue.map((row) => <SelectItem key={row.id} value={row.id}>{row.patient?.display_name || "Patient"} / {dateTime(row.starts_at, { timeOnly: true })}</SelectItem>)}</SelectContent></Select></Field><Field label="Chief complaint" error={formState.errors.chief_complaint}><Textarea {...register("chief_complaint")} placeholder="Record the Patient's presenting concern" aria-invalid={Boolean(formState.errors.chief_complaint)} /></Field><FormRootError error={formState.errors.root?.server} /><Button type="submit" loading={formState.isSubmitting || state.isLoading} loadingText="Opening securely..." className="w-full">Open encounter</Button></form></DrawerForm>;
}


function LegacyClinicalRecordDrawer({ record, onOpenChange, medicines, canWrite, canSign }) {
  const [update, updateState] = useUpdateEncounterMutation();
  const [diagnose, diagnosisState] = useAddDiagnosisMutation();
  const [sign, signState] = useSignEncounterMutation();
  const [createPrescription, prescriptionState] = useCreatePrescriptionMutation();
  const [notes, setNotes] = useState(null);
  const [diagnosis, setDiagnosis] = useState("");
  const [rx, setRx] = useState({ medicine_item_id: "manual", medicine_name: "", dosage: "", frequency: "", duration: "", instructions: "" });
  const current = notes?.id === record?.id ? notes : record ? { id: record.id, chief_complaint: record.chief_complaint || "", clinical_notes: record.clinical_notes || "", assessment: record.assessment || "", plan: record.plan || "", follow_up_on: record.follow_up_on || "", version: record.version } : null;
  const setCurrent = (key, value) => setNotes({ ...current, [key]: value });
  const save = async () => { try { const updated = await update({ encounterId: record.id, chief_complaint: current.chief_complaint || null, clinical_notes: current.clinical_notes || null, assessment: current.assessment || null, plan: current.plan || null, follow_up_on: current.follow_up_on || null, version: current.version }).unwrap(); setNotes({ ...updated, id: updated.id }); toast.success("Clinical draft saved"); } catch (error) { toast.error(error?.data?.detail || "Clinical draft could not be saved"); } };
  const addDiagnosis = async () => { if (!diagnosis.trim()) return; try { await diagnose({ encounterId: record.id, description: diagnosis.trim(), is_primary: true, ai_suggested: false }).unwrap(); setDiagnosis(""); toast.success("Diagnosis recorded"); } catch (error) { toast.error(error?.data?.detail || "Diagnosis could not be recorded"); } };
  const addPrescription = async () => { const selected = medicines.find((item) => item.id === rx.medicine_item_id); const name = selected?.name || rx.medicine_name.trim(); if (!name || !rx.dosage || !rx.frequency || !rx.duration) return; try { await createPrescription({ encounter_id: record.id, items: [{ medicine_item_id: selected?.id || null, medicine_name: name, dosage: rx.dosage, frequency: rx.frequency, duration: rx.duration, instructions: rx.instructions || null }], ai_drafted: false }).unwrap(); setRx({ medicine_item_id: "manual", medicine_name: "", dosage: "", frequency: "", duration: "", instructions: "" }); toast.success("Prescription draft created"); } catch (error) { toast.error(error?.data?.detail || "Prescription draft could not be created"); } };
  const signRecord = async () => { try { await sign(record.id).unwrap(); toast.success("Encounter signed and locked"); setNotes(null); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Encounter could not be signed"); } };
  const editable = record?.status !== "signed" && canWrite;
  return <DrawerForm open={Boolean(record)} onOpenChange={(open) => { if (!open) setNotes(null); onOpenChange(open); }} title={record?.patient?.display_name || "Clinical encounter"} description={record ? `${record.practitioner_name || "Practitioner"} · ${dateTime(record.created_at)}` : ""} className="sm:max-w-2xl">{record && current && <div className="space-y-6"><Surface className="border-accent/30 bg-accent/5 p-4"><div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 text-accent" /><p className="text-sm leading-6">Clinical content becomes immutable after the assigned practitioner signs it. Draft changes remain fully attributable.</p></div></Surface><Field label="Chief complaint"><Textarea disabled={!editable} value={current.chief_complaint} onChange={(event) => setCurrent("chief_complaint", event.target.value)} /></Field><Field label="Clinical notes"><Textarea disabled={!editable} className="min-h-28" value={current.clinical_notes} onChange={(event) => setCurrent("clinical_notes", event.target.value)} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Assessment"><Textarea disabled={!editable} value={current.assessment} onChange={(event) => setCurrent("assessment", event.target.value)} /></Field><Field label="Care plan"><Textarea disabled={!editable} value={current.plan} onChange={(event) => setCurrent("plan", event.target.value)} /></Field></div><Field label="Follow-up date"><Input disabled={!editable} type="date" value={current.follow_up_on} onChange={(event) => setCurrent("follow_up_on", event.target.value)} /></Field>{editable && <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={updateState.isLoading} onClick={save}>{updateState.isLoading ? "Saving..." : "Save draft"}</Button>{canSign && <Button disabled={signState.isLoading} onClick={signRecord}>{signState.isLoading ? "Signing..." : "Review and sign encounter"}</Button>}</div>}{editable && <Surface className="p-5"><h3 className="font-display text-xl font-semibold">Diagnosis</h3><div className="mt-4 flex gap-2"><Input value={diagnosis} onChange={(event) => setDiagnosis(event.target.value)} placeholder="Clinical diagnosis" /><Button variant="outline" disabled={diagnosisState.isLoading || !diagnosis.trim()} onClick={addDiagnosis}>Add</Button></div></Surface>}{editable && <Surface className="p-5"><h3 className="font-display text-xl font-semibold">Prescription draft</h3><div className="mt-4 space-y-4"><Field label="Medicine"><Select value={rx.medicine_item_id} onValueChange={(medicine_item_id) => setRx({ ...rx, medicine_item_id })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="manual">Manual medicine</SelectItem>{medicines.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></Field>{rx.medicine_item_id === "manual" && <Field label="Medicine name"><Input value={rx.medicine_name} onChange={(event) => setRx({ ...rx, medicine_name: event.target.value })} /></Field>}<div className="grid gap-4 sm:grid-cols-3"><Field label="Dosage"><Input value={rx.dosage} onChange={(event) => setRx({ ...rx, dosage: event.target.value })} /></Field><Field label="Frequency"><Input value={rx.frequency} onChange={(event) => setRx({ ...rx, frequency: event.target.value })} /></Field><Field label="Duration"><Input value={rx.duration} onChange={(event) => setRx({ ...rx, duration: event.target.value })} /></Field></div><Field label="Instructions"><Textarea value={rx.instructions} onChange={(event) => setRx({ ...rx, instructions: event.target.value })} /></Field><Button variant="outline" disabled={prescriptionState.isLoading} onClick={addPrescription}>Create prescription draft</Button></div></Surface>}</div>}</DrawerForm>;
}


function ClinicalRecordDrawer({ record, onOpenChange, medicines, canWrite, canSign }) {
  const [update, updateState] = useUpdateEncounterMutation();
  const [diagnose, diagnosisState] = useAddDiagnosisMutation();
  const [sign, signState] = useSignEncounterMutation();
  const [createPrescription, prescriptionState] = useCreatePrescriptionMutation();
  const draftApi = useForm({
    resolver: zodResolver(clinicalEncounterDraftSchema),
    defaultValues: encounterDraftValues(record),
    ...FORM_OPTIONS,
  });
  const diagnosisApi = useForm({
    resolver: zodResolver(diagnosisSchema),
    defaultValues: { description: "" },
    ...FORM_OPTIONS,
  });
  const prescriptionApi = useForm({
    resolver: zodResolver(prescriptionDraftSchema),
    defaultValues: emptyPrescription(),
    ...FORM_OPTIONS,
  });
  const selectedMedicine = prescriptionApi.watch("medicine_item_id");

  useEffect(() => {
    draftApi.reset(encounterDraftValues(record));
  }, [record?.id, record?.version]);

  const persistDraft = async (values, announce = true) => {
    draftApi.clearErrors("root.server");
    try {
      const updated = await update({ encounterId: record.id, ...values }).unwrap();
      draftApi.reset(encounterDraftValues(updated));
      if (announce) toast.success("Clinical draft saved");
      return updated;
    } catch (error) {
      const normalized = applyApiErrors(error, draftApi.setError, { fallback: "Clinical draft could not be saved" });
      toast.error(normalized.message);
      return null;
    }
  };

  const save = draftApi.handleSubmit((values) => persistDraft(values));
  const addDiagnosis = diagnosisApi.handleSubmit(async (values) => {
    diagnosisApi.clearErrors("root.server");
    try {
      await diagnose({ encounterId: record.id, description: values.description, is_primary: true, ai_suggested: false }).unwrap();
      diagnosisApi.reset();
      toast.success("Diagnosis recorded");
    } catch (error) {
      const normalized = applyApiErrors(error, diagnosisApi.setError, { fallback: "Diagnosis could not be recorded" });
      toast.error(normalized.message);
    }
  });
  const addPrescription = prescriptionApi.handleSubmit(async (values) => {
    prescriptionApi.clearErrors("root.server");
    const selected = medicines.find((item) => item.id === values.medicine_item_id);
    try {
      await createPrescription({
        encounter_id: record.id,
        items: [{
          medicine_item_id: selected?.id || null,
          medicine_name: selected?.name || values.medicine_name,
          dosage: values.dosage,
          frequency: values.frequency,
          duration: values.duration,
          instructions: values.instructions,
        }],
        ai_drafted: false,
      }).unwrap();
      prescriptionApi.reset(emptyPrescription());
      toast.success("Prescription draft created");
    } catch (error) {
      const normalized = applyApiErrors(error, prescriptionApi.setError, { fallback: "Prescription draft could not be created" });
      toast.error(normalized.message);
    }
  });
  const signRecord = async () => {
    draftApi.clearErrors("root.server");
    if (!(await draftApi.trigger())) return;
    if (draftApi.formState.isDirty && !await persistDraft(draftApi.getValues(), false)) return;
    try {
      await sign(record.id).unwrap();
      toast.success("Encounter signed and locked");
      draftApi.reset(encounterDraftValues(null));
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, draftApi.setError, { fallback: "Encounter could not be signed" });
      toast.error(normalized.message);
    }
  };

  const editable = record?.status !== "signed" && canWrite;
  const busy = updateState.isLoading || diagnosisState.isLoading || signState.isLoading || prescriptionState.isLoading
    || draftApi.formState.isSubmitting || diagnosisApi.formState.isSubmitting || prescriptionApi.formState.isSubmitting;
  const close = (open) => {
    if (!open && busy) return;
    onOpenChange(open);
  };

  return <DrawerForm
    open={Boolean(record)}
    onOpenChange={close}
    title={record?.patient?.display_name || "Clinical encounter"}
    description={record ? `${record.practitioner_name || "Practitioner"} / ${dateTime(record.created_at)}` : ""}
    className="sm:max-w-2xl"
  >
    {record && <div className="space-y-6">
      <Surface className="border-accent/30 bg-accent/5 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 text-accent" />
          <p className="text-sm leading-6">Clinical content becomes immutable after the assigned practitioner signs it. Draft changes remain fully attributable.</p>
        </div>
      </Surface>

      <form noValidate onSubmit={save} className="space-y-4">
        <Field label="Chief complaint" error={draftApi.formState.errors.chief_complaint}>
          <Textarea disabled={!editable} {...draftApi.register("chief_complaint")} aria-invalid={Boolean(draftApi.formState.errors.chief_complaint)} />
        </Field>
        <Field label="Clinical notes" error={draftApi.formState.errors.clinical_notes}>
          <Textarea disabled={!editable} className="min-h-28" {...draftApi.register("clinical_notes")} aria-invalid={Boolean(draftApi.formState.errors.clinical_notes)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Assessment" error={draftApi.formState.errors.assessment}>
            <Textarea disabled={!editable} {...draftApi.register("assessment")} aria-invalid={Boolean(draftApi.formState.errors.assessment)} />
          </Field>
          <Field label="Care plan" error={draftApi.formState.errors.plan}>
            <Textarea disabled={!editable} {...draftApi.register("plan")} aria-invalid={Boolean(draftApi.formState.errors.plan)} />
          </Field>
        </div>
        <Field label="Follow-up date" error={draftApi.formState.errors.follow_up_on}>
          <Input disabled={!editable} type="date" {...draftApi.register("follow_up_on")} aria-invalid={Boolean(draftApi.formState.errors.follow_up_on)} />
        </Field>
        <FormRootError error={draftApi.formState.errors.root?.server} />
        {editable && <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="outline" loading={updateState.isLoading || draftApi.formState.isSubmitting} loadingText="Saving draft..." disabled={busy && !updateState.isLoading}>Save draft</Button>
          {canSign && <Button type="button" loading={signState.isLoading} loadingText="Signing encounter..." disabled={busy && !signState.isLoading} onClick={signRecord}>Review and sign encounter</Button>}
        </div>}
      </form>

      {editable && <Surface className="p-5">
        <h3 className="font-display text-xl font-semibold">Diagnosis</h3>
        <form noValidate onSubmit={addDiagnosis} className="mt-4 space-y-2">
          <div className="flex gap-2">
            <Input {...diagnosisApi.register("description")} placeholder="Clinical diagnosis" aria-invalid={Boolean(diagnosisApi.formState.errors.description)} />
            <Button type="submit" variant="outline" loading={diagnosisState.isLoading || diagnosisApi.formState.isSubmitting} loadingText="Adding..." disabled={busy && !diagnosisState.isLoading}>Add</Button>
          </div>
          <FieldError error={diagnosisApi.formState.errors.description} />
          <FormRootError error={diagnosisApi.formState.errors.root?.server} />
        </form>
      </Surface>}

      {editable && <Surface className="p-5">
        <h3 className="font-display text-xl font-semibold">Prescription draft</h3>
        <form noValidate onSubmit={addPrescription} className="mt-4 space-y-4">
          <Field label="Medicine" error={prescriptionApi.formState.errors.medicine_item_id}>
            <Select value={selectedMedicine} onValueChange={(value) => prescriptionApi.setValue("medicine_item_id", value, { shouldDirty: true, shouldValidate: true })} disabled={busy}>
              <SelectTrigger aria-invalid={Boolean(prescriptionApi.formState.errors.medicine_item_id)}><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="manual">Manual medicine</SelectItem>{medicines.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          {selectedMedicine === "manual" && <Field label="Medicine name" error={prescriptionApi.formState.errors.medicine_name}>
            <Input {...prescriptionApi.register("medicine_name")} aria-invalid={Boolean(prescriptionApi.formState.errors.medicine_name)} />
          </Field>}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Dosage" error={prescriptionApi.formState.errors.dosage}><Input {...prescriptionApi.register("dosage")} aria-invalid={Boolean(prescriptionApi.formState.errors.dosage)} /></Field>
            <Field label="Frequency" error={prescriptionApi.formState.errors.frequency}><Input {...prescriptionApi.register("frequency")} aria-invalid={Boolean(prescriptionApi.formState.errors.frequency)} /></Field>
            <Field label="Duration" error={prescriptionApi.formState.errors.duration}><Input {...prescriptionApi.register("duration")} aria-invalid={Boolean(prescriptionApi.formState.errors.duration)} /></Field>
          </div>
          <Field label="Instructions" error={prescriptionApi.formState.errors.instructions}><Textarea {...prescriptionApi.register("instructions")} aria-invalid={Boolean(prescriptionApi.formState.errors.instructions)} /></Field>
          <FormRootError error={prescriptionApi.formState.errors.root?.server} />
          <Button type="submit" variant="outline" loading={prescriptionState.isLoading || prescriptionApi.formState.isSubmitting} loadingText="Creating draft..." disabled={busy && !prescriptionState.isLoading}>Create prescription draft</Button>
        </form>
      </Surface>}
    </div>}
  </DrawerForm>;
}


function encounterDraftValues(record) {
  return {
    chief_complaint: record?.chief_complaint || "",
    clinical_notes: record?.clinical_notes || "",
    assessment: record?.assessment || "",
    plan: record?.plan || "",
    follow_up_on: record?.follow_up_on || "",
    version: record?.version || 1,
  };
}


function emptyPrescription() {
  return { medicine_item_id: "manual", medicine_name: "", dosage: "", frequency: "", duration: "", instructions: "" };
}


function LegacyLabDrawer({ open, onOpenChange, encounters, tests, canManage, canWrite }) {
  const [mode, setMode] = useState(canWrite ? "order" : "test");
  const [form, setForm] = useState({ encounter_id: "", test_id: "", name: "", code: "", price: "" });
  const [createTest, testState] = useCreateLabTestMutation();
  const [createOrder, orderState] = useCreateLabOrderMutation();
  const submit = async (event) => { event.preventDefault(); try { if (mode === "test") await createTest({ name: form.name, code: form.code, price_paise: Math.round(Number(form.price || 0) * 100), reference_ranges: {} }).unwrap(); else await createOrder({ encounter_id: form.encounter_id, test_id: form.test_id }).unwrap(); toast.success(mode === "test" ? "Lab test added" : "Lab order created"); setForm({ encounter_id: "", test_id: "", name: "", code: "", price: "" }); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Lab work could not be saved"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="New lab work" description="Catalog administration and Patient orders remain separate clinical actions."><form onSubmit={submit} className="space-y-5"><Field label="Action"><Select value={mode} onValueChange={setMode}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{canWrite && <SelectItem value="order">Order a Patient test</SelectItem>}{canManage && <SelectItem value="test">Add a test to the catalog</SelectItem>}</SelectContent></Select></Field>{mode === "test" ? <><Field label="Test name"><Input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Code"><Input required value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></Field><Field label="Price (INR)"><Input type="number" min="0" step="0.01" value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} /></Field></div></> : <><Field label="Open encounter"><Select required value={form.encounter_id} onValueChange={(encounter_id) => setForm({ ...form, encounter_id })}><SelectTrigger><SelectValue placeholder="Choose encounter" /></SelectTrigger><SelectContent>{encounters.filter((row) => row.status === "open").map((row) => <SelectItem key={row.id} value={row.id}>{row.patient?.display_name || "Patient"} · {row.chief_complaint || "Consultation"}</SelectItem>)}</SelectContent></Select></Field><Field label="Test"><Select required value={form.test_id} onValueChange={(test_id) => setForm({ ...form, test_id })}><SelectTrigger><SelectValue placeholder="Choose test" /></SelectTrigger><SelectContent>{tests.map((test) => <SelectItem key={test.id} value={test.id}>{test.name} · {test.code}</SelectItem>)}</SelectContent></Select></Field></>}<Button disabled={testState.isLoading || orderState.isLoading} className="w-full">{testState.isLoading || orderState.isLoading ? "Saving..." : "Save lab work"}</Button></form></DrawerForm>;
}

function LabDrawer({ open, onOpenChange, encounters, tests, canManage, canWrite }) {
  const [mode, setMode] = useState(canWrite ? "order" : "test");
  const [createTest, testState] = useCreateLabTestMutation();
  const [createOrder, orderState] = useCreateLabOrderMutation();
  const testApi = useForm({ resolver: zodResolver(labTestSchema), defaultValues: { name: "", code: "", price: "" }, ...FORM_OPTIONS });
  const orderApi = useForm({ resolver: zodResolver(labOrderSchema), defaultValues: { encounter_id: "", test_id: "" }, ...FORM_OPTIONS });
  const encounterId = orderApi.watch("encounter_id");
  const testId = orderApi.watch("test_id");
  const submitTest = testApi.handleSubmit(async (values) => {
    testApi.clearErrors("root.server");
    try {
      await createTest(values).unwrap();
      toast.success("Lab test added");
      testApi.reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, testApi.setError, { fallback: "Lab test could not be saved" });
      toast.error(normalized.message);
    }
  });
  const submitOrder = orderApi.handleSubmit(async (values) => {
    orderApi.clearErrors("root.server");
    try {
      await createOrder(values).unwrap();
      toast.success("Lab order created");
      orderApi.reset();
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, orderApi.setError, { fallback: "Lab order could not be saved" });
      toast.error(normalized.message);
    }
  });
  const busy = testState.isLoading || orderState.isLoading || testApi.formState.isSubmitting || orderApi.formState.isSubmitting;
  const close = (next) => { if (!next && busy) return; onOpenChange(next); };
  return <DrawerForm open={open} onOpenChange={close} title="New lab work" description="Catalog administration and Patient orders remain separate clinical actions."><form noValidate onSubmit={mode === "test" ? submitTest : submitOrder} className="space-y-5"><Field label="Action"><Select value={mode} onValueChange={setMode} disabled={busy}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{canWrite && <SelectItem value="order">Order a Patient test</SelectItem>}{canManage && <SelectItem value="test">Add a test to the catalog</SelectItem>}</SelectContent></Select></Field>{mode === "test" ? <><Field label="Test name" error={testApi.formState.errors.name}><Input {...testApi.register("name")} aria-invalid={Boolean(testApi.formState.errors.name)} /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Code" error={testApi.formState.errors.code}><Input {...testApi.register("code")} aria-invalid={Boolean(testApi.formState.errors.code)} /></Field><Field label="Price (INR)" error={testApi.formState.errors.price}><Input inputMode="decimal" {...testApi.register("price")} aria-invalid={Boolean(testApi.formState.errors.price)} /></Field></div><FormRootError error={testApi.formState.errors.root?.server} /></> : <><Field label="Open encounter" error={orderApi.formState.errors.encounter_id}><Select value={encounterId} onValueChange={(value) => orderApi.setValue("encounter_id", value, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(orderApi.formState.errors.encounter_id)}><SelectValue placeholder="Choose encounter" /></SelectTrigger><SelectContent>{encounters.filter((row) => row.status === "open").map((row) => <SelectItem key={row.id} value={row.id}>{row.patient?.display_name || "Patient"} / {row.chief_complaint || "Consultation"}</SelectItem>)}</SelectContent></Select></Field><Field label="Test" error={orderApi.formState.errors.test_id}><Select value={testId} onValueChange={(value) => orderApi.setValue("test_id", value, { shouldDirty: true, shouldValidate: true })}><SelectTrigger aria-invalid={Boolean(orderApi.formState.errors.test_id)}><SelectValue placeholder="Choose test" /></SelectTrigger><SelectContent>{tests.map((test) => <SelectItem key={test.id} value={test.id}>{test.name} / {test.code}</SelectItem>)}</SelectContent></Select></Field><FormRootError error={orderApi.formState.errors.root?.server} /></>}<Button type="submit" loading={busy} loadingText="Saving lab work..." className="w-full">Save lab work</Button></form></DrawerForm>;
}


function LegacyDispenseDrawer({ prescription, onOpenChange, locationId, levels }) {
  const eligible = useMemo(() => prescription?.items.filter((item) => item.medicine_item_id) || [], [prescription]);
  const [quantities, setQuantities] = useState({});
  const [dispense, state] = useDispensePrescriptionMutation();
  const rows = eligible.map((item) => ({ item, stock: levels.find((level) => level.item_id === item.medicine_item_id && level.quantity_milli > 0) }));
  const submit = async (event) => { event.preventDefault(); const items = rows.map(({ item, stock }) => ({ prescription_item_id: item.id, quantity_milli: Math.round(Number(quantities[item.id] || 1) * 1000), batch_number: stock?.batch_number || "" })); try { await dispense({ location_id: locationId, prescription_id: prescription.id, items }).unwrap(); toast.success("Prescription dispensed and stock updated"); setQuantities({}); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Prescription could not be dispensed"); } };
  return <DrawerForm open={Boolean(prescription)} onOpenChange={onOpenChange} title="Dispense prescription" description={prescription ? `${prescription.patient?.display_name || "Patient"} · signed medication order` : ""}><form onSubmit={submit} className="space-y-4">{rows.map(({ item, stock }) => <Surface key={item.id} className="p-4"><div className="font-semibold">{item.medicine_name}</div><div className="mt-1 text-xs text-muted-foreground">{item.dosage} · {item.frequency} · {item.duration}</div>{stock ? <div className="mt-4 grid grid-cols-2 gap-3"><Field label={`Quantity (${stock.item.unit})`}><Input required type="number" min="0.001" step="0.001" max={stock.quantity_milli / 1000} value={quantities[item.id] || "1"} onChange={(event) => setQuantities({ ...quantities, [item.id]: event.target.value })} /></Field><div><div className="text-xs text-muted-foreground">Batch</div><div className="mt-2 font-mono text-sm">{stock.batch_number || "Default"}</div><div className="mt-1 text-xs text-muted-foreground">{stock.quantity_milli / 1000} available</div></div></div> : <div className="mt-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">No available linked stock for this medicine.</div>}</Surface>)}{!eligible.length && <EmptyState compact icon={Pill} title="No inventory-linked medicine" description="This prescription must be reviewed before it can be dispensed from stock." />}<Button disabled={state.isLoading || !rows.length || rows.some((row) => !row.stock)} className="w-full">{state.isLoading ? "Dispensing..." : "Confirm dispensing"}</Button></form></DrawerForm>;
}

function DispenseDrawer({ prescription, onOpenChange, locationId, levels }) {
  const eligible = useMemo(() => prescription?.items.filter((item) => item.medicine_item_id) || [], [prescription]);
  const rows = eligible.map((item) => ({ item, stock: levels.find((level) => level.item_id === item.medicine_item_id && level.quantity_milli > 0) }));
  const [dispense, state] = useDispensePrescriptionMutation();
  const formApi = useForm({ resolver: zodResolver(dispenseSchema), defaultValues: { items: [] }, ...FORM_OPTIONS });
  const { clearErrors, formState, handleSubmit, register, reset, setError } = formApi;
  useEffect(() => {
    reset({ items: rows.map(({ item, stock }) => ({ prescription_item_id: item.id, quantity: "1", available: stock ? stock.quantity_milli / 1000 : 0, batch_number: stock?.batch_number || "" })) });
  }, [prescription?.id, levels]);
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await dispense({ location_id: locationId, prescription_id: prescription.id, items: values.items }).unwrap();
      toast.success("Prescription dispensed and stock updated");
      reset({ items: [] });
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Prescription could not be dispensed" });
      toast.error(normalized.message);
    }
  });
  const busy = formState.isSubmitting || state.isLoading;
  const close = (next) => { if (!next && busy) return; onOpenChange(next); };
  return <DrawerForm open={Boolean(prescription)} onOpenChange={close} title="Dispense prescription" description={prescription ? `${prescription.patient?.display_name || "Patient"} / signed medication order` : ""}><form noValidate onSubmit={submit} className="space-y-4">{rows.map(({ item, stock }, index) => <Surface key={item.id} className="p-4"><div className="font-semibold">{item.medicine_name}</div><div className="mt-1 text-xs text-muted-foreground">{item.dosage} / {item.frequency} / {item.duration}</div>{stock ? <div className="mt-4 grid grid-cols-2 gap-3"><Field label={`Quantity (${stock.item.unit})`} error={formState.errors.items?.[index]?.quantity}><Input inputMode="decimal" {...register(`items.${index}.quantity`)} aria-invalid={Boolean(formState.errors.items?.[index]?.quantity)} /></Field><div><div className="text-xs text-muted-foreground">Batch</div><div className="mt-2 font-mono text-sm">{stock.batch_number || "Default"}</div><div className="mt-1 text-xs text-muted-foreground">{stock.quantity_milli / 1000} available</div></div></div> : <div className="mt-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">No available linked stock for this medicine.</div>}</Surface>)}{!eligible.length && <EmptyState compact icon={Pill} title="No inventory-linked medicine" description="This prescription must be reviewed before it can be dispensed from stock." />}<FormRootError error={formState.errors.root?.server || formState.errors.items?.root} /><Button type="submit" loading={busy} loadingText="Dispensing..." disabled={!rows.length || rows.some((row) => !row.stock)} className="w-full">Confirm dispensing</Button></form></DrawerForm>;
}


function Destination({ icon: Icon, title, description, action }) { return <Surface className="p-5"><div className="state-icon"><Icon size={24} /></div><h3 className="mt-4 font-display text-xl font-semibold">{title}</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>{action && <div className="mt-5">{action}</div>}</Surface>; }
function Field({ label, children, error }) { return <div className="space-y-2"><Label>{label}</Label>{children}<FieldError error={error} /></div>; }
function dateTime(value, options = {}) { if (!value) return "Not recorded"; return new Intl.DateTimeFormat("en-IN", options.timeOnly ? { hour: "numeric", minute: "2-digit" } : { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)); }
function dateOnly(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`)) : "Not set"; }
