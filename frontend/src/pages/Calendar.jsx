import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CalendarBlank, CaretLeft, CaretRight, Clock, MagnifyingGlass, Plus, UserCircle } from "@phosphor-icons/react";
import { toast } from "sonner";
import {
  DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip, PageHeader,
  PageShell, RemoteCombobox, StatusBadge, Surface,
} from "@/components/system";
import { clientLabel } from "@/app/routeManifest";
import { useGetAppointmentsWindowQuery, useGetClientDirectoryQuery } from "@/store/api/workspaceApi";
import { useGetCatalogDirectoryQuery } from "@/features/catalog/catalogApi";
import { useGetTeamDirectoryQuery } from "@/features/team/teamApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { useCreateAppointmentMutation, useRescheduleAppointmentMutation, useUpdateAppointmentStatusMutation } from "@/features/scheduling/schedulingApi";
import { cn } from "@/lib/utils";
import useCursorPagination from "@/hooks/useCursorPagination";
import { applyApiErrors, appointmentSchema, FORM_OPTIONS } from "@/lib/validation";

const activeStatuses = ["scheduled", "confirmed", "checked_in", "in_progress"];

export default function CalendarPage() {
  const { can } = useAuth();
  const { locationId, organization } = useBusiness();
  const isCollege = organization?.industry === "college";
  const timezone = organization?.timezone || "Asia/Kolkata";
  const entityName = clientLabel(organization?.industry, false);
  const [day, setDay] = useState(() => todayKey(timezone));
  const [view, setView] = useState("week");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.toLowerCase());
  const [employeeFilter, setEmployeeFilter] = useState("all");
  const [serviceFilter, setServiceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("active");
  const [createOpen, setCreateOpen] = useState(() => new URLSearchParams(window.location.search).get("new") === "1");
  const [selected, setSelected] = useState(null);
  const appointmentsQuery = useGetAppointmentsWindowQuery({ locationId, day }, withSkip(QUERY_POLICIES.live, !locationId));
  const [createAppointment, createState] = useCreateAppointmentMutation();
  const [updateStatus, statusState] = useUpdateAppointmentStatusMutation();
  const [reschedule, rescheduleState] = useRescheduleAppointmentMutation();
  const appointments = useMemo(() => appointmentsQuery.data || [], [appointmentsQuery.data]);
  const clients = useMemo(() => uniqueReferences(appointments, "client"), [appointments]);
  const employees = useMemo(() => uniqueReferences(appointments, "employee"), [appointments]);
  const services = useMemo(() => uniqueReferences(appointments, "service"), [appointments]);
  const clientsById = useMemo(() => new Map(clients.map((row) => [row.id, row])), [clients]);
  const employeesById = useMemo(() => new Map(employees.map((row) => [row.id, row])), [employees]);
  const servicesById = useMemo(() => new Map(services.map((row) => [row.id, row])), [services]);

  const filtered = useMemo(() => appointments.filter((row) => {
    const client = clientsById.get(row.client_id);
    const employee = employeesById.get(row.employee_id);
    const service = servicesById.get(row.service_id);
    const text = `${client?.first_name || ""} ${client?.last_name || ""} ${employee?.first_name || ""} ${service?.name || ""}`.toLowerCase();
    return (!deferredSearch || text.includes(deferredSearch))
      && (employeeFilter === "all" || row.employee_id === employeeFilter)
      && (serviceFilter === "all" || row.service_id === serviceFilter)
      && (statusFilter === "all" || (statusFilter === "active" ? activeStatuses.includes(row.status) : row.status === statusFilter));
  }), [appointments, clientsById, deferredSearch, employeeFilter, employeesById, serviceFilter, servicesById, statusFilter]);
  const selectedDayRows = filtered.filter((row) => dateKey(row.starts_at, timezone) === day);
  const week = weekDates(day);
  const today = todayKey(timezone);

  if (appointmentsQuery.isError && !appointmentsQuery.data) return <PageShell><ErrorState title="Calendar could not be loaded" description={appointmentsQuery.error?.data?.detail} retry={appointmentsQuery.refetch} /></PageShell>;

  const metrics = appointmentsQuery.data ? [
    { id: "today", label: isCollege ? "Meetings today" : "Today", value: filtered.filter((row) => dateKey(row.starts_at, timezone) === today && !["cancelled", "no_show"].includes(row.status)).length },
    { id: "waiting", label: isCollege ? "Students arrived" : "Checked in", value: filtered.filter((row) => row.status === "checked_in").length },
    { id: "unassigned", label: "Unassigned", value: filtered.filter((row) => !row.employee_id && activeStatuses.includes(row.status)).length, tone: "warning" },
    { id: "completion", label: isCollege ? "Completed meetings" : "Completed in view", value: filtered.filter((row) => row.status === "completed").length },
  ] : [];

  const moveStatus = async (row, status) => {
    try { const updated = await updateStatus({ appointmentId: row.id, status, version: row.version }).unwrap(); setSelected((current) => current?.id === row.id ? updated : current); toast.success(`${isCollege ? "Student meeting" : "Appointment"} marked ${status.replaceAll("_", " ")}`); }
    catch (error) { toast.error(error?.data?.detail || `Could not update ${isCollege ? "student meeting" : "appointment"}`); }
  };
  const moveToDay = async (row, targetDay) => {
    if (!can("appointments.manage") || ["completed", "cancelled", "no_show"].includes(row.status) || dateKey(row.starts_at, timezone) === targetDay) return;
    const startLocal = toLocalInput(new Date(row.starts_at), timezone);
    const targetStart = zonedLocalToDate(`${targetDay}${startLocal.slice(10)}`, timezone);
    const targetEnd = new Date(targetStart.getTime() + (new Date(row.ends_at).getTime() - new Date(row.starts_at).getTime()));
    try {
      await reschedule({ appointmentId: row.id, version: row.version, starts_at: targetStart.toISOString(), ends_at: targetEnd.toISOString(), employee_id: row.employee_id, service_id: row.service_id, location_id: row.location_id, notes: row.notes }).unwrap();
      toast.success(isCollege ? "Student meeting rescheduled" : "Appointment rescheduled");
    } catch (error) { toast.error(error?.data?.detail || `Could not reschedule ${isCollege ? "student meeting" : "appointment"}`); }
  };

  const agendaColumns = [
    { key: "time", label: "When", render: (row) => <div><div className="font-semibold">{formatDay(row.starts_at, timezone)}</div><div className="mt-1 text-xs text-muted-foreground">{formatTime(row.starts_at, timezone)}–{formatTime(row.ends_at, timezone)}</div></div> },
    { key: "client", label: entityName, render: (row) => fullName(clientsById.get(row.client_id)) || entityName },
    { key: "service", label: isCollege ? "Purpose" : "Service", render: (row) => servicesById.get(row.service_id)?.name || (isCollege ? "Student support" : "General appointment") },
    { key: "employee", label: isCollege ? "Faculty / coordinator" : "Assigned to", render: (row) => fullName(employeesById.get(row.employee_id)) || "Unassigned" },
    { key: "status", label: "State", render: (row) => <StatusBadge status={row.status} /> },
  ];

  return <PageShell className="reveal">
    <PageHeader eyebrow={isCollege ? "Student support" : "Schedule and availability"} title={isCollege ? "Student schedule" : "Calendar"} description={isCollege ? "Coordinate counselling, placement preparation, interviews, and student support without scheduling conflicts." : `Day, week, and agenda views for ${entityName.toLowerCase()} appointments, walk-ins, staff availability, and conflict-safe scheduling.`} actions={can("appointments.manage") && <Button onClick={() => setCreateOpen(true)}><Plus className="mr-2" />{isCollege ? "Schedule student meeting" : organization?.industry === "salon" ? "Book or add walk-in" : "Book appointment"}</Button>} />
    <MetricStrip metrics={metrics} loading={appointmentsQuery.isLoading && !appointmentsQuery.data} />
    <Surface className="p-3"><div className="flex flex-col gap-3 xl:flex-row xl:items-center"><div className="flex items-center gap-1"><Button variant="ghost" size="icon" onClick={() => setDay(addDays(day, view === "week" ? -7 : -1))} aria-label="Previous period"><CaretLeft /></Button><Input type="date" className="w-40" value={day} onChange={(event) => setDay(event.target.value)} /><Button variant="ghost" size="icon" onClick={() => setDay(addDays(day, view === "week" ? 7 : 1))} aria-label="Next period"><CaretRight /></Button><Button variant="ghost" onClick={() => setDay(today)}>Today</Button></div><div className="flex rounded-xl bg-secondary p-1">{["day", "week", "agenda"].map((value) => <button key={value} onClick={() => setView(value)} className={cn("rounded-lg px-3 py-1.5 text-sm capitalize", view === value && "bg-card shadow-sm")}>{value}</button>)}</div><div className="relative min-w-0 flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder={isCollege ? "Search student or faculty member" : `Search ${entityName.toLowerCase()}, staff, or service`} /></div></div></Surface>
    <FilterBar><Select value={employeeFilter} onValueChange={setEmployeeFilter}><SelectTrigger className="w-full sm:w-52"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{isCollege ? "All faculty & coordinators" : "All staff"}</SelectItem>{employees.map((row) => <SelectItem key={row.id} value={row.id}>{fullName(row)}</SelectItem>)}</SelectContent></Select>{!isCollege && <Select value={serviceFilter} onValueChange={setServiceFilter}><SelectTrigger className="w-full sm:w-52"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All services</SelectItem>{services.map((row) => <SelectItem key={row.id} value={row.id}>{row.name}</SelectItem>)}</SelectContent></Select>}<Select value={statusFilter} onValueChange={setStatusFilter}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">{isCollege ? "Upcoming & active" : "Active work"}</SelectItem><SelectItem value="all">All states</SelectItem>{["scheduled", "confirmed", "checked_in", "in_progress", "completed", "cancelled", "no_show"].map((value) => <SelectItem key={value} value={value}>{value.replaceAll("_", " ")}</SelectItem>)}</SelectContent></Select></FilterBar>

    {view === "week" ? <WeekView isCollege={isCollege} entityName={entityName} dates={week} rows={filtered} timezone={timezone} loading={appointmentsQuery.isLoading} references={{ clientsById, employeesById, servicesById }} onOpen={setSelected} onDrop={moveToDay} canManage={can("appointments.manage")} /> : view === "day" ? <DayView isCollege={isCollege} entityName={entityName} day={day} rows={selectedDayRows} timezone={timezone} loading={appointmentsQuery.isLoading} references={{ clientsById, employeesById, servicesById }} onOpen={setSelected} onCreate={can("appointments.manage") ? () => setCreateOpen(true) : null} /> : <DataTable loading={appointmentsQuery.isLoading} rows={filtered} columns={agendaColumns} onRowClick={setSelected} empty={<CalendarEmpty isCollege={isCollege} onCreate={can("appointments.manage") ? () => setCreateOpen(true) : null} />} />}

    <DrawerForm open={createOpen} onOpenChange={(nextOpen) => { if (!nextOpen && createState.isLoading) return; setCreateOpen(nextOpen); }} title={isCollege ? "Schedule student meeting" : organization?.industry === "salon" ? "Book or add walk-in" : "Book appointment"} description={isCollege ? "Choose the student, responsible faculty member, and time. Conflicts are checked before saving." : "Availability and overlapping staff appointments are checked before saving."}><AppointmentForm open={createOpen} locationId={locationId} timezone={timezone} isCollege={isCollege} entityName={entityName} createAppointment={createAppointment} saving={createState.isLoading} onCreated={() => setCreateOpen(false)} /></DrawerForm>
    <AppointmentDrawer isCollege={isCollege} row={selected} onClose={() => setSelected(null)} timezone={timezone} references={{ clientsById, employeesById, servicesById }} canManage={can("appointments.manage")} onStatus={moveStatus} saving={statusState.isLoading || rescheduleState.isLoading} />
  </PageShell>;
}

