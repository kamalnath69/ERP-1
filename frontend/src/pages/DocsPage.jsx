import React, { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, BookOpen, CircleNotch, MagnifyingGlass } from "@phosphor-icons/react";

import PageMeta from "@/components/public/PageMeta";
import PublicDocumentLayout, {
  DocumentNavGroup, DocumentNavLink, DocumentOverview, DocumentSkeleton,
} from "@/components/public/PublicDocumentLayout";
import SafeMarkdown, { markdownHeadings } from "@/components/public/SafeMarkdown";
import { Input } from "@/components/ui/input";
import {
  docsBySlug, docsManifest, filterDocumentationMetadata,
  loadDocumentationContent, searchDocumentation,
} from "@/content/docs/manifest";
import { withoutMarkdownTitle } from "@/lib/legalDocuments";

function groupedDocuments(documents = docsManifest) {
  return documents.reduce((groups, document) => {
    if (!groups[document.group]) groups[document.group] = [];
    groups[document.group].push(document);
    return groups;
  }, {});
}

function DocsNavigation({ activeSlug, documents, query, setQuery, onNavigate, homeActive = false, showSearch = true, searching = false }) {
  const groups = groupedDocuments(documents);
  return <><div className="px-3 py-2"><div className="overline">Knowledge base</div><p className="mt-2 text-xs leading-5 text-muted-foreground">Product guidance and integration reference</p></div><nav aria-label="Documentation" className="mt-3">
    <DocumentNavLink to="/docs" onClick={onNavigate} active={homeActive} icon={BookOpen} title="Documentation home" meta="Browse every guide" />
    {showSearch && <div className="relative mx-1 mb-6 mt-4">
      <MagnifyingGlass className="pointer-events-none absolute left-3 top-2.5 text-muted-foreground" size={15} />
      <Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-9 bg-card pl-9 text-xs" placeholder="Search guides" aria-label="Search documentation guides" />
    </div>}
    {Object.entries(groups).map(([group, groupDocuments]) => <DocumentNavGroup key={group} label={group}>{groupDocuments.map((item) => <DocumentNavLink key={item.slug} to={`/docs/${item.slug}`} onClick={onNavigate} active={item.slug === activeSlug} title={item.title} />)}</DocumentNavGroup>)}
    {searching && <div role="status" className="mx-1 flex items-center gap-2 rounded-lg bg-secondary/55 px-3 py-3 text-xs text-muted-foreground"><CircleNotch className="animate-spin" />Searching guide content</div>}
    {!searching && !documents.length && <div className="rounded-lg bg-secondary/55 px-3 py-4 text-xs leading-5 text-muted-foreground">No guides match this search.</div>}
  </nav></>;
}

