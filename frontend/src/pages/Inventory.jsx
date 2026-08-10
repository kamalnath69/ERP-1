import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowsLeftRight, MagnifyingGlass, Package, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip, PageHeader, PageShell, RemoteCombobox, StatusBadge } from "@/components/system";
import StockAdjustmentDialog from "@/components/StockAdjustmentDialog";
import { useGetInventoryLevelsPageQuery, useGetInventoryMovementsPageQuery, useTransferStockMutation } from "@/store/api/workspaceApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import useCursorPagination from "@/hooks/useCursorPagination";

export default function Inventory() {
  const { can } = useAuth();
  const { locationId, locations } = useBusiness();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [state, setState] = useState("all");
  const [activeTab, setActiveTab] = useState("stock");
  const [adjustment, setAdjustment] = useState(null);
  const [transferOpen, setTransferOpen] = useState(false);
  const stockPaging = useCursorPagination(JSON.stringify({ locationId, q: deferredSearch, state }));
  const movementPaging = useCursorPagination(JSON.stringify({ locationId, ledger: true }));
  const batchPaging = useCursorPagination(JSON.stringify({ locationId, batches: true }));
  const stockQuery = useGetInventoryLevelsPageQuery({
    locationId,
    q: deferredSearch,
    state: state === "all" ? undefined : state,
    cursor: stockPaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.operational, !locationId));
  const movementQuery = useGetInventoryMovementsPageQuery({
    locationId,
    cursor: movementPaging.cursor,
    limit: 50,
  }, withSkip(QUERY_POLICIES.operational, !locationId || activeTab !== "movements"));
  const batchQuery = useGetInventoryLevelsPageQuery({
    locationId,
    batchesOnly: true,
    cursor: batchPaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.operational, !locationId || activeTab !== "batches"));
  const { accept: acceptStock } = stockPaging;
  const { accept: acceptMovements } = movementPaging;
  const { accept: acceptBatches } = batchPaging;
  useEffect(() => { acceptStock(stockQuery.data); }, [acceptStock, stockQuery.data]);
  useEffect(() => { acceptMovements(movementQuery.data); }, [acceptMovements, movementQuery.data]);
  useEffect(() => { acceptBatches(batchQuery.data); }, [acceptBatches, batchQuery.data]);
  const levels = stockPaging.items;
  const movements = movementPaging.items;
  const batches = batchPaging.items;
  const summary = stockQuery.data?.summary;
  const metrics = summary ? [
    { id: "stocked", label: "Stocked items", value: summary.stocked_items },
    { id: "value", label: "Stock value", value: summary.stock_value_paise, format: "money" },
    { id: "low", label: "Low stock", value: summary.low_stock, tone: summary.low_stock ? "warning" : "neutral" },
    { id: "expiry", label: "Expiring batches", value: summary.expiring_batches, tone: summary.expiring_batches ? "warning" : "neutral" },
  ] : [];
  if (stockQuery.isError && !stockQuery.data && !levels.length) return <PageShell><ErrorState retry={stockQuery.refetch} title="Inventory could not be loaded" description={stockQuery.error?.data?.detail} /></PageShell>;
  const columns = [
    { key: "item", label: "Item", render: (row) => <div><div className="font-semibold">{row.item.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.item.sku}</div></div> },
    { key: "location", label: "Location", render: (row) => row.location.name },
    { key: "quantity", label: "Available", render: (row) => <span className="font-mono font-medium">{quantity(row.quantity_milli)} {row.item.unit}</span> },
    { key: "threshold", label: "Reorder at", render: (row) => quantity(row.reorder_level_milli) },
    { key: "batch", label: "Batch / expiry", render: (row) => <div><div>{row.batch_number || "No batch"}</div><div className="mt-1 text-xs text-muted-foreground">{row.expires_on ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${row.expires_on}T00:00:00`)) : "No expiry"}</div></div> },
    { key: "status", label: "State", render: (row) => <StatusBadge status={stockState(row)} /> },
    { key: "actions", label: "", render: (row) => can("inventory.adjust") && <div className="flex justify-end gap-1"><Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); setAdjustment(adjustmentFor(row, "increase")); }} aria-label={`Increase ${row.item.name}`}><ArrowUp /></Button><Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); setAdjustment(adjustmentFor(row, "decrease")); }} disabled={row.quantity_milli <= 0} aria-label={`Decrease ${row.item.name}`}><ArrowDown /></Button></div> },
  ];
  const isFilteredEmpty = Boolean(search.trim() || state !== "all");
  return <PageShell className="reveal">
    <PageHeader eyebrow="Stock control" title="Inventory" description="Location quantities, batches, expiry risks, and every movement in one ledger." actions={can("inventory.adjust") && locations.length > 1 ? <Button className="rounded-xl" onClick={() => setTransferOpen(true)}><ArrowsLeftRight className="mr-2" />Transfer stock</Button> : null} />
    <MetricStrip metrics={metrics} loading={stockQuery.isLoading && !stockQuery.data} />
    <Tabs value={activeTab} onValueChange={setActiveTab}><TabsList className="h-auto w-full justify-start overflow-x-auto rounded-xl bg-secondary/60 p-1 sm:w-fit"><TabsTrigger value="stock">Current stock</TabsTrigger><TabsTrigger value="movements">Movement ledger</TabsTrigger><TabsTrigger value="batches">Batches & expiry</TabsTrigger></TabsList>
      <TabsContent value="stock" className="mt-5 space-y-4"><FilterBar><div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder="Search item, SKU, or batch" /></div><Select value={state} onValueChange={setState}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All stock</SelectItem><SelectItem value="available">Available</SelectItem><SelectItem value="low">Low stock</SelectItem><SelectItem value="out">Out of stock</SelectItem><SelectItem value="expiring">Expiring soon</SelectItem></SelectContent></Select></FilterBar><DataTable columns={columns} rows={levels} loading={stockQuery.isLoading && !levels.length} empty={<EmptyState variant={isFilteredEmpty ? "filtered" : "page"} alignment="left" icon={Package} title={isFilteredEmpty ? "No stock matches this view" : "Receive your first stock"} description={isFilteredEmpty ? "Clear the item search and stock-state filter to see all quantities." : "Create a stock-tracked catalog item, then receive its opening quantity at this location."} primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setSearch(""); setState("all"); }}>Clear filters</Button> : can("catalog.manage") ? <Button asChild><Link to="/app/catalog">Open catalog</Link></Button> : null} steps={isFilteredEmpty ? [] : [{ title: "Create item" }, { title: "Receive quantity" }, { title: "Track movement" }]} />} />{(levels.length > 0 || stockQuery.data?.has_more) && <CursorListFooter count={levels.length} noun="stock rows" hasMore={Boolean(stockQuery.data?.has_more)} loading={stockQuery.isFetching} error={stockQuery.isError} onLoadMore={() => stockPaging.loadMore(stockQuery.data?.next_cursor)} onRetry={stockQuery.refetch} />}</TabsContent>
      <TabsContent value="movements" className="mt-5"><DataTable loading={movementQuery.isLoading && !movements.length} rows={movements} columns={movementColumns} empty={<EmptyState variant="section" alignment="left" icon={ArrowsLeftRight} title="No stock movements yet" description="Receipts, adjustments, sales, and transfers will build this audit trail." />} />{(movements.length > 0 || movementQuery.data?.has_more) && <CursorListFooter count={movements.length} noun="movements" hasMore={Boolean(movementQuery.data?.has_more)} loading={movementQuery.isFetching} error={movementQuery.isError} onLoadMore={() => movementPaging.loadMore(movementQuery.data?.next_cursor)} onRetry={movementQuery.refetch} />}</TabsContent>
      <TabsContent value="batches" className="mt-5"><DataTable loading={batchQuery.isLoading && !batches.length} rows={batches} columns={columns.filter((column) => column.key !== "actions")} empty={<EmptyState variant="section" alignment="left" icon={Warning} title="No batch-controlled stock" description="Batch numbers and expiry dates are captured while receiving stock." />} />{(batches.length > 0 || batchQuery.data?.has_more) && <CursorListFooter count={batches.length} noun="batches" hasMore={Boolean(batchQuery.data?.has_more)} loading={batchQuery.isFetching} error={batchQuery.isError} onLoadMore={() => batchPaging.loadMore(batchQuery.data?.next_cursor)} onRetry={batchQuery.refetch} />}</TabsContent>
    </Tabs>
    {adjustment && <StockAdjustmentDialog adjustment={adjustment} onClose={() => setAdjustment(null)} onComplete={() => { stockPaging.reset(); stockQuery.refetch(); }} />}
    <TransferDrawer open={transferOpen} onOpenChange={setTransferOpen} activeLocationId={locationId} locations={locations} onComplete={() => { stockPaging.reset(); movementPaging.reset(); }} />
  </PageShell>;
}

const movementColumns = [
  { key: "item_name", label: "Item", render: (row) => <div><div className="font-semibold">{row.item_name}</div><div className="mt-1 text-xs text-muted-foreground">{row.location_name}</div></div> },
  { key: "movement_type", label: "Type", render: (row) => <StatusBadge status={row.movement_type} /> },
  { key: "quantity_delta_milli", label: "Quantity", render: (row) => <span className={row.quantity_delta_milli > 0 ? "text-positive" : "text-danger"}>{row.quantity_delta_milli > 0 ? "+" : ""}{quantity(row.quantity_delta_milli)}</span> },
  { key: "reason", label: "Reason" },
  { key: "created_at", label: "Recorded", render: (row) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(row.created_at)) },
];

function TransferDrawer({ open, onOpenChange, activeLocationId, locations, onComplete }) {
  const [itemSearch, setItemSearch] = useState("");
  const deferredItemSearch = useDeferredValue(itemSearch.trim());
  const [selectedLevel, setSelectedLevel] = useState(null);
  const [form, setForm] = useState({ item_id: "", source_location_id: activeLocationId || "", destination_location_id: "", quantity: "", batch_number: "", reason: "Location transfer" });
  const itemPaging = useCursorPagination(JSON.stringify({ open, source: form.source_location_id, q: deferredItemSearch }));
  const itemQuery = useGetInventoryLevelsPageQuery({
    locationId: form.source_location_id,
    q: deferredItemSearch,
    state: "in_stock",
    cursor: itemPaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.reference, !open || !form.source_location_id));
  const { accept: acceptItems } = itemPaging;
  useEffect(() => { acceptItems(itemQuery.data); }, [acceptItems, itemQuery.data]);
  useEffect(() => {
    setForm((current) => current.source_location_id ? current : { ...current, source_location_id: activeLocationId || "" });
  }, [activeLocationId]);
  const uniqueLevels = useMemo(() => {
    const rows = itemPaging.items.length ? itemPaging.items : itemQuery.data?.items || [];
    return [...new Map(rows.map((row) => [row.item.id, row])).values()];
  }, [itemPaging.items, itemQuery.data?.items]);
  const [transfer, result] = useTransferStockMutation();
  const reset = () => {
    setForm({ item_id: "", source_location_id: activeLocationId || "", destination_location_id: "", quantity: "", batch_number: "", reason: "Location transfer" });
    setSelectedLevel(null);
    setItemSearch("");
    itemPaging.reset();
  };
  const submit = async (event) => {
    event.preventDefault();
    try {
      await transfer({ ...form, quantity_milli: Math.round(Number(form.quantity) * 1000) }).unwrap();
      onComplete?.();
      toast.success("Stock transferred");
      onOpenChange(false);
      reset();
    } catch (error) { toast.error(error?.data?.detail || "Could not transfer stock"); }
  };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Transfer stock" description="Search the selected source location and move available stock with a complete ledger trail."><form onSubmit={submit} className="space-y-4"><div className="grid gap-4 sm:grid-cols-2"><Field label="From"><Select required value={form.source_location_id} onValueChange={(value) => { setForm((current) => ({ ...current, source_location_id: value, item_id: "", destination_location_id: current.destination_location_id === value ? "" : current.destination_location_id })); setSelectedLevel(null); setItemSearch(""); itemPaging.reset(); }}><SelectTrigger><SelectValue placeholder="Source" /></SelectTrigger><SelectContent>{locations.map((location) => <SelectItem key={location.id} value={location.id}>{location.name}</SelectItem>)}</SelectContent></Select></Field><Field label="To"><Select required value={form.destination_location_id} onValueChange={(value) => setForm((current) => ({ ...current, destination_location_id: value }))}><SelectTrigger><SelectValue placeholder="Destination" /></SelectTrigger><SelectContent>{locations.filter((location) => location.id !== form.source_location_id).map((location) => <SelectItem key={location.id} value={location.id}>{location.name}</SelectItem>)}</SelectContent></Select></Field></div><Field label="Item"><RemoteCombobox
    value={form.item_id}
    selectedItem={selectedLevel}
    items={uniqueLevels}
    onValueChange={(value, level) => { setForm((current) => ({ ...current, item_id: value, batch_number: level.batch_number || "" })); setSelectedLevel(level); }}
    onSearchChange={setItemSearch}
    getValue={(level) => level.item.id}
    getLabel={(level) => level.item.name}
    getDescription={(level) => `${level.item.sku} · ${quantity(level.quantity_milli)} ${level.item.unit} available`}
    placeholder={form.source_location_id ? "Search available stock" : "Choose a source first"}
    searchPlaceholder="Search item, SKU, or batch"
    emptyText="No matching stock at this location"
    loading={itemQuery.isFetching}
    error={itemQuery.isError}
    hasMore={Boolean(itemQuery.data?.has_more)}
    onLoadMore={() => itemPaging.loadMore(itemQuery.data?.next_cursor)}
    onRetry={itemQuery.refetch}
    disabled={!form.source_location_id}
  /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Quantity"><Input required type="number" min="0.001" max={selectedLevel ? Number(selectedLevel.quantity_milli) / 1000 : undefined} step="0.001" value={form.quantity} onChange={(event) => setForm((current) => ({ ...current, quantity: event.target.value }))} /></Field><Field label="Batch"><Input value={form.batch_number} onChange={(event) => setForm((current) => ({ ...current, batch_number: event.target.value }))} /></Field></div><Field label="Reason"><Input required minLength={3} value={form.reason} onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))} /></Field><Button disabled={result.isLoading || !form.item_id || !form.destination_location_id} className="w-full">{result.isLoading ? "Transferring..." : "Transfer stock"}</Button></form></DrawerForm>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function quantity(value) { return (Number(value || 0) / 1000).toLocaleString("en-IN", { maximumFractionDigits: 3 }); }
function stockState(row) { if (row.quantity_milli <= 0) return "out_of_stock"; if (row.quantity_milli <= row.reorder_level_milli) return "low"; if (row.expires_on && new Date(`${row.expires_on}T00:00:00`) <= new Date(Date.now() + 30 * 86400000)) return "expiring"; return "available"; }
function adjustmentFor(row, mode) { return { mode, item: row.item, locationId: row.location_id, locationName: row.location.name, currentQuantityMilli: row.quantity_milli, reorderLevelMilli: row.reorder_level_milli, batchNumber: row.batch_number, expiresOn: row.expires_on }; }