function WeekView({ isCollege, entityName, dates, rows, timezone, loading, references, onOpen, onDrop, canManage }) {
  if (loading) return <div className="h-96 animate-pulse rounded-3xl bg-secondary" />;
  return <div className="premium-scrollbar overflow-x-auto"><div className="grid min-w-[980px] grid-cols-7 gap-2">{dates.map((date) => { const items = rows.filter((row) => dateKey(row.starts_at, timezone) === date); return <Surface key={date} className="min-h-[28rem] overflow-hidden" onDragOver={(event) => canManage && event.preventDefault()} onDrop={(event) => { const id = event.dataTransfer.getData("text/appointment"); const row = rows.find((item) => item.id === id); if (row) onDrop(row, date); }}><div className={cn("border-b p-3 text-center", date === todayKey(timezone) && "bg-accent/10")}><div className="text-xs text-muted-foreground">{new Intl.DateTimeFormat("en-IN", { weekday: "short" }).format(new Date(`${date}T12:00:00`))}</div><div className="mt-1 font-display text-xl">{Number(date.slice(-2))}</div></div><div className="space-y-2 p-2">{items.map((row) => <AppointmentCard isCollege={isCollege} entityName={entityName} compact key={row.id} row={row} timezone={timezone} references={references} onOpen={onOpen} draggable={canManage && activeStatuses.includes(row.status)} />)}{!items.length && <div className="py-12 text-center text-xs text-muted-foreground">Open</div>}</div></Surface>; })}</div></div>;
}

