import React, { useDeferredValue, useEffect, useState } from "react";
import { ArrowClockwise, Books, DownloadSimple, File, MagnifyingGlass, Trash, UploadSimple } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { CursorListFooter, DataTable, DrawerForm, EmptyState, ErrorState, FilterBar, MetricCard, PageHeader, PageShell, StatusBadge } from "@/components/system";
import { useDeleteDocumentMutation, useGetDocumentsQuery, useReindexDocumentMutation, useUploadDocumentMutation } from "@/store/api/workspaceApi";
import { QUERY_POLICIES } from "@/store/api/queryPolicies";
import { API_BASE } from "@/lib/http";
import useCursorPagination from "@/hooks/useCursorPagination";

export default function Documents() {
  const { can } = useAuth();
  const { locationId, entitlements, organization } = useBusiness();
  const isCollege = organization?.industry === "college";
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const deferredSearch = useDeferredValue(search.trim());
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const pageKey = JSON.stringify({ q: deferredSearch, status });
  const paging = useCursorPagination(pageKey);
  const query = useGetDocumentsQuery({ q: deferredSearch, status, cursor: paging.cursor, limit: 25 }, QUERY_POLICIES.collaborative);
  const [reindex] = useReindexDocumentMutation();
  const [remove, removeState] = useDeleteDocumentMutation();
  const { accept: acceptPage } = paging;
  useEffect(() => { acceptPage(query.data); }, [acceptPage, query.data]);
  const documents = paging.items;
  const summary = query.data?.summary || {};
  const metrics = [
    { id: "files", label: "Documents", value: summary.files || 0 },
    { id: "ready", label: "Knowledge ready", value: summary.ready || 0 },
    { id: "processing", label: "Processing", value: summary.processing || 0 },
    { id: "storage", label: "Storage used", value: summary.storage_bytes || 0, format: "bytes" },
  ];
  if (query.isError && !query.data) return <PageShell><ErrorState title="Documents could not be loaded" description={query.error?.data?.detail} retry={query.refetch} /></PageShell>;
  const knowledgeEnabled = Boolean(entitlements?.values?.["documents.knowledge"]);
  const columns = [
    { key: "name", label: "Document", render: (row) => <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-secondary"><File /></span><span><span className="block max-w-xs truncate font-semibold">{row.name}</span><span className="mt-1 block text-xs text-muted-foreground">{fileType(row.content_type)} · {formatBytes(row.size_bytes)}</span></span></div> },
    { key: "entity_type", label: "Linked to", render: (row) => row.entity_type ? <span className="capitalize">{row.entity_type === "client" && isCollege ? "student" : row.entity_type}</span> : isCollege ? "College knowledge" : "Business knowledge" },
    { key: "visibility", label: "Visibility", render: (row) => <StatusBadge status={row.visibility} /> },
    { key: "status", label: "Processing", render: (row) => <div><StatusBadge status={row.status} />{row.status === "failed" && row.error && <div className="mt-1 max-w-xs text-xs text-danger">{row.error}</div>}</div> },
    { key: "updated_at", label: "Updated", render: (row) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(row.updated_at)) },
    { key: "actions", label: "", render: (row) => <div className="flex justify-end gap-1"><Button asChild size="sm" variant="ghost"><a href={`${API_BASE}/documents/${row.id}/download`} aria-label={`Download ${row.name}`}><DownloadSimple /></a></Button>{can("documents.manage") && knowledgeEnabled && <Button size="sm" variant="ghost" disabled={row.status === "processing"} onClick={async () => { try { await reindex(row.id).unwrap(); toast.success("Document queued for processing"); } catch (error) { toast.error(error?.data?.detail || "Could not reprocess document"); } }} aria-label={`Reprocess ${row.name}`}><ArrowClockwise /></Button>}{can("documents.manage") && <Button size="sm" variant="ghost" onClick={() => setDeleting(row)} aria-label={`Delete ${row.name}`}><Trash /></Button>}</div> },
  ];
  const isFilteredEmpty = Boolean(search.trim() || status !== "all");
  return <PageShell className="reveal">
    <PageHeader eyebrow="Secure knowledge" title="Documents" description={isCollege ? "Private academic, placement, policy, and student-linked files with controlled AI knowledge access." : "Private business files, entity links, processing health, and AI knowledge readiness."} actions={can("documents.manage") && <Button onClick={() => setUploadOpen(true)}><UploadSimple className="mr-2" />Upload document</Button>} />
    {summary.files > 0 && <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metrics.map((metric) => <MetricCard key={metric.id} metric={metric} />)}</div>}
    {(summary.files > 0 || isFilteredEmpty) && <FilterBar><div className="relative flex-1"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input className="border-0 bg-transparent pl-10 shadow-none" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search documents" /></div><Select value={status} onValueChange={setStatus}><SelectTrigger className="w-full sm:w-44"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All states</SelectItem><SelectItem value="ready">Knowledge ready</SelectItem><SelectItem value="pending">Pending</SelectItem><SelectItem value="processing">Processing</SelectItem><SelectItem value="failed">Failed</SelectItem></SelectContent></Select></FilterBar>}
    <DataTable loading={query.isLoading && !documents.length} rows={documents} columns={columns} empty={<EmptyState variant={isFilteredEmpty ? "filtered" : "page"} alignment="left" icon={Books} title={isFilteredEmpty ? "No documents match this view" : "Create your private document library"} description={isFilteredEmpty ? "Clear the search and processing-state filter to see every document." : isCollege ? "Upload placement policies, student forms, academic references, or employer material. Files remain private while processing." : "Upload policies, price lists, forms, or reference material. Files remain private while processing."} primaryAction={isFilteredEmpty ? <Button variant="outline" onClick={() => { setSearch(""); setStatus("all"); }}>Clear filters</Button> : can("documents.manage") ? <Button onClick={() => setUploadOpen(true)}><UploadSimple className="mr-2" />Upload document</Button> : null} steps={isFilteredEmpty ? [] : [{ title: "Choose a file" }, { title: "Set visibility" }, { title: "Use securely" }]} />} />
    {(documents.length > 0 || query.data?.has_more) && <CursorListFooter count={documents.length} noun="documents" hasMore={Boolean(query.data?.has_more)} loading={query.isFetching} error={query.isError} onLoadMore={() => paging.loadMore(query.data?.next_cursor)} onRetry={query.refetch} />}
    <UploadDrawer open={uploadOpen} onOpenChange={setUploadOpen} locationId={locationId} />
    <AlertDialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(null)}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Delete this document?</AlertDialogTitle><AlertDialogDescription>The file and its searchable knowledge will be removed. This cannot be undone.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Keep document</AlertDialogCancel><AlertDialogAction disabled={removeState.isLoading} onClick={async () => { try { await remove(deleting.id).unwrap(); toast.success("Document deleted"); setDeleting(null); } catch (error) { toast.error(error?.data?.detail || "Could not delete document"); } }}>Delete document</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </PageShell>;
}

