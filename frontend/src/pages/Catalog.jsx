import React, { useDeferredValue, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MagnifyingGlass, Package, Plus, Warehouse } from "@phosphor-icons/react";
import { toast } from "sonner";
import {
  CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip, PageHeader,
  PageShell, StatusBadge,
} from "@/components/system";
import { QUERY_POLICIES } from "@/store/api/queryPolicies";
import { useCreateCatalogItemMutation, useGetCatalogDirectoryQuery } from "@/features/catalog/catalogApi";
import useCursorPagination from "@/hooks/useCursorPagination";
import { applyApiErrors, catalogItemSchema, FORM_OPTIONS } from "@/lib/validation";

const blank = { name: "", sku: "", item_type: "product", description: "", price: "", cost: "", tax_rate: "0", tax_inclusive: false, duration_minutes: "", unit: "unit", track_stock: true, hsn_sac: "" };
const typeLabels = { product: "Product", service: "Service", medicine: "Medicine", lab_test: "Lab test" };
export default function Catalog() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [createItem, createState] = useCreateCatalogItemMutation();
  const [open, setOpen] = useState(() => new URLSearchParams(window.location.search).get("new") === "1");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [type, setType] = useState("all");
  const [state, setState] = useState("active");
  const itemForm = useForm({ resolver: zodResolver(catalogItemSchema), defaultValues: blank, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, setValue, watch } = itemForm;
  const itemType = watch("item_type"); const trackStock = watch("track_stock"); const taxInclusive = watch("tax_inclusive");
  const pageKey = JSON.stringify({ q: deferredSearch, type, state });
  const paging = useCursorPagination(pageKey);
  const query = useGetCatalogDirectoryQuery({
    q: deferredSearch,
    itemType: type,
    state,
    cursor: paging.cursor,
    limit: 25,
  }, QUERY_POLICIES.collaborative);
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(query.data); }, [acceptPage, query.data]);
  const items = paging.items;

  if (query.isError && !query.data && !items.length) return <PageShell><ErrorState title="Catalog could not be loaded" description={query.error?.data?.detail} retry={query.refetch} /></PageShell>;

  const summary = query.data?.summary;
  const metrics = summary ? [
    { id: "items", label: "Catalog items", value: summary.catalog_items },
    { id: "products", label: "Products and medicines", value: summary.products },
    { id: "services", label: "Services and tests", value: summary.services },
    { id: "stock", label: "Inventory tracked", value: summary.stock_tracked },
  ] : [];
  const columns = [
    { key: "item", label: "Item", render: (row) => <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary"><Package /></span><span><span className="block font-semibold">{row.name}</span><span className="mt-1 block text-xs text-muted-foreground">{row.sku}{row.hsn_sac ? ` · ${row.hsn_sac}` : ""}</span></span></div> },
    { key: "type", label: "Type", render: (row) => <StatusBadge status="neutral" label={typeLabels[row.item_type] || row.item_type} /> },
    { key: "price", label: "Selling price", render: (row) => money(row.price_paise) },
    { key: "tax", label: "GST", render: (row) => `${row.tax_rate_bps / 100}% ${row.tax_inclusive ? "included" : "extra"}` },
    { key: "availability", label: "Operations", render: (row) => row.item_type === "service" ? `${row.duration_minutes || 0} minutes` : row.track_stock ? "Tracked in Inventory" : "Quantity not tracked" },
    { key: "status", label: "State", render: (row) => <StatusBadge status={row.is_active ? "active" : "inactive"} /> },
  ];
  const isFilteredEmpty = Boolean(deferredSearch || type !== "all" || state !== "active");

  const create = handleSubmit(async (values) => {
    clearErrors("root.server");
    try {
      await createItem({
        name: values.name, sku: values.sku, item_type: values.item_type,
        description: values.description,
        price_paise: values.price_paise, cost_paise: values.cost_paise,
        tax_rate_bps: values.tax_rate_bps, tax_inclusive: values.tax_inclusive,
        duration_minutes: values.item_type === "service" ? values.duration_minutes : null,
        unit: values.unit, track_stock: !["service", "lab_test"].includes(values.item_type) && values.track_stock,
        hsn_sac: values.hsn_sac,
      }).unwrap();
      paging.reset();
      toast.success("Catalog item created"); setOpen(false); reset(blank);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { aliases: { price_paise: "price", cost_paise: "cost", tax_rate_bps: "tax_rate" }, fallback: "Could not create catalog item" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });

  return <PageShell className="reveal">
    <PageHeader eyebrow="What your business offers" title="Catalog" description="Define products, services, medicines, and tests once. Manage physical quantities separately in Inventory." actions={<div className="flex gap-2">{can("inventory.view") && <Button variant="outline" onClick={() => navigate("/app/inventory")}><Warehouse className="mr-2" />Open inventory</Button>}{can("catalog.manage") && <Button onClick={() => { reset(blank); setOpen(true); }}><Plus className="mr-2" />Add item</Button>}</div>} />
    <MetricStrip metrics={metrics} loading={query.isLoading && !query.data} />
    <FilterBar><div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search name, SKU, HSN, or SAC" /></div><Select value={type} onValueChange={setType}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All item types</SelectItem>{Object.entries(typeLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select><Select value={state} onValueChange={setState}><SelectTrigger className="w-full sm:w-36"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="inactive">Inactive</SelectItem><SelectItem value="all">All states</SelectItem></SelectContent></Select></FilterBar>
    <DataTable loading={query.isLoading && !items.length} rows={items} columns={columns} onRowClick={(row) => navigate(`/app/catalog/${row.id}`)} empty={<EmptyState variant={isFilteredEmpty ? "filtered" : "page"} alignment="left" icon={Package} title={isFilteredEmpty ? "No catalog items match this view" : "Define what your business offers"} description={isFilteredEmpty ? "Clear the search and catalog filters to see every item." : "Create the first product or service, then connect pricing, tax, stock, sales, and appointments."} primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setSearch(""); setType("all"); setState("active"); }}>Clear filters</Button> : can("catalog.manage") ? <Button onClick={() => setOpen(true)}>Add catalog item</Button> : null} steps={isFilteredEmpty ? [] : [{ title: "Create item" }, { title: "Set pricing" }, { title: "Use in operations" }]} />} />
    {(items.length > 0 || query.data?.has_more) && <CursorListFooter count={items.length} noun="catalog items" hasMore={Boolean(query.data?.has_more)} loading={query.isFetching} error={query.isError} onLoadMore={() => paging.loadMore(query.data?.next_cursor)} onRetry={query.refetch} />}

    <DrawerForm open={open} onOpenChange={(next) => { if (!next && (formState.isSubmitting || createState.isLoading)) return; setOpen(next); }} title="Add catalog item" description="Set commercial details here. Opening stock is received from Inventory after creation."><Form {...itemForm}><form noValidate onSubmit={create} className="space-y-5"><div className="grid gap-4 sm:grid-cols-2"><CatalogField control={control} name="name" label="Name"><Input autoFocus /></CatalogField><CatalogField control={control} name="sku" label="SKU"><Input /></CatalogField><FormField control={control} name="item_type" render={({ field }) => <FormItem><FormLabel>Type</FormLabel><Select value={field.value} onValueChange={(value) => { field.onChange(value); setValue("track_stock", !["service", "lab_test"].includes(value)); }}><FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl><SelectContent>{Object.entries(typeLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} /><CatalogField control={control} name="price" label="Selling price (INR)"><Input inputMode="decimal" placeholder="0.00" /></CatalogField><CatalogField control={control} name="cost" label="Cost (INR)"><Input inputMode="decimal" placeholder="0.00" /></CatalogField><CatalogField control={control} name="tax_rate" label="GST %"><Input inputMode="decimal" placeholder="0" /></CatalogField><CatalogField control={control} name="hsn_sac" label="HSN / SAC"><Input /></CatalogField><CatalogField control={control} name="unit" label="Unit"><Input /></CatalogField>{itemType === "service" && <CatalogField control={control} name="duration_minutes" label="Duration (minutes)"><Input inputMode="numeric" /></CatalogField>}</div><CatalogField control={control} name="description" label="Description"><Textarea rows={4} /></CatalogField><div className="flex flex-wrap gap-5 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={taxInclusive} onChange={(event) => setValue("tax_inclusive", event.target.checked, { shouldDirty: true })} />Price includes GST</label>{!["service", "lab_test"].includes(itemType) && <label className="flex items-center gap-2"><input type="checkbox" checked={trackStock} onChange={(event) => setValue("track_stock", event.target.checked, { shouldDirty: true })} />Track in Inventory</label>}</div><FormRootError error={formState.errors.root?.server} /><Button type="submit" loading={formState.isSubmitting || createState.isLoading} loadingText="Creating item..." className="h-12 w-full">Create catalog item</Button></form></Form></DrawerForm>
  </PageShell>;
}

function CatalogField({ control, name, label, children }) { return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />; }
function money(value) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0) / 100); }
