import React, { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useParams } from "react-router-dom";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import StockAdjustmentDialog from "@/components/StockAdjustmentDialog";
import { ArrowLeft, CalendarBlank, CurrencyInr, Cube, Minus, NotePencil, Package, Plus, TrendUp, WarningCircle } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useGetCatalogProfileQuery } from "@/store/api/workspaceApi";
import { QUERY_POLICIES } from "@/store/api/queryPolicies";
import { ProfileBackLink } from "@/components/entities/EntityProfile";
import { EmptyState, PageShell, Surface } from "@/components/system";
import { useUpdateCatalogItemMutation } from "@/features/catalog/catalogApi";
import { applyApiErrors, catalogProfileSchema, FORM_OPTIONS } from "@/lib/validation";
import { useRegisterAIPageContext } from "@/components/ai/AIConversationProvider";

function catalogValues(item = {}) {
  return {
    name: item.name || "",
    item_type: item.item_type || "product",
    description: item.description || "",
    hsn_sac: item.hsn_sac || "",
    price: item.price_paise == null ? "" : String(item.price_paise / 100),
    cost: item.cost_paise == null ? "" : String(item.cost_paise / 100),
    tax_rate: item.tax_rate_bps == null ? "" : String(item.tax_rate_bps / 100),
    duration_minutes: item.duration_minutes == null ? "" : String(item.duration_minutes),
    unit: item.unit || "unit",
    tax_inclusive: Boolean(item.tax_inclusive),
    track_stock: Boolean(item.track_stock),
    is_active: item.is_active !== false,
    version: item.version || 1,
  };
}

