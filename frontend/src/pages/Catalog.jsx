import React, { useDeferredValue, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

const blank = { name: "", sku: "", item_type: "product", description: "", price: "", cost: "", tax: "0", tax_inclusive: false, duration_minutes: "", unit: "unit", track_stock: true, hsn_sac: "" };
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
  const [form, setForm] = useState(blank);
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

  const create = async (event) => {
    event.preventDefault();
    try {
      await createItem({
        name: form.name.trim(), sku: form.sku.trim(), item_type: form.item_type,
        description: form.description.trim() || null,
        price_paise: Math.round(Number(form.price) * 100), cost_paise: Math.round(Number(form.cost || 0) * 100),
        tax_rate_bps: Math.round(Number(form.tax || 0) * 100), tax_inclusive: form.tax_inclusive,
        duration_minutes: form.item_type === "service" && form.duration_minutes ? Number(form.duration_minutes) : null,
        unit: form.unit || "unit", track_stock: !["service", "lab_test"].includes(form.item_type) && form.track_stock,
        hsn_sac: form.hsn_sac.trim() || null,
      }).unwrap();
      paging.reset();
      toast.success("Catalog item created"); setOpen(false); setForm(blank);
    } catch (error) { toast.error(error?.data?.detail || "Could not create catalog item"); }
  };

  return <PageShell className="reveal">
    <PageHeader eyebrow="What your business offers" title="Catalog" description="Define products, services, medicines, and tests once. Manage physical quantities separately in Inventory." actions={<div className="flex gap-2">{can("inventory.view") && <Button variant="outline" onClick={() => navigate("/app/inventory")}><Warehouse className="mr-2" />Open inventory</Button>}{can("catalog.manage") && <Button onClick={() => setOpen(true)}><Plus className="mr-2" />Add item</Button>}</div>} />
    <MetricStrip metrics={metrics} loading={query.isLoading && !query.data} />
    <FilterBar><div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search name, SKU, HSN, or SAC" /></div><Select value={type} onValueChange={setType}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All item types</SelectItem>{Object.entries(typeLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select><Select value={state} onValueChange={setState}><SelectTrigger className="w-full sm:w-36"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="inactive">Inactive</SelectItem><SelectItem value="all">All states</SelectItem></SelectContent></Select></FilterBar>
    <DataTable loading={query.isLoading && !items.length} rows={items} columns={columns} onRowClick={(row) => navigate(`/app/catalog/${row.id}`)} empty={<EmptyState variant={isFilteredEmpty ? "filtered" : "page"} alignment="left" icon={Package} title={isFilteredEmpty ? "No catalog items match this view" : "Define what your business offers"} description={isFilteredEmpty ? "Clear the search and catalog filters to see every item." : "Create the first product or service, then connect pricing, tax, stock, sales, and appointments."} primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setSearch(""); setType("all"); setState("active"); }}>Clear filters</Button> : can("catalog.manage") ? <Button onClick={() => setOpen(true)}>Add catalog item</Button> : null} steps={isFilteredEmpty ? [] : [{ title: "Create item" }, { title: "Set pricing" }, { title: "Use in operations" }]} />} />
    {(items.length > 0 || query.data?.has_more) && <CursorListFooter count={items.length} noun="catalog items" hasMore={Boolean(query.data?.has_more)} loading={query.isFetching} error={query.isError} onLoadMore={() => paging.loadMore(query.data?.next_cursor)} onRetry={query.refetch} />}

    <DrawerForm open={open} onOpenChange={setOpen} title="Add catalog item" description="Set commercial details here. Opening stock is received from Inventory after creation."><form onSubmit={create} className="space-y-5"><div className="grid gap-4 sm:grid-cols-2"><Field label="Name"><Input autoFocus required value={form.name} onChange={setField(setForm, "name")} /></Field><Field label="SKU"><Input required value={form.sku} onChange={setField(setForm, "sku")} /></Field><Field label="Type"><Select value={form.item_type} onValueChange={(value) => setForm((current) => ({ ...current, item_type: value, track_stock: !["service", "lab_test"].includes(value) }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{Object.entries(typeLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select></Field><Field label="Selling price (INR)"><Input required type="number" min="0" step=".01" value={form.price} onChange={setField(setForm, "price")} /></Field><Field label="Cost (INR)"><Input type="number" min="0" step=".01" value={form.cost} onChange={setField(setForm, "cost")} /></Field><Field label="GST %"><Input type="number" min="0" max="100" step=".01" value={form.tax} onChange={setField(setForm, "tax")} /></Field><Field label="HSN / SAC"><Input value={form.hsn_sac} onChange={setField(setForm, "hsn_sac")} /></Field><Field label="Unit"><Input value={form.unit} onChange={setField(setForm, "unit")} /></Field>{form.item_type === "service" && <Field label="Duration (minutes)"><Input required type="number" min="1" value={form.duration_minutes} onChange={setField(setForm, "duration_minutes")} /></Field>}</div><Field label="Description"><textarea className="min-h-24 w-full rounded-xl border bg-background p-3 text-sm" value={form.description} onChange={setField(setForm, "description")} /></Field><div className="flex flex-wrap gap-5 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={form.tax_inclusive} onChange={(event) => setForm((current) => ({ ...current, tax_inclusive: event.target.checked }))} />Price includes GST</label>{!["service", "lab_test"].includes(form.item_type) && <label className="flex items-center gap-2"><input type="checkbox" checked={form.track_stock} onChange={(event) => setForm((current) => ({ ...current, track_stock: event.target.checked }))} />Track in Inventory</label>}</div><Button disabled={createState.isLoading} className="h-12 w-full">{createState.isLoading ? "Creating item..." : "Create catalog item"}</Button></form></DrawerForm>
  </PageShell>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function setField(setForm, key) { return (event) => setForm((current) => ({ ...current, [key]: event.target.value })); }
function money(value) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0) / 100); }