function UploadDrawer({ open, onOpenChange, locationId }) {
  const [file, setFile] = useState(null);
  const [visibility, setVisibility] = useState("team");
  const [upload, result] = useUploadDocumentMutation();
  const submit = async (event) => { event.preventDefault(); if (!file) return; const data = new FormData(); data.append("file", file); if (locationId) data.append("location_id", locationId); data.append("visibility", visibility); try { await upload(data).unwrap(); toast.success("Document uploaded for processing"); setFile(null); onOpenChange(false); } catch (error) { toast.error(error?.data?.detail || "Could not upload document"); } };
  return <DrawerForm open={open} onOpenChange={onOpenChange} title="Upload document" description="Files remain private and are checked before they become searchable."><form onSubmit={submit} className="space-y-5"><div className="rounded-2xl border border-dashed p-6 text-center"><UploadSimple className="mx-auto text-muted-foreground" size={30} /><Label htmlFor="document-file" className="mt-4 block cursor-pointer font-semibold">Choose PDF, DOCX, TXT, JPG, or PNG</Label><p className="mt-2 text-xs text-muted-foreground">Maximum 20 MB</p><Input id="document-file" className="mt-4" type="file" accept=".pdf,.docx,.txt,.jpg,.jpeg,.png" required onChange={(event) => setFile(event.target.files?.[0] || null)} />{file && <p className="mt-3 text-sm">{file.name} · {formatBytes(file.size)}</p>}</div><div className="space-y-2"><Label>Who can see it</Label><Select value={visibility} onValueChange={setVisibility}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="team">Team</SelectItem><SelectItem value="managers">Managers</SelectItem><SelectItem value="author_only">Only me</SelectItem></SelectContent></Select></div><Button disabled={!file || result.isLoading} className="w-full">{result.isLoading ? "Uploading..." : "Upload securely"}</Button></form></DrawerForm>;
}

function fileType(value = "") { if (value.includes("pdf")) return "PDF"; if (value.includes("wordprocessing")) return "DOCX"; if (value.startsWith("image/")) return "Image"; if (value === "text/plain") return "Text"; return "File"; }
function formatBytes(value = 0) { const bytes = Number(value); if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / 1024 ** 2).toFixed(1)} MB`; }
