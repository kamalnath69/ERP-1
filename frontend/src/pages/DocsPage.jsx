import React, { useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, List, MagnifyingGlass } from "@phosphor-icons/react";

import PageMeta from "@/components/public/PageMeta";
import SafeMarkdown, { markdownHeadings } from "@/components/public/SafeMarkdown";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { docsBySlug, docsManifest } from "@/content/docs/manifest";

function groupedDocuments(documents = docsManifest) {
  return documents.reduce((groups, document) => {
    if (!groups[document.group]) groups[document.group] = [];
    groups[document.group].push(document);
    return groups;
  }, {});
}

function DocsNavigation({ activeSlug, documents, query, setQuery, onNavigate }) {
  const groups = groupedDocuments(documents);
  return <nav aria-label="Documentation">
    <Link to="/docs" onClick={onNavigate} className="mb-4 flex items-center justify-between rounded-lg px-3 py-2 text-sm font-semibold hover:bg-secondary">Documentation home<ArrowRight size={14} /></Link>
    <div className="relative mb-6">
      <MagnifyingGlass className="pointer-events-none absolute left-3 top-2.5 text-muted-foreground" size={15} />
      <Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-9 bg-card pl-9 text-xs" placeholder="Search guides" aria-label="Search documentation guides" />
    </div>
    {Object.entries(groups).map(([group, groupDocuments]) => <div key={group} className="mb-5">
      <div className="px-3 text-[10px] font-semibold uppercase tracking-[.16em] text-muted-foreground">{group}</div>
      <div className="mt-2 space-y-0.5">{groupDocuments.map((item) => <Link key={item.slug} to={`/docs/${item.slug}`} onClick={onNavigate} aria-current={item.slug === activeSlug ? "page" : undefined} className={`block rounded-r-lg border-l-2 px-3 py-2 text-sm transition-colors ${item.slug === activeSlug ? "border-primary bg-secondary font-semibold text-foreground" : "border-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground"}`}>{item.title}</Link>)}</div>
    </div>)}
    {!documents.length && <div className="rounded-lg bg-secondary/55 px-3 py-4 text-xs leading-5 text-muted-foreground">No guides match this search.</div>}
  </nav>;
}

