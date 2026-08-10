import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, MagnifyingGlass, Minus, Plus, Receipt, ShoppingCart, Trash, Wallet,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { clientLabel } from "@/app/routeManifest";
import {
  CursorListFooter, DataTable, DetailHero, DrawerForm, EmptyState, ErrorState, FilterBar, MetricStrip,
  PageHeader, PageShell, RemoteCombobox, StatusBadge, Surface, formatMetric,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  useCreateSaleMutation, useGetSaleDetailQuery, useGetSalesDirectoryQuery,
} from "@/features/sales/salesApi";
import { useGetCatalogDirectoryQuery } from "@/features/catalog/catalogApi";
import { PaymentDrawer, VoidInvoiceDrawer } from "@/features/sales/InvoiceActions";
import { useGetClientDirectoryQuery } from "@/store/api/workspaceApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { cn } from "@/lib/utils";
import useCursorPagination from "@/hooks/useCursorPagination";


export default function Sales() {
  const { invoiceId } = useParams();
  const { organization } = useBusiness();
  if (!invoiceId && organization?.industry === "college") {
    return <Navigate to="/app/college?section=clearance" replace />;
  }
  return invoiceId ? <InvoiceProfile invoiceId={invoiceId} /> : <SalesDirectory />;
}


function SalesDirectory() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const { locationId, organization } = useBusiness();
  const entityName = clientLabel(organization?.industry, false);
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [status, setStatus] = useState("all");
  const [range, setRange] = useState("30");
  const [checkoutOpen, setCheckoutOpen] = useState(() => new URLSearchParams(window.location.search).get("new") === "1");
  const [paying, setPaying] = useState(null);
  const startsAt = useMemo(
    () => (range === "all" ? undefined : new Date(Date.now() - Number(range) * 86400000).toISOString()),
    [range],
  );
  const pageKey = JSON.stringify({ locationId, q, status, startsAt });
  const paging = useCursorPagination(pageKey);
  const query = useGetSalesDirectoryQuery(
    { locationId, q, status, startsAt, cursor: paging.cursor, limit: 25 },
    withSkip(QUERY_POLICIES.operational, !locationId),
  );
  const data = query.data;
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(data); }, [acceptPage, data]);
  const rows = paging.items;
  const metrics = data?.summary ? [
    { id: "billed", label: "Billed", value: data.summary.billed_paise, format: "money" },
    { id: "collected", label: "Collected", value: data.summary.collected_paise, format: "money" },
    { id: "outstanding", label: "Outstanding", value: data.summary.outstanding_paise, format: "money", tone: data.summary.outstanding_paise ? "warning" : "neutral" },
    { id: "invoices", label: "Invoices", value: data.summary.invoice_count },
  ] : [];

  if (query.isError && !data) return <PageShell><ErrorState title="Sales could not be loaded" description={query.error?.data?.detail} retry={query.refetch} /></PageShell>;

  const columns = [
    { key: "invoice", label: "Invoice", render: (row) => <div><div className="font-mono font-semibold">{row.invoice_number}</div><div className="mt-1 text-xs text-muted-foreground">{row.items_preview?.join(", ") || "No line preview"}{row.line_count > 3 ? ` +${row.line_count - 3}` : ""}</div></div> },
    { key: "client", label: entityName, render: (row) => row.client?.display_name || "Walk-in" },
    { key: "created_at", label: "Issued", render: (row) => dateTime(row.issued_at || row.created_at) },
    { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
    { key: "total_paise", label: "Total", cellClassName: "text-right font-semibold", render: (row) => money(row.total_paise) },
    { key: "balance", label: "Balance", cellClassName: "text-right", render: (row) => <span className={row.balance_paise ? "text-warning" : "text-muted-foreground"}>{money(row.balance_paise)}</span> },
    { key: "action", label: "", render: (row) => can("payments.record") && row.balance_paise > 0 && !["draft", "void", "refunded"].includes(row.status) ? <Button size="sm" variant="outline" onClick={(event) => { event.stopPropagation(); setPaying(row); }}>Record payment</Button> : null },
  ];
  const isFilteredEmpty = Boolean(q || status !== "all" || range !== "30");

  return <PageShell className="reveal">
    <PageHeader
      eyebrow="Checkout and invoices"
      title="Sales"
      description="Issue GST-ready invoices, collect balances, and inspect every item snapshot from one financial workspace."
      actions={can("sales.manage") ? <Button onClick={() => setCheckoutOpen(true)}><ShoppingCart className="mr-2" />New sale</Button> : null}
    />
    <MetricStrip metrics={metrics} loading={query.isLoading && !data} />
    <FilterBar>
      <div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} className="border-0 bg-transparent pl-10 shadow-none" placeholder={`Search invoice, item, or ${entityName.toLowerCase()}`} /></div>
      <Select value={status} onValueChange={setStatus}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All statuses</SelectItem>{["draft", "issued", "partially_paid", "paid", "void", "refunded"].map((value) => <SelectItem key={value} value={value}>{sentence(value)}</SelectItem>)}</SelectContent></Select>
      <Select value={range} onValueChange={setRange}><SelectTrigger className="w-full sm:w-40"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="7">Last 7 days</SelectItem><SelectItem value="30">Last 30 days</SelectItem><SelectItem value="90">Last 90 days</SelectItem><SelectItem value="all">All time</SelectItem></SelectContent></Select>
      {query.isFetching && data && <span className="px-2 text-xs text-muted-foreground">Refreshing...</span>}
    </FilterBar>
    <DataTable
      columns={columns}
      rows={rows}
      loading={query.isLoading && !rows.length}
      onRowClick={(row) => navigate(`/app/sales/${row.id}`, { state: { from: "/app/sales" } })}
      empty={<EmptyState variant={isFilteredEmpty ? "filtered" : "page"} alignment="left" icon={Receipt} title={isFilteredEmpty ? "No invoices match this view" : "Create your first invoice"} description={isFilteredEmpty ? "Clear the search, status, and date filters to return to recent sales." : `Create a sale for a ${entityName.toLowerCase()} or walk-in and choose how payment will be recorded.`} primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setSearch(""); setStatus("all"); setRange("30"); }}>Clear filters</Button> : can("sales.manage") ? <Button onClick={() => setCheckoutOpen(true)}>Create first sale</Button> : null} steps={isFilteredEmpty ? [] : [{ title: "Add items" }, { title: "Issue invoice" }, { title: "Record payment" }]} />}
    />
    {(rows.length > 0 || data?.has_more) && <CursorListFooter count={rows.length} noun="invoices" hasMore={Boolean(data?.has_more)} loading={query.isFetching} error={query.isError} onLoadMore={() => paging.loadMore(data?.next_cursor)} onRetry={query.refetch} />}
    <CheckoutDrawer open={checkoutOpen} onOpenChange={setCheckoutOpen} locationId={locationId} entityName={entityName} onCreated={(invoice) => navigate(`/app/sales/${invoice.id}`)} />
    <PaymentDrawer invoice={paying} onOpenChange={(open) => !open && setPaying(null)} />
  </PageShell>;
}


