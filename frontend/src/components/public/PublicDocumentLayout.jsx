import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CaretRight, Check, Copy, List, Printer } from "@phosphor-icons/react";

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

export default function PublicDocumentLayout({
  title,
  eyebrow,
  meta,
  breadcrumbs = [],
  navigationTitle,
  navigationLabel = "Document navigation",
  renderNavigation,
  headings = [],
  showActions = true,
  actionsLoading = false,
  metaLoading = false,
  contentsLoading = false,
  children,
}) {
  const hasContents = headings.length > 0 || contentsLoading;
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeHeading, setActiveHeading] = useState("");
  const [readingProgress, setReadingProgress] = useState(0);
  const [copied, setCopied] = useState(false);
  const documentRef = useRef(null);

  useEffect(() => {
    if (!headings.length) {
      setActiveHeading("");
      return undefined;
    }
    setActiveHeading(headings[0].id);
    if (typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]?.target?.id) setActiveHeading(visible[0].target.id);
    }, { rootMargin: "-18% 0px -72% 0px", threshold: 0 });
    headings.forEach(({ id }) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [headings]);

  useEffect(() => {
    const updateProgress = () => {
      const element = documentRef.current;
      if (!element) return;
      const start = element.getBoundingClientRect().top + window.scrollY - 120;
      const distance = Math.max(element.offsetHeight - window.innerHeight + 160, 1);
      setReadingProgress(Math.min(100, Math.max(0, ((window.scrollY - start) / distance) * 100)));
    };
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateProgress);
    if (documentRef.current) resizeObserver?.observe(documentRef.current);
    updateProgress();
    window.addEventListener("scroll", updateProgress, { passive: true });
    window.addEventListener("resize", updateProgress);
    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("scroll", updateProgress);
      window.removeEventListener("resize", updateProgress);
    };
  }, []);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return <>
    <div className="document-reading-progress fixed left-0 top-16 z-40 h-0.5 bg-accent transition-[width] duration-150" style={{ width: `${readingProgress}%` }} aria-hidden="true" />
    <section className="document-titlebar border-b bg-card">
      <div className="mx-auto max-w-[1320px] px-4 py-7 sm:px-6 sm:py-9 lg:px-8">
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 overflow-hidden text-xs text-muted-foreground">
          {breadcrumbs.map((item, index) => <React.Fragment key={`${item.label}-${index}`}>{index > 0 && <CaretRight className="shrink-0" />}{item.to ? <Link to={item.to} className="shrink-0 hover:text-foreground">{item.label}</Link> : <span className="truncate text-foreground">{item.label}</span>}</React.Fragment>)}
        </nav>
        <div className="mt-5 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0"><div className="overline">{eyebrow}</div><h1 className="mt-2 max-w-4xl text-3xl font-semibold tracking-[-0.035em] sm:text-4xl lg:text-[2.75rem]">{title}</h1>{metaLoading ? <div className="mt-4 h-3 w-36 animate-pulse rounded bg-secondary" aria-hidden="true" /> : meta && <div className="mt-4 text-xs font-medium text-muted-foreground">{meta}</div>}</div>
          {actionsLoading ? <div className="document-actions flex shrink-0 gap-2" aria-hidden="true"><span className="h-10 w-28 animate-pulse rounded-lg bg-secondary" /><span className="h-10 w-20 animate-pulse rounded-lg bg-secondary" /></div> : showActions && <div className="document-actions flex shrink-0 gap-2"><button type="button" onClick={copyLink} className="inline-flex h-10 items-center gap-2 rounded-lg border bg-background px-3.5 text-sm font-semibold hover:bg-secondary">{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy link"}</button><button type="button" onClick={() => window.print()} className="inline-flex h-10 items-center gap-2 rounded-lg border bg-background px-3.5 text-sm font-semibold hover:bg-secondary"><Printer />Print</button></div>}
        </div>
      </div>
    </section>
    <div className="document-mobile-navigation sticky top-16 z-30 border-b bg-background/95 backdrop-blur lg:hidden">
      <div className="mx-auto flex max-w-[1320px] items-center justify-between gap-4 px-4 py-3 sm:px-6"><span className="min-w-0 truncate text-sm font-semibold">{title}</span><Sheet open={mobileOpen} onOpenChange={setMobileOpen}><SheetTrigger asChild><button type="button" className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg border bg-card px-3 text-xs font-semibold"><List />Browse</button></SheetTrigger><SheetContent side="left" className="w-[88vw] max-w-[340px] overflow-y-auto p-0"><SheetHeader className="border-b px-5 py-5 text-left"><SheetTitle>{navigationTitle}</SheetTitle></SheetHeader><div className="p-4">{renderNavigation?.({ mobile: true, close: () => setMobileOpen(false) })}</div></SheetContent></Sheet></div>
    </div>
    <section className="bg-surface-subtle px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
      <div className={`document-workspace mx-auto grid max-w-[1320px] items-start rounded-2xl border bg-card shadow-[0_18px_50px_hsl(var(--shadow-color)/0.055)] lg:grid-cols-[232px_minmax(0,1fr)] ${hasContents ? "xl:grid-cols-[232px_minmax(0,1fr)_224px]" : ""}`}>
        <aside className="document-navigation-rail hidden self-stretch rounded-l-2xl border-r bg-secondary/20 lg:block"><div className="premium-scrollbar sticky top-[5.25rem] max-h-[calc(100vh-6.5rem)] overflow-y-auto p-4">{renderNavigation?.({ mobile: false, close: undefined })}</div></aside>
        <main ref={documentRef} className="document-panel min-w-0 px-5 py-7 sm:px-8 sm:py-9 lg:px-10 lg:py-10">{children}</main>
        {hasContents && <DocumentContents headings={headings} activeHeading={activeHeading} navigationLabel={navigationLabel} loading={contentsLoading} />}
      </div>
    </section>
  </>;
}

export function DocumentNavGroup({ label, children, className = "" }) {
  return <div className={`mb-5 ${className}`}><div className="px-3 text-[10px] font-semibold uppercase tracking-[.16em] text-muted-foreground">{label}</div><div className="mt-2 space-y-0.5">{children}</div></div>;
}

export function DocumentNavLink({ to, active = false, icon: Icon, title, meta, onClick }) {
  return <Link to={to} onClick={onClick} aria-current={active ? "page" : undefined} className={`group flex items-start gap-3 border-l-2 px-3 py-2.5 transition-colors ${active ? "border-primary bg-card text-foreground shadow-sm" : "border-transparent text-muted-foreground hover:border-border hover:bg-card/65 hover:text-foreground"}`}>{Icon && <Icon size={18} className="mt-0.5 shrink-0" />}<span className="min-w-0"><span className="block text-sm font-semibold leading-5">{title}</span>{meta && <span className="mt-0.5 block text-[11px] leading-4">{meta}</span>}</span></Link>;
}

export function DocumentOverview({ children, eyebrow = "Document overview" }) {
  return <div className="mb-8 border-b pb-8"><div className="overline">{eyebrow}</div><div className="mt-3 text-base leading-7 text-foreground/80">{children}</div></div>;
}

export function DocumentSkeleton() {
  return <div className="mx-auto max-w-3xl animate-pulse py-1" role="status" aria-label="Loading document"><div className="border-b pb-8"><div className="h-3 w-28 rounded bg-secondary" /><div className="mt-4 h-4 w-full rounded bg-secondary" /><div className="mt-3 h-4 w-4/5 rounded bg-secondary" /></div>{[1, 2, 3].map((section, index) => <div key={section} className={index ? "mt-10" : "mt-9"}><div className={`h-6 rounded bg-secondary ${index === 1 ? "w-2/5" : "w-1/3"}`} /><div className="mt-5 space-y-3"><div className="h-3.5 w-full rounded bg-secondary" /><div className="h-3.5 w-[94%] rounded bg-secondary" /><div className="h-3.5 w-4/5 rounded bg-secondary" /></div></div>)}<span className="sr-only">Loading document</span></div>;
}

function DocumentContents({ headings, activeHeading, navigationLabel, loading = false }) {
  return <aside className="document-contents hidden self-stretch rounded-r-2xl border-l bg-secondary/10 xl:block"><div className="premium-scrollbar sticky top-[5.25rem] max-h-[calc(100vh-6.5rem)] overflow-y-auto p-5"><div className="overline">On this page</div>{loading ? <div className="mt-5 space-y-3" aria-hidden="true">{["w-full", "w-5/6", "w-3/4", "w-[88%]"].map((width, index) => <div key={`${width}-${index}`} className={`h-3 animate-pulse rounded bg-secondary ${width}`} />)}</div> : headings.length ? <nav className="mt-4 space-y-1" aria-label={`${navigationLabel} contents`}>{headings.map((heading) => <a key={heading.id} href={`#${heading.id}`} aria-current={activeHeading === heading.id ? "location" : undefined} className={`block border-l px-3 py-1.5 text-xs leading-5 transition-colors ${heading.level === 3 ? "pl-6" : ""} ${activeHeading === heading.id ? "border-primary font-semibold text-foreground" : "border-border text-muted-foreground hover:text-foreground"}`}>{heading.title}</a>)}</nav> : <p className="mt-3 text-xs leading-5 text-muted-foreground">Section links will appear when the document loads.</p>}</div></aside>;
}