function DayView({ isCollege, entityName, rows, timezone, loading, references, onOpen, onCreate }) {
  if (loading) return <div className="h-96 animate-pulse rounded-3xl bg-secondary" />;
  if (!rows.length) return <CalendarEmpty isCollege={isCollege} onCreate={onCreate} />;
  return <div className="grid gap-3 lg:grid-cols-2">{rows.map((row) => <AppointmentCard isCollege={isCollege} entityName={entityName} key={row.id} row={row} timezone={timezone} references={references} onOpen={onOpen} />)}</div>;
}

function AppointmentCard({ isCollege, entityName, row, timezone, references, onOpen, compact = false, draggable = false }) {
  const client = references.clientsById.get(row.client_id);
  const employee = references.employeesById.get(row.employee_id);
  const service = references.servicesById.get(row.service_id);
  return <button type="button" draggable={draggable} onDragStart={(event) => event.dataTransfer.setData("text/appointment", row.id)} onClick={() => onOpen(row)} className={cn("w-full rounded-2xl border bg-card p-4 text-left transition hover:border-accent focus-visible:ring-2 focus-visible:ring-ring", compact && "rounded-xl p-3")}><div className="flex items-start justify-between gap-2"><span className="font-semibold leading-tight">{fullName(client) || entityName}</span><StatusBadge status={row.status} className="shrink-0" /></div><div className="mt-2 text-xs text-muted-foreground">{formatTime(row.starts_at, timezone)} · {service?.name || (isCollege ? "Student support" : "General appointment")}</div>{!compact && <div className="mt-4 flex items-center gap-2 border-t pt-3 text-xs text-muted-foreground"><UserCircle />{fullName(employee) || "Unassigned"}</div>}</button>;
}