function CheckoutDrawer({ open, onOpenChange, locationId, entityName, onCreated }) {
  const [createSale, createState] = useCreateSaleMutation();
  const [itemSearch, setItemSearch] = useState("");
  const deferredItemSearch = useDeferredValue(itemSearch.trim());
  const [clientSearch, setClientSearch] = useState("");
  const deferredClientSearch = useDeferredValue(clientSearch.trim());
  const [clientId, setClientId] = useState("walk-in");
  const [selectedClient, setSelectedClient] = useState(WALK_IN_CLIENT);
  const [cart, setCart] = useState([]);
  const [notes, setNotes] = useState("");
  const [interstate, setInterstate] = useState("no");
  const itemPaging = useCursorPagination(JSON.stringify({ open, q: deferredItemSearch }));
  const clientPaging = useCursorPagination(JSON.stringify({ open, locationId, q: deferredClientSearch }));
  const catalogQuery = useGetCatalogDirectoryQuery({
    q: deferredItemSearch,
    state: "active",
    cursor: itemPaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.reference, !open));
  const clientsQuery = useGetClientDirectoryQuery({
    locationId,
    q: deferredClientSearch,
    segment: "active",
    cursor: clientPaging.cursor,
    limit: 25,
  }, withSkip(QUERY_POLICIES.reference, !open || !locationId));
  const { accept: acceptItems } = itemPaging;
  const { accept: acceptClients } = clientPaging;
  useEffect(() => { acceptItems(catalogQuery.data); }, [acceptItems, catalogQuery.data]);
  useEffect(() => { acceptClients(clientsQuery.data); }, [acceptClients, clientsQuery.data]);
  const items = itemPaging.items.length ? itemPaging.items : catalogQuery.data?.items || [];
  const clientOptions = useMemo(() => [
    WALK_IN_CLIENT,
    ...(clientPaging.items.length ? clientPaging.items : clientsQuery.data?.items || []),
  ], [clientPaging.items, clientsQuery.data?.items]);
  const total = cart.reduce((sum, line) => sum + previewTotal(line.item, line.quantity), 0);
  const add = (item) => setCart((current) => {
    const match = current.find((line) => line.item.id === item.id);
    return match ? current.map((line) => line.item.id === item.id ? { ...line, quantity: line.quantity + 1 } : line) : [...current, { item, quantity: 1 }];
  });
  const setQuantity = (itemId, quantity) => setCart((current) => current.map((line) => line.item.id === itemId ? { ...line, quantity: Math.max(1, quantity) } : line));
  const reset = () => {
    setCart([]);
    setClientId("walk-in");
    setSelectedClient(WALK_IN_CLIENT);
    setNotes("");
    setInterstate("no");
    setItemSearch("");
    setClientSearch("");
    itemPaging.reset();
    clientPaging.reset();
  };
  const submit = async (event) => {
    event.preventDefault();
    if (!cart.length) return;
    try {
      const invoice = await createSale({
        location_id: locationId,
        client_id: clientId === "walk-in" ? null : clientId,
        lines: cart.map((line) => ({ item_id: line.item.id, quantity_milli: line.quantity * 1000, discount_paise: 0 })),
        discount_paise: 0,
        interstate: interstate === "yes",
        notes: notes || null,
        issue: true,
        idempotency_key: crypto.randomUUID(),
      }).unwrap();
      toast.success("Invoice issued");
      reset();
      onOpenChange(false);
      onCreated(invoice);
    } catch (error) {
      toast.error(error?.data?.detail || "Invoice could not be issued. Your cart is still here.");
    }
  };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Quick checkout" description="Choose items, confirm who is buying, and review the live total before issuing.">
    <form onSubmit={submit} className="space-y-6">
      <Field label={entityName}><RemoteCombobox
        value={clientId}
        selectedItem={selectedClient}
        items={clientOptions}
        onValueChange={(value, item) => { setClientId(value); setSelectedClient(item); }}
        onSearchChange={setClientSearch}
        getLabel={(client) => client.display_name || `${client.first_name || ""} ${client.last_name || ""}`.trim()}
        getDescription={(client) => client.id === "walk-in" ? "Issue without linking a profile" : client.client_number}
        placeholder={`Choose ${entityName.toLowerCase()}`}
        searchPlaceholder={`Search ${entityName.toLowerCase()} name or number`}
        loading={clientsQuery.isFetching}
        error={clientsQuery.isError}
        hasMore={Boolean(clientsQuery.data?.has_more)}
        onLoadMore={() => clientPaging.loadMore(clientsQuery.data?.next_cursor)}
        onRetry={clientsQuery.refetch}
        disabled={!open || !locationId}
      /></Field>
      <Field label="Add products or services"><div className="relative"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={itemSearch} onChange={(event) => setItemSearch(event.target.value)} className="pl-10" placeholder="Search name or SKU" /></div></Field>
      <div className="grid max-h-56 gap-2 overflow-y-auto premium-scrollbar sm:grid-cols-2">
        {catalogQuery.isLoading && !items.length ? Array.from({ length: 4 }, (_, index) => <div key={index} className="h-24 animate-pulse rounded-2xl bg-secondary" />) : items.map((item) => <button type="button" key={item.id} onClick={() => add(item)} className="surface-card surface-interactive p-4 text-left"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold">{item.name}</div><div className="mt-1 text-xs text-muted-foreground">{item.sku} · {sentence(item.item_type)}</div></div><Plus /></div><div className="mt-3 font-display text-xl font-semibold">{money(previewTotal(item, 1))}</div></button>)}
        {!catalogQuery.isLoading && !items.length && <div className="col-span-full rounded-xl bg-secondary/50 px-4 py-6 text-center text-sm text-muted-foreground">No products or services match this search.</div>}
      </div>
      {catalogQuery.data?.has_more && <Button type="button" variant="outline" size="sm" className="w-full" disabled={catalogQuery.isFetching} onClick={() => itemPaging.loadMore(catalogQuery.data?.next_cursor)}>{catalogQuery.isFetching ? "Loading..." : "Load more products and services"}</Button>}
      <div className="space-y-2">
        {!cart.length ? <EmptyState compact icon={ShoppingCart} title="Your cart is empty" description="Select a product or service above." /> : cart.map((line) => <Surface key={line.item.id} className="p-4"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold">{line.item.name}</div><div className="mt-1 text-xs text-muted-foreground">{money(previewTotal(line.item, line.quantity))}</div></div><Button type="button" size="icon" variant="ghost" onClick={() => setCart((current) => current.filter((row) => row.item.id !== line.item.id))} aria-label={`Remove ${line.item.name}`}><Trash /></Button></div><div className="mt-3 flex items-center gap-2"><Button type="button" size="icon" variant="outline" onClick={() => setQuantity(line.item.id, line.quantity - 1)} aria-label="Decrease quantity"><Minus /></Button><span className="min-w-9 text-center font-mono">{line.quantity}</span><Button type="button" size="icon" variant="outline" onClick={() => setQuantity(line.item.id, line.quantity + 1)} aria-label="Increase quantity"><Plus /></Button></div></Surface>)}
      </div>
      <div className="grid gap-4 sm:grid-cols-2"><Field label="Tax treatment"><Select value={interstate} onValueChange={setInterstate}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="no">CGST + SGST</SelectItem><SelectItem value="yes">IGST</SelectItem></SelectContent></Select></Field><Field label="Invoice note"><Textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} placeholder="Optional note" /></Field></div>
      <Surface className="flex items-center justify-between p-5"><div><div className="text-sm text-muted-foreground">Estimated total</div><div className="mt-1 text-xs text-muted-foreground">Final tax is calculated securely when issued.</div></div><div className="font-display text-3xl font-semibold">{money(total)}</div></Surface>
      <Button disabled={createState.isLoading || !cart.length || !locationId} className="w-full">{createState.isLoading ? "Issuing invoice..." : "Review and issue invoice"}</Button>
    </form>
  </DrawerForm>;
}

const WALK_IN_CLIENT = { id: "walk-in", display_name: "Walk-in" };


function InvoiceProfile({ invoiceId }) {
  const navigate = useNavigate();
  const { can } = useAuth();
  const { organization } = useBusiness();
  const isCollege = organization?.industry === "college";
  const entityName = clientLabel(organization?.industry, false);
  const query = useGetSaleDetailQuery(invoiceId, QUERY_POLICIES.operational);
  const [paying, setPaying] = useState(null);
  const [voiding, setVoiding] = useState(null);
  const invoice = query.data;
  if (query.isLoading) return <PageShell><div className="h-80 animate-pulse rounded-3xl bg-secondary" /></PageShell>;
  if (query.isError || !invoice) return <PageShell><Button variant="ghost" onClick={() => navigate(isCollege ? "/app/college?section=clearance" : "/app/sales")}><ArrowLeft className="mr-2" />{isCollege ? "Back to internship clearance" : "Back to sales"}</Button><ErrorState title="Invoice could not be opened" description={query.error?.data?.detail} retry={query.refetch} /></PageShell>;
  const tax = invoice.cgst_paise + invoice.sgst_paise + invoice.igst_paise;
  return <PageShell className="reveal">
    <Button variant="ghost" className="w-fit" onClick={() => navigate(-1)}><ArrowLeft className="mr-2" />Back</Button>
    <DetailHero
      avatar={<div className="detail-avatar"><Receipt size={30} /></div>}
      eyebrow={isCollege ? "Student fee record" : "Invoice"}
      title={invoice.invoice_number}
      subtitle={`${invoice.location?.name || "Location"} · ${dateTime(invoice.issued_at || invoice.created_at)}`}
      badges={<><StatusBadge status={invoice.status} />{invoice.client ? <StatusBadge status="neutral" label={`${entityName}: ${invoice.client.display_name}`} /> : <StatusBadge status="neutral" label="Walk-in" />}</>}
      metrics={[
        { label: "Total", value: invoice.total_paise, format: "money" },
        { label: "Paid", value: invoice.paid_paise, format: "money" },
        { label: "Balance", value: invoice.balance_paise, format: "money" },
        { label: "Tax", value: tax, format: "money" },
      ]}
      actions={<>{can("payments.record") && invoice.balance_paise > 0 && !["draft", "void", "refunded"].includes(invoice.status) && <Button onClick={() => setPaying(invoice)}><Wallet className="mr-2" />Record payment</Button>}{can("sales.manage") && invoice.voidable && <Button variant="outline" className="text-danger" onClick={() => setVoiding(invoice)}>Void invoice</Button>}</>}
    />
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,.7fr)]">
      <Surface className="overflow-hidden"><div className="border-b p-5"><h2 className="font-display text-2xl font-semibold">{isCollege ? "Fee obligation" : "Items"}</h2><p className="mt-1 text-sm text-muted-foreground">{isCollege ? "This record is used only for verified fee completion and internship clearance." : "Prices and tax rates are preserved exactly as issued."}</p></div><div className="divide-y">{invoice.lines.map((line) => <div key={line.id} className="grid gap-3 p-5 sm:grid-cols-[1fr_auto] sm:items-center"><div><div className="font-semibold">{line.item_name}</div><div className="mt-1 text-xs text-muted-foreground">{line.sku || (isCollege ? "College fee" : "No SKU")} · {quantity(line.quantity_milli)} × {money(line.unit_price_paise)} · GST {(line.tax_rate_bps / 100).toLocaleString("en-IN")}%</div></div><div className="text-right"><div className="font-semibold">{money(line.total_paise)}</div>{line.discount_paise > 0 && <div className="mt-1 text-xs text-positive">Discount {money(line.discount_paise)}</div>}</div></div>)}</div><div className="border-t bg-surface-subtle p-5"><MoneyRow label="Taxable subtotal" value={invoice.subtotal_paise} /><MoneyRow label="CGST" value={invoice.cgst_paise} hidden={!invoice.cgst_paise} /><MoneyRow label="SGST" value={invoice.sgst_paise} hidden={!invoice.sgst_paise} /><MoneyRow label="IGST" value={invoice.igst_paise} hidden={!invoice.igst_paise} /><MoneyRow label="Total" value={invoice.total_paise} strong /></div></Surface>
      <div className="space-y-6"><Surface className="p-5"><h2 className="font-display text-2xl font-semibold">Payment history</h2>{invoice.payments.length ? <div className="mt-4 divide-y">{invoice.payments.map((payment) => <div key={payment.id} className="flex items-center justify-between gap-4 py-4"><div><StatusBadge status={payment.status} /><div className="mt-2 text-xs text-muted-foreground">{sentence(payment.method)} · {dateTime(payment.created_at)}</div></div><div className="font-semibold">{money(payment.amount_paise)}</div></div>)}</div> : <p className="mt-4 text-sm text-muted-foreground">No payments have been recorded.</p>}</Surface>{invoice.notes && <Surface className="p-5"><h2 className="font-display text-xl font-semibold">Invoice note</h2><p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{invoice.notes}</p></Surface>}</div>
    </div>
    <PaymentDrawer invoice={paying} onOpenChange={(open) => !open && setPaying(null)} />
    <VoidInvoiceDrawer invoice={voiding} onOpenChange={(open) => !open && setVoiding(null)} />
  </PageShell>;
}


function MoneyRow({ label, value, strong, hidden }) {
  if (hidden) return null;
  return <div className={cn("flex items-center justify-between gap-4 py-1.5 text-sm", strong && "mt-2 border-t pt-4 font-display text-xl font-semibold")}><span>{label}</span><span>{money(value)}</span></div>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function money(paise) { return formatMetric(paise, "money"); }
function quantity(value) { return (Number(value || 0) / 1000).toLocaleString("en-IN", { maximumFractionDigits: 3 }); }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function dateTime(value) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value)) : "Not issued"; }
function previewTotal(item, quantity) { const gross = item.price_paise * quantity; return item.tax_inclusive ? gross : gross + Math.round(gross * item.tax_rate_bps / 10000); }
