import React, { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, CalendarBlank, CurrencyInr, IdentificationCard, MapPin,
  NotePencil, ShieldCheck, User,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { EmptyState, PageShell, Surface } from "@/components/system";
import { ProfileBackLink } from "@/components/entities/EntityProfile";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/contexts/AuthContext";
import { useUpdateEmployeeMutation } from "@/features/team/teamApi";
import { applyApiErrors, employeeProfileSchema, FORM_OPTIONS } from "@/lib/validation";
import { useGetEmployeeProfileQuery } from "@/store/api/workspaceApi";
import { QUERY_POLICIES } from "@/store/api/queryPolicies";

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function employeeValues(employee = {}) {
  return {
    first_name: employee.first_name || "",
    last_name: employee.last_name || "",
    phone: employee.phone || "",
    email: employee.email || "",
    designation: employee.designation || "",
    specialties: employee.specialties || [],
    salary: employee.salary_paise == null ? "" : String(employee.salary_paise / 100),
    joining_date: employee.joining_date || "",
    status: employee.status || "active",
    location_ids: employee.location_ids || [],
    version: employee.version || 1,
  };
}

export default function EmployeeProfile() {
  const { employeeId } = useParams();
  const { can } = useAuth();
  const { data, error } = useGetEmployeeProfileQuery(employeeId, QUERY_POLICIES.reference);
  const [editing, setEditing] = useState(false);
  const [updateEmployee, updateState] = useUpdateEmployeeMutation();
  const editForm = useForm({
    resolver: zodResolver(employeeProfileSchema),
    defaultValues: employeeValues(),
    ...FORM_OPTIONS,
  });
  const { clearErrors, control, formState, handleSubmit, register, reset, setError, setValue, watch } = editForm;
  const selectedLocations = watch("location_ids") || [];

  useEffect(() => {
    if (data?.employee && !editing) reset(employeeValues(data.employee));
  }, [data?.employee, editing, reset]);

  const openEditor = () => {
    reset(employeeValues(data.employee));
    setEditing(true);
  };

  const save = handleSubmit(async (values) => {
    clearErrors("root.server");
    const payload = {
      employeeId,
      first_name: values.first_name,
      last_name: values.last_name || "",
      phone: values.phone || null,
      email: values.email || null,
      designation: values.designation || null,
      specialties: values.specialties,
      joining_date: values.joining_date || null,
      status: values.status,
      location_ids: values.location_ids,
      version: values.version,
    };
    if (data.capabilities.view_compensation) payload.salary_paise = values.salary_paise;
    try {
      await updateEmployee(payload).unwrap();
      toast.success("Employee updated");
      setEditing(false);
    } catch (requestError) {
      const normalized = applyApiErrors(requestError, setError, {
        aliases: { salary_paise: "salary" },
        fallback: "Could not update employee",
      });
      if (!Object.keys(normalized.fieldErrors).length) {
        setError("root.server", { type: "server", message: normalized.message });
      }
    }
  });

  if (error) return <PageShell><Empty title={error.status === 403 ? "Access restricted" : "Employee unavailable"} copy={error.data?.detail || "Could not load employee"} /></PageShell>;
  if (!data) return <PageShell><div className="h-72 animate-pulse rounded-2xl bg-secondary" /></PageShell>;

  const employee = data.employee;
  const hasWork = Boolean(data.appointments?.length || data.sales?.length);
  const busy = formState.isSubmitting || updateState.isLoading;

  return <PageShell className="reveal" size="standard">
    <ProfileBackLink fallback="/app/team" className="inline-flex items-center gap-2 text-sm text-muted-foreground"><ArrowLeft />Back</ProfileBackLink>
    <Surface className="flex flex-col justify-between gap-5 p-5 sm:p-6 lg:flex-row lg:items-center">
      <div className="flex min-w-0 gap-4"><div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-primary font-display text-2xl text-primary-foreground sm:h-16 sm:w-16 sm:text-3xl">{employee.first_name[0]}</div><div className="min-w-0"><div className="font-mono text-xs text-muted-foreground">{employee.employee_number}</div><h1 className="mt-1 truncate font-display text-2xl font-semibold sm:text-3xl">{employee.first_name} {employee.last_name}</h1><div className="mt-2 text-sm text-muted-foreground">{employee.designation || "Team member"} / <span className="capitalize">{employee.status}</span></div></div></div>
      {data.capabilities.manage && <Button className="self-start rounded-xl lg:self-auto" onClick={openEditor}><NotePencil className="mr-2" />Edit employee</Button>}
    </Surface>
    {(data.capabilities.view_appointments || data.capabilities.view_sales) && <div className="grid gap-4 sm:grid-cols-3">{data.capabilities.view_appointments && <><Metric icon={CalendarBlank} label="Appointments" value={data.metrics.appointment_count} /><Metric icon={User} label="Completed" value={data.metrics.completed_appointments} /></>}{data.capabilities.view_sales && <Metric icon={CurrencyInr} label="Attributed sales" value={money(data.metrics.sales_paise)} />}</div>}
    <Tabs defaultValue="overview"><TabsList className="premium-scrollbar h-auto max-w-full justify-start overflow-x-auto rounded-xl"><TabsTrigger value="overview">Overview</TabsTrigger>{hasWork && <TabsTrigger value="work">Work history</TabsTrigger>}<TabsTrigger value="schedule">Schedule</TabsTrigger>{data.capabilities.view_account && <TabsTrigger value="access">Login & access</TabsTrigger>}</TabsList>
      <TabsContent value="overview" className="mt-5 grid items-start gap-5 lg:grid-cols-2"><Panel title="Employment"><Detail icon={IdentificationCard} label="Designation" value={employee.designation} /><Detail label="Joined" value={employee.joining_date ? new Date(employee.joining_date).toLocaleDateString("en-IN") : null} />{data.capabilities.view_compensation && <Detail label="Monthly salary" value={employee.salary_paise != null ? money(employee.salary_paise) : "Not set"} />}<div className="mt-4 flex flex-wrap gap-2">{employee.specialties?.map((item) => <span key={item} className="rounded-full bg-secondary px-3 py-1 text-xs">{item}</span>)}</div></Panel><Panel title="Locations">{data.locations.length ? data.locations.map((location) => <div key={location.id} className="flex gap-3 border-b py-3 last:border-0"><MapPin className="text-accent" /><div><div className="font-medium">{location.name}</div><div className="text-xs text-muted-foreground">{location.city || "No city"}{location.is_primary ? " / Primary" : ""}</div></div></div>) : <EmptyState variant="inline" icon={MapPin} title="No locations assigned" description="Assign a location before scheduling work." />}</Panel></TabsContent>
      {hasWork && <TabsContent value="work" className="mt-5 grid items-start gap-5 lg:grid-cols-2">{data.appointments?.length > 0 && <Panel title="Recent appointments">{data.appointments.map((item) => <Row key={item.id} title={item.status} meta={new Date(item.starts_at).toLocaleString("en-IN")} value={item.notes} />)}</Panel>}{data.sales?.length > 0 && <Panel title="Recent sales">{data.sales.map((item) => <Row key={item.id} title={item.invoice_number} meta={new Date(item.created_at).toLocaleDateString("en-IN")} value={money(item.total_paise)} />)}</Panel>}</TabsContent>}
      <TabsContent value="schedule" className="mt-5"><Panel title="Weekly availability">{data.schedules.length ? <div className="grid gap-3 sm:grid-cols-2">{data.schedules.map((item) => <div key={item.id} className="rounded-xl border p-4"><div className="font-medium">{weekdays[item.weekday] || `Day ${item.weekday}`}</div><div className="mt-1 text-sm text-muted-foreground">{item.starts_at.slice(0, 5)} - {item.ends_at.slice(0, 5)}</div></div>)}</div> : <EmptyState variant="inline" icon={CalendarBlank} title="No schedule configured" description="Set availability before assigning appointments." />}</Panel></TabsContent>
      {data.capabilities.view_account && <TabsContent value="access" className="mt-5"><Panel title="Account access">{data.account ? <><Detail icon={ShieldCheck} label="Login email" value={data.account.email} /><Detail label="Account" value={data.account.is_active ? "Active" : "Disabled"} /><Detail label="Last login" value={data.account.last_login ? new Date(data.account.last_login).toLocaleString("en-IN") : "Never"} />{can("roles.manage") && <Button asChild variant="outline" className="mt-3 rounded-xl"><Link to="/app/access">Manage roles and locations</Link></Button>}</> : <EmptyState variant="inline" icon={ShieldCheck} title="No application access" description="This employee has a business profile without a login account." />}</Panel></TabsContent>}
    </Tabs>

    <Dialog open={editing} onOpenChange={(open) => { if (!open && busy) return; setEditing(open); }}><DialogContent className="sm:max-w-2xl"><DialogHeader><DialogTitle className="font-display text-3xl">Edit employee</DialogTitle></DialogHeader><Form {...editForm}><form noValidate onSubmit={save} className="grid gap-4 sm:grid-cols-2">
      <ValidatedField control={control} name="first_name" label="First name"><Input autoFocus autoComplete="given-name" /></ValidatedField>
      <ValidatedField control={control} name="last_name" label="Last name"><Input autoComplete="family-name" /></ValidatedField>
      <ValidatedField control={control} name="phone" label="Phone"><Input inputMode="tel" autoComplete="tel" /></ValidatedField>
      <ValidatedField control={control} name="email" label="Email"><Input type="email" autoComplete="email" /></ValidatedField>
      <ValidatedField control={control} name="designation" label="Designation"><Input /></ValidatedField>
      {data.capabilities.view_compensation && <ValidatedField control={control} name="salary" label="Monthly salary (INR)"><Input inputMode="decimal" /></ValidatedField>}
      <ValidatedField control={control} name="joining_date" label="Joining date"><Input type="date" /></ValidatedField>
      <ValidatedField control={control} name="status" label="Status"><select className="h-10 w-full rounded-xl border bg-background px-3" {...register("status")}><option value="active">Active</option><option value="on_leave">On leave</option><option value="inactive">Inactive</option></select></ValidatedField>
      <FormField control={control} name="location_ids" render={() => <FormItem className="sm:col-span-2"><FormLabel>Locations</FormLabel><div className="mt-2 grid gap-2 sm:grid-cols-2">{data.available_locations.map((location) => <label key={location.id} className="flex gap-2 rounded-xl border p-3 text-sm"><input type="checkbox" checked={selectedLocations.includes(location.id)} onChange={(event) => setValue("location_ids", event.target.checked ? [...selectedLocations, location.id] : selectedLocations.filter((id) => id !== location.id), { shouldDirty: true, shouldValidate: true })} />{location.name}</label>)}</div><FormMessage /></FormItem>} />
      <FormRootError className="sm:col-span-2" error={formState.errors.root?.server} />
      <Button type="submit" loading={busy} loadingText="Saving employee..." className="rounded-xl sm:col-span-2">Save employee</Button>
    </form></Form></DialogContent></Dialog>
  </PageShell>;
}

function ValidatedField({ control, name, label, children }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />; }
function Metric({ icon: Icon, label, value }) { return <Surface className="p-5"><Icon className="text-accent" /><div className="mt-3 font-display text-3xl">{value}</div><div className="mt-1 text-xs text-muted-foreground">{label}</div></Surface>; }
function Panel({ title, children }) { return <Surface className="p-5"><h2 className="mb-4 font-display text-xl font-semibold sm:text-2xl">{title}</h2>{children}</Surface>; }
function Detail({ icon: Icon, label, value }) { return <div className="flex gap-3 py-2">{Icon && <Icon className="text-muted-foreground" />}<div><div className="overline">{label}</div><div className="mt-1 text-sm">{value || "Not provided"}</div></div></div>; }
function Row({ title, meta, value }) { return <div className="flex justify-between gap-3 border-b py-3 last:border-0"><div><div className="font-medium capitalize">{title}</div><div className="text-xs text-muted-foreground">{meta}</div></div><div className="text-sm">{value}</div></div>; }
function Empty({ title, copy }) { return <EmptyState variant="page" icon={User} title={title} description={copy} />; }
function money(value) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format((value || 0) / 100); }