function AppointmentForm({ open, locationId, timezone, isCollege, entityName, createAppointment, saving, onCreated }) {
  const [clientSearch, setClientSearch] = useState("");
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [serviceSearch, setServiceSearch] = useState("");
  const clientQuery = useDeferredValue(clientSearch.trim());
  const employeeQuery = useDeferredValue(employeeSearch.trim());
  const serviceQuery = useDeferredValue(serviceSearch.trim());
  const [selectedClient, setSelectedClient] = useState(null);
  const [selectedEmployee, setSelectedEmployee] = useState(NONE_EMPLOYEE);
  const [selectedService, setSelectedService] = useState(NONE_SERVICE);
  const appointmentForm = useForm({ resolver: zodResolver(appointmentSchema), defaultValues: newAppointment(locationId, timezone), ...FORM_OPTIONS });
  const { clearErrors, control, formState, getValues, handleSubmit, reset, setError, setValue, watch } = appointmentForm;
  const clientId = watch("client_id");
  const employeeId = watch("employee_id");
  const serviceId = watch("service_id");
  const clientPaging = useCursorPagination(JSON.stringify({ open, locationId, q: clientQuery }));
  const employeePaging = useCursorPagination(JSON.stringify({ open, locationId, q: employeeQuery }));
  const servicePaging = useCursorPagination(JSON.stringify({ open, q: serviceQuery }));
  const clientsResponse = useGetClientDirectoryQuery({ locationId, q: clientQuery, segment: "active", cursor: clientPaging.cursor, limit: 25 }, withSkip(QUERY_POLICIES.reference, !open || !locationId));
  const employeesResponse = useGetTeamDirectoryQuery({ locationId, q: employeeQuery, status: "active", cursor: employeePaging.cursor, limit: 25 }, withSkip(QUERY_POLICIES.reference, !open || !locationId));
  const servicesResponse = useGetCatalogDirectoryQuery({ q: serviceQuery, itemType: "service", state: "active", cursor: servicePaging.cursor, limit: 25 }, withSkip(QUERY_POLICIES.reference, !open || isCollege));
  const { accept: acceptClients } = clientPaging;
  const { accept: acceptEmployees } = employeePaging;
  const { accept: acceptServices } = servicePaging;
  useEffect(() => { acceptClients(clientsResponse.data); }, [acceptClients, clientsResponse.data]);
  useEffect(() => { acceptEmployees(employeesResponse.data); }, [acceptEmployees, employeesResponse.data]);
  useEffect(() => { acceptServices(servicesResponse.data); }, [acceptServices, servicesResponse.data]);
  useEffect(() => {
    if (!open) return;
    reset(newAppointment(locationId, timezone));
    setSelectedClient(null);
    setSelectedEmployee(NONE_EMPLOYEE);
    setSelectedService(NONE_SERVICE);
  }, [locationId, open, reset, timezone]);
  useEffect(() => { if (!clientId) setSelectedClient(null); }, [clientId]);
  useEffect(() => { if (employeeId === "none") setSelectedEmployee(NONE_EMPLOYEE); }, [employeeId]);
  useEffect(() => { if (serviceId === "none") setSelectedService(NONE_SERVICE); }, [serviceId]);
  const clients = clientPaging.items.length ? clientPaging.items : clientsResponse.data?.items || [];
  const employees = employeePaging.items.length ? employeePaging.items : employeesResponse.data?.items || [];
  const services = servicePaging.items.length ? servicePaging.items : servicesResponse.data?.items || [];

  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await createAppointment({
        location_id: values.location_id,
        client_id: values.client_id,
        employee_id: values.employee_id === "none" ? null : values.employee_id,
        service_id: values.service_id === "none" ? null : values.service_id,
        starts_at: zonedLocalToDate(values.starts_at, timezone).toISOString(),
        ends_at: zonedLocalToDate(values.ends_at, timezone).toISOString(),
        source: values.source,
        notes: values.notes || null,
      }).unwrap();
      toast.success(isCollege ? "Student meeting scheduled" : values.source === "walk_in" ? "Walk-in added" : "Appointment scheduled");
      reset(newAppointment(locationId, timezone));
      onCreated();
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: isCollege ? "Could not schedule student meeting" : "Could not schedule appointment" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });

  const chooseService = (value, item) => {
    setSelectedService(item);
    setValue("service_id", value, { shouldDirty: true, shouldValidate: true });
    const startsAt = getValues("starts_at");
    if (!startsAt) return;
    const start = zonedLocalToDate(startsAt, timezone);
    const end = new Date(start.getTime() + (item?.duration_minutes || 30) * 60000);
    setValue("ends_at", toLocalInput(end, timezone), { shouldDirty: true, shouldValidate: true });
  };

  return <Form {...appointmentForm}><form noValidate onSubmit={submit} className="space-y-5">
    <FormField control={control} name="client_id" render={({ field }) => <FormItem><FormLabel>{entityName}</FormLabel><RemoteCombobox value={field.value} selectedItem={selectedClient} items={clients} onValueChange={(value, item) => { field.onChange(value); setSelectedClient(item); }} onSearchChange={setClientSearch} getLabel={(row) => row.display_name || fullName(row)} getDescription={(row) => isCollege ? row.admission_number || row.client_number : row.phone || row.client_number} placeholder={`Select ${entityName.toLowerCase()}`} searchPlaceholder={`Search ${entityName.toLowerCase()} name or number`} loading={clientsResponse.isFetching} error={clientsResponse.isError} hasMore={Boolean(clientsResponse.data?.has_more)} onLoadMore={() => clientPaging.loadMore(clientsResponse.data?.next_cursor)} onRetry={clientsResponse.refetch} /><FormMessage /></FormItem>} />
    <div className="grid gap-4 sm:grid-cols-2">
      {!isCollege && <FormField control={control} name="service_id" render={({ field }) => <FormItem><FormLabel>Service</FormLabel><RemoteCombobox value={field.value} selectedItem={selectedService} items={[NONE_SERVICE, ...services]} onValueChange={chooseService} onSearchChange={setServiceSearch} getLabel={(row) => row.name} getDescription={(row) => row.id === "none" ? "No catalog service" : `${money(row.price_paise)} · ${row.duration_minutes || 30} min`} placeholder="Choose service" searchPlaceholder="Search service name" loading={servicesResponse.isFetching} error={servicesResponse.isError} hasMore={Boolean(servicesResponse.data?.has_more)} onLoadMore={() => servicePaging.loadMore(servicesResponse.data?.next_cursor)} onRetry={servicesResponse.refetch} /><FormMessage /></FormItem>} />}
      <FormField control={control} name="employee_id" render={({ field }) => <FormItem><FormLabel>{isCollege ? "Faculty / placement coordinator" : "Assigned staff"}</FormLabel><RemoteCombobox value={field.value} selectedItem={selectedEmployee} items={[NONE_EMPLOYEE, ...employees]} onValueChange={(value, item) => { field.onChange(value); setSelectedEmployee(item); }} onSearchChange={setEmployeeSearch} getLabel={(row) => row.id === "none" ? "Unassigned" : fullName(row)} getDescription={(row) => row.id === "none" ? "Assign later" : row.designation} placeholder="Choose team member" searchPlaceholder="Search team member" loading={employeesResponse.isFetching} error={employeesResponse.isError} hasMore={Boolean(employeesResponse.data?.has_more)} onLoadMore={() => employeePaging.loadMore(employeesResponse.data?.next_cursor)} onRetry={employeesResponse.refetch} /><FormMessage /></FormItem>} />
    </div>
    <div className="grid gap-4 sm:grid-cols-2"><ValidatedCalendarField control={control} name="starts_at" label="Starts"><Input type="datetime-local" /></ValidatedCalendarField><ValidatedCalendarField control={control} name="ends_at" label="Ends"><Input type="datetime-local" /></ValidatedCalendarField></div>
    <div className="grid gap-4 sm:grid-cols-2">{!isCollege && <FormField control={control} name="source" render={({ field }) => <FormItem><FormLabel>Booking type</FormLabel><Select value={field.value} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl><SelectContent><SelectItem value="staff">Scheduled booking</SelectItem><SelectItem value="walk_in">Walk-in</SelectItem><SelectItem value="phone">Phone booking</SelectItem></SelectContent></Select><FormMessage /></FormItem>} />}<ValidatedCalendarField control={control} name="notes" label={isCollege ? "Meeting purpose / notes" : "Notes"}><Input placeholder={isCollege ? "Placement counselling, resume review, interview preparation..." : undefined} /></ValidatedCalendarField></div>
    <FormRootError error={formState.errors.root?.server} />
    <Button type="submit" loading={formState.isSubmitting || saving} loadingText="Checking availability..." className="h-12 w-full">{isCollege ? "Schedule meeting" : "Save appointment"}</Button>
  </form></Form>;
}