export default function CatalogProfile() {
  const { itemId } = useParams(); const { locationId, location } = useBusiness(); const { data, error, refetch } = useGetCatalogProfileQuery({ itemId, locationId }, QUERY_POLICIES.operational); const [editing, setEditing] = useState(false); const [adjustment, setAdjustment] = useState(null); const [updateItem, updateState] = useUpdateCatalogItemMutation();
  useRegisterAIPageContext(data?.item ? { kind: "catalog", id: data.item.id || itemId, label: `Catalog item: ${data.item.name}` } : null);
  const editForm = useForm({ resolver: zodResolver(catalogProfileSchema), defaultValues: catalogValues(), ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, setValue, watch } = editForm;
  const taxInclusive = watch("tax_inclusive"); const active = watch("is_active");
  useEffect(() => { if (data?.item && !editing) reset(catalogValues(data.item)); }, [data?.item, editing, reset]);
  const openEditor = () => { reset(catalogValues(data.item)); setEditing(true); };
  const save = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await updateItem({ itemId, name: values.name, description: values.description || null, hsn_sac: values.hsn_sac || null, price_paise: values.price_paise, cost_paise: values.cost_paise, tax_rate_bps: values.tax_rate_bps, tax_inclusive: values.tax_inclusive, duration_minutes: values.item_type === "service" ? values.duration_minutes : null, unit: values.unit, track_stock: values.track_stock, is_active: values.is_active, version: values.version }).unwrap();
      toast.success("Catalog item updated"); setEditing(false);
    } catch (requestError) {
      const normalized = applyApiErrors(requestError, setError, { aliases: { price_paise: "price", cost_paise: "cost", tax_rate_bps: "tax_rate" }, fallback: "Could not update item" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  if (error) return <PageShell><State title={error.status === 403 ? "Access restricted" : "Item unavailable"} copy={error.data?.detail || "Could not load catalog item"} /></PageShell>;
  if (!data) return <PageShell><div className="h-72 animate-pulse rounded-2xl bg-secondary" /></PageShell>;
  const item = data.item;
  const hasPerformance = Boolean(data.sales?.length || data.appointments?.length);
  const hasInventoryData = Boolean(data.stock?.length || data.movements?.length);
  return <PageShell className="reveal" size="standard">
    <ProfileBackLink fallback="/app/catalog" className="inline-flex items-center gap-2 text-sm text-muted-foreground"><ArrowLeft />Back</ProfileBackLink>
    <Surface className="flex flex-col justify-between gap-5 p-5 sm:p-6 lg:flex-row lg:items-center"><div className="flex min-w-0 gap-4"><div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-secondary sm:h-16 sm:w-16"><Package size={28} /></div><div className="min-w-0"><div className="font-mono text-xs text-muted-foreground">{item.sku}</div><h1 className="mt-1 truncate font-display text-2xl font-semibold sm:text-3xl">{item.name}</h1><div className="mt-2 flex flex-wrap gap-2"><span className="rounded-full bg-secondary px-3 py-1 text-xs capitalize">{item.item_type.replaceAll("_", " ")}</span><span className={`rounded-full px-3 py-1 text-xs ${item.is_active ? "bg-emerald-100 text-emerald-800" : "bg-secondary"}`}>{item.is_active ? "Active" : "Inactive"}</span></div></div></div><div className="flex flex-wrap gap-2">{item.track_stock && data.capabilities.adjust_inventory && <Button variant="outline" disabled={!locationId} onClick={() => setAdjustment({ item, mode: "increase", locationId, locationName: location?.name })} className="rounded-xl text-emerald-700"><Plus />Receive stock</Button>}{data.capabilities.manage && <Button onClick={openEditor} className="rounded-xl"><NotePencil className="mr-2" />Edit item</Button>}</div></Surface>
    {(data.capabilities.view_inventory || data.capabilities.view_sales || data.capabilities.view_appointments) && <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">{data.capabilities.view_inventory && <Metric icon={Cube} label={`Available at ${data.scope?.location?.name || "all locations"}`} value={`${data.metrics.stock_milli / 1000} ${item.unit}`} />}{data.capabilities.view_sales && <><Metric icon={TrendUp} label={`Sold at ${data.scope?.location?.name || "all locations"}`} value={`${data.metrics.units_sold_milli / 1000} ${item.unit}`} /><Metric icon={CurrencyInr} label="Revenue" value={money(data.metrics.revenue_paise)} /></>}{data.capabilities.view_appointments && <Metric icon={CalendarBlank} label="Bookings" value={data.metrics.bookings} />}</div>}
    <Tabs defaultValue="overview">
      <TabsList className="premium-scrollbar h-auto max-w-full justify-start overflow-x-auto rounded-xl">
        <TabsTrigger value="overview">Overview</TabsTrigger>
        {item.track_stock && data.capabilities.view_inventory && <TabsTrigger value="inventory">Inventory</TabsTrigger>}
        {hasPerformance && <TabsTrigger value="performance">Performance</TabsTrigger>}
      </TabsList>
      <TabsContent value="overview" className="mt-5 grid items-start gap-5 lg:grid-cols-2">
        <Panel title="Pricing & tax"><Detail label="Selling price" value={money(item.price_paise)} /><Detail label="Cost" value={money(item.cost_paise)} /><Detail label="GST" value={`${item.tax_rate_bps / 100}% ${item.tax_inclusive ? "inclusive" : "exclusive"}`} /><Detail label="HSN / SAC" value={item.hsn_sac} /></Panel>
        <Panel title="Service information"><Detail label="Unit" value={item.unit} /><Detail label="Duration" value={item.duration_minutes ? `${item.duration_minutes} minutes` : null} /><p className="mt-4 text-sm leading-7">{item.description || "No description has been added."}</p></Panel>
      </TabsContent>
      {item.track_stock && data.capabilities.view_inventory && <TabsContent value="inventory" className="mt-5">
        {hasInventoryData ? <div className="grid items-start gap-5 lg:grid-cols-2">
          {data.stock?.length > 0 && <Panel title={`Stock at ${data.scope?.location?.name || "all locations"}`}>{data.stock.map((stock) => <div key={stock.id} className="border-b py-3 last:border-0"><div className="flex justify-between gap-3"><div><div className="font-medium">Batch {stock.batch_number || "General"}</div><div className="text-xs text-muted-foreground">{stock.expires_on ? `Expires ${new Date(stock.expires_on).toLocaleDateString("en-IN")}` : "No expiry date"}</div></div><div className={stock.quantity_milli <= stock.reorder_level_milli ? "text-destructive" : ""}>{stock.quantity_milli / 1000} {item.unit}</div></div>{data.capabilities.adjust_inventory && <div className="mt-3 flex gap-2"><Button size="sm" variant="outline" className="rounded-lg text-emerald-700" onClick={() => setAdjustment({ item, mode: "increase", locationId: stock.location_id, locationName: stock.location.name, batchNumber: stock.batch_number, expiresOn: stock.expires_on, reorderLevelMilli: stock.reorder_level_milli, currentQuantityMilli: stock.quantity_milli })}><Plus />Increase</Button><Button size="sm" variant="outline" className="rounded-lg text-destructive" disabled={stock.quantity_milli <= 0} onClick={() => setAdjustment({ item, mode: "decrease", locationId: stock.location_id, locationName: stock.location.name, batchNumber: stock.batch_number, expiresOn: stock.expires_on, reorderLevelMilli: stock.reorder_level_milli, currentQuantityMilli: stock.quantity_milli })}><Minus />Decrease</Button></div>}</div>)}</Panel>}
          {data.movements?.length > 0 && <Panel title="Movement ledger">{data.movements.slice(0, 30).map((movement) => <div key={movement.id} className="flex justify-between border-b py-3 last:border-0"><div><div className="font-medium capitalize">{movement.movement_type}</div><div className="text-xs text-muted-foreground">{movement.reason}</div></div><div className={movement.quantity_delta_milli < 0 ? "text-destructive" : "text-emerald-700"}>{movement.quantity_delta_milli > 0 ? "+" : ""}{movement.quantity_delta_milli / 1000}</div></div>)}</Panel>}
        </div> : <EmptyState variant="section" alignment="left" icon={Cube} title="No stock received yet" description="Receive the opening quantity to begin stock and movement tracking." primaryAction={data.capabilities.adjust_inventory && locationId ? <Button onClick={() => setAdjustment({ item, mode: "increase", locationId, locationName: location?.name })}><Plus />Receive stock</Button> : null} />}
      </TabsContent>}
      {hasPerformance && <TabsContent value="performance" className="mt-5 grid items-start gap-5 lg:grid-cols-2">
        {data.capabilities.view_sales && data.sales?.length > 0 && <Panel title="Recent sales">{data.sales.slice(0, 30).map(({ line, invoice }) => <div key={line.id} className="flex justify-between gap-3 border-b py-3 last:border-0"><div><div className="font-medium">{invoice.invoice_number}</div><div className="text-xs text-muted-foreground">{new Date(invoice.created_at).toLocaleDateString("en-IN")} / {line.quantity_milli / 1000} {item.unit}</div></div><div>{money(line.total_paise)}</div></div>)}</Panel>}
        {data.capabilities.view_appointments && data.appointments?.length > 0 && <Panel title="Service bookings">{data.appointments.slice(0, 30).map((appointment) => <div key={appointment.id} className="flex justify-between border-b py-3 last:border-0"><div><div className="font-medium capitalize">{appointment.status}</div><div className="text-xs text-muted-foreground">{new Date(appointment.starts_at).toLocaleString("en-IN")}</div></div></div>)}</Panel>}
      </TabsContent>}
    </Tabs>
    <Dialog open={editing} onOpenChange={(open) => { if (!open && (formState.isSubmitting || updateState.isLoading)) return; setEditing(open); }}><DialogContent className="sm:max-w-2xl"><DialogHeader><DialogTitle className="font-display text-3xl">Edit catalog item</DialogTitle></DialogHeader><Form {...editForm}><form noValidate onSubmit={save} className="grid gap-4 sm:grid-cols-2"><ValidatedField control={control} name="name" label="Name"><Input autoFocus /></ValidatedField><ValidatedField control={control} name="hsn_sac" label="HSN / SAC"><Input /></ValidatedField><ValidatedField control={control} name="price" label="Selling price (INR)"><Input inputMode="decimal" /></ValidatedField><ValidatedField control={control} name="cost" label="Cost (INR)"><Input inputMode="decimal" /></ValidatedField><ValidatedField control={control} name="tax_rate" label="GST %"><Input inputMode="decimal" /></ValidatedField><ValidatedField control={control} name="unit" label="Unit"><Input /></ValidatedField>{item.item_type === "service" && <ValidatedField control={control} name="duration_minutes" label="Duration (minutes)"><Input inputMode="numeric" /></ValidatedField>}<ValidatedField control={control} name="description" label="Description" className="sm:col-span-2"><Textarea rows={4} /></ValidatedField><FormField control={control} name="tax_inclusive" render={() => <FormItem><label className="flex gap-2 text-sm"><input type="checkbox" checked={taxInclusive} onChange={(event) => setValue("tax_inclusive", event.target.checked, { shouldDirty: true })} />Tax-inclusive pricing</label></FormItem>} /><FormField control={control} name="is_active" render={() => <FormItem><label className="flex gap-2 text-sm"><input type="checkbox" checked={active} onChange={(event) => setValue("is_active", event.target.checked, { shouldDirty: true })} />Active item</label></FormItem>} /><FormRootError className="sm:col-span-2" error={formState.errors.root?.server} /><Button type="submit" loading={formState.isSubmitting || updateState.isLoading} loadingText="Saving item..." className="rounded-xl sm:col-span-2">Save item</Button></form></Form></DialogContent></Dialog>
    {adjustment && <StockAdjustmentDialog adjustment={adjustment} onClose={() => setAdjustment(null)} onComplete={refetch} />}
  </PageShell>;
}
function Metric({ icon: Icon, label, value }) { return <Surface className="p-5"><Icon className="text-accent" /><div className="mt-3 font-display text-2xl">{value}</div><div className="mt-1 text-xs text-muted-foreground">{label}</div></Surface>; }
function Panel({ title, children }) { return <Surface className="p-5"><h2 className="mb-4 font-display text-xl font-semibold sm:text-2xl">{title}</h2>{children}</Surface>; }
function Detail({ label, value }) { return <div className="py-2"><div className="overline">{label}</div><div className="text-sm mt-1">{value || "Not provided"}</div></div>; }
function ValidatedField({ control, name, label, children, className }) { return <FormField control={control} name={name} render={({ field }) => <FormItem className={className}><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />; }
function State({ title, copy }) { return <EmptyState variant="page" icon={WarningCircle} title={title} description={copy} />; }
function money(value) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format((value || 0) / 100); }