export default function DocsPage() {
  const params = useParams();
  const slug = params["*"]?.replace(/^\/+|\/+$/g, "") || "";
  const [query, setQuery] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const document = slug ? docsBySlug[slug] : null;
  const results = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return docsManifest;
    return docsManifest.filter((item) => `${item.title} ${item.description} ${item.content}`.toLowerCase().includes(value));
  }, [query]);
  if (slug && !document) return <Navigate to="/docs" replace />;
  if (!document) return <DocsHome query={query} setQuery={setQuery} results={results} />;
  const position = docsManifest.findIndex((item) => item.slug === document.slug);
  const previous = docsManifest[position - 1];
  const next = docsManifest[position + 1];
  const headings = markdownHeadings(document.content);
  return <>
    <PageMeta title={`${document.title} documentation`} description={document.description} path={`/docs/${document.slug}`} />
    <div className="sticky top-16 z-40 border-b bg-background/95 backdrop-blur lg:hidden"><div className="mx-auto flex max-w-[1280px] items-center justify-between gap-4 px-4 py-3 sm:px-6"><span className="min-w-0 truncate text-sm font-semibold">{document.title}</span><Sheet open={mobileOpen} onOpenChange={setMobileOpen}><SheetTrigger asChild><button type="button" className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg border bg-card px-3 text-xs font-semibold"><List />Browse</button></SheetTrigger><SheetContent side="left" className="w-[86vw] max-w-[320px] overflow-y-auto p-0"><SheetHeader className="border-b px-5 py-5 text-left"><SheetTitle>Documentation</SheetTitle></SheetHeader><div className="p-4"><DocsNavigation activeSlug={document.slug} documents={results} query={query} setQuery={setQuery} onNavigate={() => setMobileOpen(false)} /></div></SheetContent></Sheet></div></div>
    <div className="mx-auto grid max-w-[1440px] lg:grid-cols-[232px_minmax(0,1fr)] xl:grid-cols-[232px_minmax(0,820px)_minmax(184px,1fr)]">
      <aside className="hidden border-r bg-surface-subtle/45 px-4 py-8 lg:block"><div className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto pr-1"><DocsNavigation activeSlug={document.slug} documents={results} query={query} setQuery={setQuery} /></div></aside>
      <div className="min-w-0 px-4 py-10 sm:px-7 lg:px-10 lg:py-14"><div className="flex flex-wrap items-center gap-2 text-xs font-medium text-muted-foreground"><Link to="/docs" className="hover:text-foreground">Docs</Link><span aria-hidden="true">/</span><span>{document.group}</span><span aria-hidden="true">/</span><span className="text-foreground">{document.title}</span></div><SafeMarkdown content={document.content} className="mt-7" /><nav className="mt-14 grid gap-3 border-t pt-7 sm:grid-cols-2" aria-label="Adjacent documentation">{previous ? <Link to={`/docs/${previous.slug}`} className="rounded-xl border bg-card p-4 transition-colors hover:bg-secondary/50"><span className="flex items-center gap-2 text-xs text-muted-foreground"><ArrowLeft />Previous</span><strong className="mt-2 block text-sm">{previous.title}</strong></Link> : <span />}{next && <Link to={`/docs/${next.slug}`} className="rounded-xl border bg-card p-4 text-right transition-colors hover:bg-secondary/50"><span className="flex items-center justify-end gap-2 text-xs text-muted-foreground">Next<ArrowRight /></span><strong className="mt-2 block text-sm">{next.title}</strong></Link>}</nav></div>
      <aside className="hidden px-6 py-14 xl:block">{headings.length > 0 && <div className="sticky top-24"><div className="text-[10px] font-semibold uppercase tracking-[.16em] text-muted-foreground">On this page</div><nav className="mt-4 space-y-2 border-l pl-4">{headings.map((heading) => <a key={heading.id} href={`#${heading.id}`} className={`block text-xs leading-5 text-muted-foreground hover:text-foreground ${heading.level === 3 ? "pl-2" : ""}`}>{heading.title}</a>)}</nav></div>}</aside>
    </div>
  </>;
}

function DocsHome({ query, setQuery, results }) {
  return <>
    <PageMeta title="Edvatiq documentation" description="Product, workspace, College ERP integration, security, and troubleshooting documentation for Edvatiq." path="/docs" />
    <section className="border-b bg-surface-subtle"><div className="mx-auto max-w-[1080px] px-4 py-14 sm:px-6 lg:px-8 lg:py-20"><div className="overline">Documentation</div><h1 className="mt-3 text-4xl font-semibold sm:text-5xl">Build a reliable Edvatiq workflow.</h1><p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">Guides for workspace setup, industry modules, permissions, College placement intelligence, and supported ERP integrations.</p><div className="relative mt-7 max-w-2xl"><MagnifyingGlass className="absolute left-4 top-3.5 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-12 bg-card pl-11" placeholder="Search documentation" aria-label="Search documentation" /></div></div></section>
    <section className="mx-auto max-w-[1080px] px-4 py-12 sm:px-6 lg:px-8 lg:py-16">{query && <div className="mb-5 text-sm text-muted-foreground">{results.length} {results.length === 1 ? "result" : "results"}</div>}<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{results.map((document) => <Link key={document.slug} to={`/docs/${document.slug}`} className="group rounded-2xl border bg-card p-5 shadow-sm transition-transform hover:-translate-y-0.5"><div className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted-foreground">{document.group}</div><h2 className="mt-4 text-lg font-semibold group-hover:text-accent">{document.title}</h2><p className="mt-2 text-xs leading-5 text-muted-foreground">{document.description}</p><span className="mt-5 inline-flex items-center gap-2 text-xs font-semibold">Read guide<ArrowRight className="transition-transform group-hover:translate-x-1" /></span></Link>)}</div>{!results.length && <div className="rounded-xl border bg-card p-6"><h2 className="font-semibold">No matching guide</h2><p className="mt-2 text-sm text-muted-foreground">Try a module, workflow, or integration term.</p></div>}</section>
  </>;
}