function ValidatedCalendarField({ control, name, label, children }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />;
}

function LegacyAppointmentForm({ open, locationId, isCollege, entityName, form, setForm, serviceChanged, submit, saving }) {
  const [clientSearch, setClientSearch] = useState("");
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [serviceSearch, setServiceSearch] = useState("");
  const clientQuery = useDeferredValue(clientSearch.trim());
  const employeeQuery = useDeferredValue(employeeSearch.trim());
  const serviceQuery = useDeferredValue(serviceSearch.trim());
  const [selectedClient, setSelectedClient] = useState(null);
  const [selectedEmployee, setSelectedEmployee] = useState(NONE_EMPLOYEE);
  const [selectedService, setSelectedService] = useState(NONE_SERVICE);
  const clientPaging = useCursorPagination(JSON.stringify({ open, locationId, q: clientQuery }));
  const employeePaging = useCursorPagination(JSON.stringify({ open, locationId, q: employeeQuery }));
  const servicePaging = useCursorPagination(JSON.stringify({ open, q: serviceQuery }));
  const clientsResponse = useGetClientDirectoryQuery({
    locationId,
    q: clientQuery,
    segment: "active",
    cursor: clientPaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.reference, !open || !locationId));
  const employeesResponse = useGetTeamDirectoryQuery({
    locationId,
    q: employeeQuery,
    status: "active",
    cursor: employeePaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.reference, !open || !locationId));
  const servicesResponse = useGetCatalogDirectoryQuery({
    q: serviceQuery,
    itemType: "service",
    state: "active",
    cursor: servicePaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.reference, !open || isCollege));
  const { accept: acceptClients } = clientPaging;
  const { accept: acceptEmployees } = employeePaging;
  const { accept: acceptServices } = servicePaging;
  useEffect(() => { acceptClients(clientsResponse.data); }, [acceptClients, clientsResponse.data]);
  useEffect(() => { acceptEmployees(employeesResponse.data); }, [acceptEmployees, employeesResponse.data]);
  useEffect(() => { acceptServices(servicesResponse.data); }, [acceptServices, servicesResponse.data]);
  useEffect(() => { if (!form.client_id) setSelectedClient(null); }, [form.client_id]);
  useEffect(() => { if (form.employee_id === "none") setSelectedEmployee(NONE_EMPLOYEE); }, [form.employee_id]);
  useEffect(() => { if (form.service_id === "none") setSelectedService(NONE_SERVICE); }, [form.service_id]);
  const clients = clientPaging.items.length ? clientPaging.items : clientsResponse.data?.items || [];
  const employees = employeePaging.items.length ? employeePaging.items : employeesResponse.data?.items || [];
  const services = servicePaging.items.length ? servicePaging.items : servicesResponse.data?.items || [];

  return <form onSubmit={submit} className="space-y-5">
    <Field label={entityName}><RemoteCombobox
      value={form.client_id}
      selectedItem={selectedClient}
      items={clients}
      onValueChange={(value, item) => { setForm((current) => ({ ...current, client_id: value })); setSelectedClient(item); }}
      onSearchChange={setClientSearch}
      getLabel={(row) => row.display_name || fullName(row)}
      getDescription={(row) => isCollege ? row.admission_number || row.client_number : row.phone || row.client_number}
      placeholder={`Select ${entityName.toLowerCase()}`}
      searchPlaceholder={`Search ${entityName.toLowerCase()} name or number`}
      loading={clientsResponse.isFetching}
      error={clientsResponse.isError}
      hasMore={Boolean(clientsResponse.data?.has_more)}
      onLoadMore={() => clientPaging.loadMore(clientsResponse.data?.next_cursor)}
      onRetry={clientsResponse.refetch}
    /></Field>
    <div className="grid gap-4 sm:grid-cols-2">
      {!isCollege && <Field label="Service"><RemoteCombobox
        value={form.service_id}
        selectedItem={selectedService}
        items={[NONE_SERVICE, ...services]}
        onValueChange={(value, item) => { setSelectedService(item); serviceChanged(value, item); }}
        onSearchChange={setServiceSearch}
        getLabel={(row) => row.name}
        getDescription={(row) => row.id === "none" ? "No catalog service" : `${money(row.price_paise)} · ${row.duration_minutes || 30} min`}
        placeholder="Choose service"
        searchPlaceholder="Search service name"
        loading={servicesResponse.isFetching}
        error={servicesResponse.isError}
        hasMore={Boolean(servicesResponse.data?.has_more)}
        onLoadMore={() => servicePaging.loadMore(servicesResponse.data?.next_cursor)}
        onRetry={servicesResponse.refetch}
      /></Field>}
      <Field label={isCollege ? "Faculty / placement coordinator" : "Assigned staff"}><RemoteCombobox
        value={form.employee_id}
        selectedItem={selectedEmployee}
        items={[NONE_EMPLOYEE, ...employees]}
        onValueChange={(value, item) => { setForm((current) => ({ ...current, employee_id: value })); setSelectedEmployee(item); }}
        onSearchChange={setEmployeeSearch}
        getLabel={(row) => row.id === "none" ? "Unassigned" : fullName(row)}
        getDescription={(row) => row.id === "none" ? "Assign later" : row.designation}
        placeholder="Choose team member"
        searchPlaceholder="Search team member"
        loading={employeesResponse.isFetching}
        error={employeesResponse.isError}
        hasMore={Boolean(employeesResponse.data?.has_more)}
        onLoadMore={() => employeePaging.loadMore(employeesResponse.data?.next_cursor)}
        onRetry={employeesResponse.refetch}
      /></Field>
    </div>
    <div className="grid gap-4 sm:grid-cols-2"><Field label="Starts"><Input type="datetime-local" required value={form.starts_at} onChange={(event) => setForm((current) => ({ ...current, starts_at: event.target.value }))} /></Field><Field label="Ends"><Input type="datetime-local" required value={form.ends_at} onChange={(event) => setForm((current) => ({ ...current, ends_at: event.target.value }))} /></Field></div>
    <div className="grid gap-4 sm:grid-cols-2">{!isCollege && <Field label="Booking type"><Select value={form.source} onValueChange={(value) => setForm((current) => ({ ...current, source: value }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="staff">Scheduled booking</SelectItem><SelectItem value="walk_in">Walk-in</SelectItem><SelectItem value="phone">Phone booking</SelectItem></SelectContent></Select></Field>}<Field label={isCollege ? "Meeting purpose / notes" : "Notes"}><Input value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} placeholder={isCollege ? "Placement counselling, resume review, interview preparation..." : undefined} /></Field></div>
    <Button disabled={saving || !form.client_id} className="h-12 w-full">{saving ? "Checking availability..." : isCollege ? "Schedule meeting" : "Save appointment"}</Button>
  </form>;
}

function AppointmentDrawer({ isCollege, row, onClose, timezone, references, canManage, onStatus, saving }) {
  const actions = row ? nextActions(row.status) : [];
  return <DrawerForm open={Boolean(row)} onOpenChange={(open) => !open && onClose()} title={row ? fullName(references.clientsById.get(row.client_id)) || (isCollege ? "Student meeting" : "Appointment") : isCollege ? "Student meeting" : "Appointment"} description={row ? `${formatDay(row.starts_at, timezone)} at ${formatTime(row.starts_at, timezone)}` : ""}>{row && <div className="space-y-5"><Surface className="p-5"><div className="flex items-start justify-between gap-3"><div><div className="overline">{isCollege ? "Purpose" : "Service"}</div><div className="mt-2 font-semibold">{references.servicesById.get(row.service_id)?.name || (isCollege ? row.notes || "Student support" : "General appointment")}</div></div><StatusBadge status={row.status} /></div><div className="mt-5 grid grid-cols-2 gap-4 border-t pt-4 text-sm"><div><div className="text-xs text-muted-foreground">{isCollege ? "Faculty / coordinator" : "Assigned to"}</div><div className="mt-1">{fullName(references.employeesById.get(row.employee_id)) || "Unassigned"}</div></div><div><div className="text-xs text-muted-foreground">State</div><div className="mt-1 capitalize">{row.status.replaceAll("_", " ")}</div></div></div>{row.notes && !isCollege && <p className="mt-4 text-sm text-muted-foreground">{row.notes}</p>}</Surface>{canManage && actions.length > 0 && <section><h3 className="font-display text-xl font-semibold">Move work forward</h3><div className="mt-3 flex flex-wrap gap-2">{actions.map((action) => <Button key={action} disabled={saving} variant={action === "completed" ? "default" : "outline"} onClick={() => onStatus(row, action)} className="capitalize">{action.replaceAll("_", " ")}</Button>)}</div></section>}<p className="text-xs text-muted-foreground">Drag this {isCollege ? "meeting" : "appointment"} to another day in Week view to reschedule it at the same time.</p></div>}</DrawerForm>;
}

function CalendarEmpty({ onCreate, isCollege = false }) { return <EmptyState variant="section" alignment="left" icon={CalendarBlank} title={isCollege ? "No student meetings scheduled" : "The calendar is clear"} description={isCollege ? "No student support or placement meetings match this date and filter combination." : "No appointments match this date and filter combination."} action={onCreate && <Button onClick={onCreate}>{isCollege ? "Schedule meeting" : "Book appointment"}</Button>} />; }
function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function nextActions(status) { return ({ scheduled: ["confirmed", "checked_in", "cancelled", "no_show"], confirmed: ["checked_in", "cancelled", "no_show"], checked_in: ["in_progress", "cancelled"], in_progress: ["completed", "cancelled"] }[status] || []); }
function fullName(row) { return row ? `${row.first_name || ""} ${row.last_name || ""}`.trim() : ""; }
function uniqueReferences(rows, key) { return [...new Map(rows.map((row) => row[key]).filter(Boolean).map((row) => [row.id, row])).values()]; }
function money(paise) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(paise || 0) / 100); }
function dateParts(value, timezone) { return Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(value)).filter((part) => part.type !== "literal").map((part) => [part.type, part.value])); }
function dateKey(value, timezone) { const parts = dateParts(value, timezone); return `${parts.year}-${parts.month}-${parts.day}`; }
function todayKey(timezone) { return dateKey(new Date(), timezone); }
function toLocalInput(value, timezone) { const parts = dateParts(value, timezone); return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`; }
function zonedLocalToDate(value, timezone) { const [date, clock] = value.split("T"); const [year, month, day] = date.split("-").map(Number); const [hour, minute] = clock.split(":").map(Number); const guess = Date.UTC(year, month - 1, day, hour, minute); const rendered = dateParts(new Date(guess), timezone); const renderedUtc = Date.UTC(Number(rendered.year), Number(rendered.month) - 1, Number(rendered.day), Number(rendered.hour), Number(rendered.minute)); return new Date(guess - (renderedUtc - guess)); }
function newAppointment(locationId, timezone) { const now = new Date(); now.setMinutes(Math.ceil(now.getMinutes() / 30) * 30, 0, 0); const end = new Date(now.getTime() + 30 * 60000); return { location_id: locationId || "", client_id: "", employee_id: "none", service_id: "none", starts_at: toLocalInput(now, timezone), ends_at: toLocalInput(end, timezone), source: "staff", notes: "" }; }
function addDays(value, amount) { const date = new Date(`${value}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + amount); return date.toISOString().slice(0, 10); }
function weekDates(value) { const date = new Date(`${value}T12:00:00Z`); const offset = (date.getUTCDay() + 6) % 7; date.setUTCDate(date.getUTCDate() - offset); return Array.from({ length: 7 }, (_, index) => addDays(date.toISOString().slice(0, 10), index)); }
function formatTime(value, timezone) { return new Intl.DateTimeFormat("en-IN", { timeZone: timezone, hour: "numeric", minute: "2-digit" }).format(new Date(value)); }
function formatDay(value, timezone) { return new Intl.DateTimeFormat("en-IN", { timeZone: timezone, weekday: "short", day: "numeric", month: "short" }).format(new Date(value)); }

const NONE_EMPLOYEE = { id: "none", first_name: "Unassigned", last_name: "" };
const NONE_SERVICE = { id: "none", name: "General appointment", duration_minutes: 30, price_paise: 0 };