export default function DocsPage() {
  const params = useParams();
  const slug = params["*"]?.replace(/^\/+|\/+$/g, "") || "";
  const [query, setQuery] = useState("");
  const [searchState, setSearchState] = useState({ results: docsManifest, loading: false });
  const [articleState, setArticleState] = useState({ slug: "", content: "", loading: false, error: "" });
  const [articleAttempt, setArticleAttempt] = useState(0);
  const document = slug ? docsBySlug[slug] : null;

  useEffect(() => {
    const value = query.trim();
    if (!value) {
      setSearchState({ results: docsManifest, loading: false });
      return undefined;
    }

    let active = true;
    const metadataMatches = filterDocumentationMetadata(value);
    setSearchState({ results: metadataMatches, loading: true });
    const timer = window.setTimeout(() => {
      searchDocumentation(value)
        .then((results) => { if (active) setSearchState({ results, loading: false }); })
        .catch(() => { if (active) setSearchState({ results: metadataMatches, loading: false }); });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    if (!document) {
      setArticleState({ slug: "", content: "", loading: false, error: "" });
      return undefined;
    }
    let active = true;
    setArticleState({ slug: document.slug, content: "", loading: true, error: "" });
    loadDocumentationContent(document.slug)
      .then((content) => { if (active) setArticleState({ slug: document.slug, content, loading: false, error: "" }); })
      .catch(() => { if (active) setArticleState({ slug: document.slug, content: "", loading: false, error: "This guide could not be loaded." }); });
    return () => { active = false; };
  }, [document, articleAttempt]);

  const results = query.trim() ? searchState.results : docsManifest;
  const searching = Boolean(query.trim()) && searchState.loading;
  const articleIsCurrent = Boolean(document && articleState.slug === document.slug);
  const articleLoading = Boolean(document && (!articleIsCurrent || articleState.loading));
  const markdown = useMemo(() => withoutMarkdownTitle(articleIsCurrent ? articleState.content : ""), [articleIsCurrent, articleState.content]);
  const headings = useMemo(() => markdownHeadings(markdown), [markdown]);

  if (slug && !document) return <Navigate to="/docs" replace />;
  if (!document) return <DocsHome query={query} setQuery={setQuery} results={results} searching={searching} />;
  const position = docsManifest.findIndex((item) => item.slug === document.slug);
  const previous = docsManifest[position - 1];
  const next = docsManifest[position + 1];
  return <>
    <PageMeta title={`${document.title} documentation`} description={document.description} path={`/docs/${document.slug}`} />
    <PublicDocumentLayout
      title={document.title}
      eyebrow={`${document.group} guide`}
      meta="Edvatiq product documentation"
      breadcrumbs={[{ label: "Resources", to: "/docs" }, { label: "Documentation", to: "/docs" }, { label: document.group }, { label: document.title }]}
      navigationTitle="Documentation"
      navigationLabel="Documentation"
      renderNavigation={({ close }) => <DocsNavigation activeSlug={document.slug} documents={results} query={query} setQuery={setQuery} onNavigate={close} searching={searching} />}
      headings={headings}
      showActions={articleIsCurrent && !articleState.error}
      actionsLoading={articleLoading}
      contentsLoading={articleLoading}
    >
      <div className="mx-auto max-w-3xl" aria-busy={articleLoading}>
        {articleLoading ? <DocumentSkeleton /> : articleState.error ? <div className="py-10"><div className="grid h-11 w-11 place-items-center rounded-xl border bg-secondary"><BookOpen /></div><h2 className="mt-5 text-2xl font-semibold">Guide unavailable</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{articleState.error} Check your connection and try again.</p><button type="button" onClick={() => setArticleAttempt((attempt) => attempt + 1)} className="mt-5 inline-flex h-10 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground">Try again</button></div> : <>
        <DocumentOverview eyebrow="Guide overview">{document.description}</DocumentOverview>
        <SafeMarkdown content={markdown} className="document-prose" />
        <nav className="mt-14 grid gap-3 border-t pt-7 sm:grid-cols-2" aria-label="Adjacent documentation">{previous ? <Link to={`/docs/${previous.slug}`} className="rounded-xl border bg-card p-4 transition-colors hover:bg-secondary/50"><span className="flex items-center gap-2 text-xs text-muted-foreground"><ArrowLeft />Previous</span><strong className="mt-2 block text-sm">{previous.title}</strong></Link> : <span />}{next && <Link to={`/docs/${next.slug}`} className="rounded-xl border bg-card p-4 text-right transition-colors hover:bg-secondary/50"><span className="flex items-center justify-end gap-2 text-xs text-muted-foreground">Next<ArrowRight /></span><strong className="mt-2 block text-sm">{next.title}</strong></Link>}</nav>
        </>}
      </div>
    </PublicDocumentLayout>
  </>;
}

function DocsHome({ query, setQuery, results, searching }) {
  const groups = groupedDocuments(results);
  return <>
    <PageMeta title="Edvatiq documentation" description="Product, workspace, College ERP integration, security, and troubleshooting documentation for Edvatiq." path="/docs" />
    <PublicDocumentLayout
      title="Documentation"
      eyebrow="Knowledge base"
      meta="Product guidance, operating workflows, and supported integration reference"
      breadcrumbs={[{ label: "Resources" }, { label: "Documentation" }]}
      navigationTitle="Documentation"
      navigationLabel="Documentation"
      renderNavigation={({ close }) => <DocsNavigation homeActive documents={docsManifest} query={query} setQuery={setQuery} onNavigate={close} showSearch={false} />}
      showActions={false}
    >
      <div className="mx-auto max-w-4xl">
        <section className="rounded-2xl border bg-secondary/20 p-5 sm:p-7">
          <div className="overline">Find a guide</div>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.02em] sm:text-2xl">What do you want to set up or understand?</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Search product workflows, permissions, industry operations, billing, security, and College ERP integration.</p>
          <div className="relative mt-5">
            <MagnifyingGlass className="pointer-events-none absolute left-4 top-3.5 text-muted-foreground" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} className="h-12 bg-card pl-11 text-sm shadow-sm" placeholder="Search by feature, workflow, or integration" aria-label="Search documentation" />
          </div>
        </section>

        <div className="mt-8 flex items-center justify-between border-b pb-4">
          <div><div className="overline">Guide directory</div><p className="mt-1 text-sm text-muted-foreground" aria-live="polite">{searching ? "Searching all guide content..." : query ? `${results.length} matching ${results.length === 1 ? "guide" : "guides"}` : `${docsManifest.length} guides across ${Object.keys(groupedDocuments()).length} topics`}</p></div>
          {query && <button type="button" onClick={() => setQuery("")} className="text-xs font-semibold text-accent hover:underline">Clear search</button>}
        </div>

        {results.length ? <div className={`mt-7 space-y-8 transition-opacity ${searching ? "opacity-60" : "opacity-100"}`}>{Object.entries(groups).map(([group, documents]) => <section key={group} aria-labelledby={`docs-group-${group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
          <div className="mb-3 flex items-end justify-between gap-3"><h2 id={`docs-group-${group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} className="text-base font-semibold">{group}</h2><span className="text-[11px] font-medium text-muted-foreground">{documents.length} {documents.length === 1 ? "guide" : "guides"}</span></div>
          <div className="overflow-hidden rounded-xl border bg-card divide-y">{documents.map((document) => <Link key={document.slug} to={`/docs/${document.slug}`} className="group grid gap-3 px-4 py-4 transition-colors hover:bg-secondary/45 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-5">
            <span className="min-w-0"><span className="block text-sm font-semibold group-hover:text-accent">{document.title}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{document.description}</span></span>
            <span className="inline-flex items-center gap-2 text-xs font-semibold text-muted-foreground group-hover:text-foreground">Open guide<ArrowRight className="transition-transform group-hover:translate-x-1" /></span>
          </Link>)}</div>
        </section>)}</div> : searching ? <div role="status" className="mt-7 flex items-center justify-center gap-2 rounded-xl border bg-secondary/20 px-5 py-8 text-sm text-muted-foreground"><CircleNotch className="animate-spin" />Searching documentation</div> : <div className="mt-7 rounded-xl border bg-secondary/20 px-5 py-8 text-center"><BookOpen size={24} className="mx-auto text-muted-foreground" /><h2 className="mt-4 font-semibold">No matching guide</h2><p className="mt-2 text-sm text-muted-foreground">Try a feature, module, workflow, or integration term.</p><button type="button" onClick={() => setQuery("")} className="mt-4 text-sm font-semibold text-accent hover:underline">Show all guides</button></div>}
      </div>
    </PublicDocumentLayout>
  </>;
}
