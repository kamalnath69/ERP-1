import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowRight, Database, Fingerprint, LockKey, UsersThree,
} from "@phosphor-icons/react";

import PageMeta from "@/components/public/PageMeta";
import SafeMarkdown from "@/components/public/SafeMarkdown";
import { usePublicSite } from "@/components/public/PublicSiteLayout";
import api from "@/lib/api";


function PublicHero({ eyebrow, title, copy, children, compact = false }) {
  return <section className="soft-glow relative overflow-hidden border-b"><div className="paper-grid absolute inset-0 opacity-20 [mask-image:linear-gradient(to_bottom,black,transparent)]" /><div className={`relative mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8 ${compact ? "py-12 sm:py-14 lg:py-16" : "py-16 sm:py-20 lg:py-24"}`}><div className="overline">{eyebrow}</div><h1 className={`mt-4 max-w-4xl font-semibold leading-[.98] tracking-[-.045em] ${compact ? "text-[clamp(2.7rem,5.2vw,4.6rem)]" : "text-[clamp(2.7rem,6vw,5.3rem)]"}`}>{title}</h1><p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">{copy}</p>{children}</div></section>;
}

export function SecurityPage() {
  const practices = [
    [Fingerprint, "Identity and sessions", "HttpOnly session cookies, CSRF protection, password hashing, session revocation, and optional authenticator security protect account access."],
    [UsersThree, "Role and scope controls", "Permission checks, organization boundaries, and location or academic scope are enforced by the API rather than hidden only in the interface."],
    [Database, "Data minimization", "Integration credentials are hashed or encrypted as appropriate, provider secrets are server-managed, and public APIs expose only documented fields."],
    [LockKey, "Sensitive action controls", "Financial, eligibility, clinical, and AI-assisted changes retain explicit confirmation and auditable ownership."],
  ];
  return <>
    <PageMeta title="Security at Edvatiq" description="How Edvatiq approaches access control, tenant isolation, integrations, and responsible AI." path="/security" />
    <PublicHero eyebrow="Security" title="Protection is part of the workflow." copy="Edvatiq combines tenant isolation, permission-scoped access, audit evidence, and careful integration boundaries. We describe implemented controls without making unsupported certification claims." />
    <section className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 lg:px-8 lg:py-24"><div className="grid gap-4 md:grid-cols-2">{practices.map(([Icon, title, copy]) => <article key={title} className="rounded-2xl border bg-card p-6 sm:p-8"><Icon size={24} className="text-accent" /><h2 className="mt-6 text-xl font-semibold">{title}</h2><p className="mt-3 text-sm leading-7 text-muted-foreground">{copy}</p></article>)}</div><div className="mt-8 rounded-2xl bg-primary p-6 text-primary-foreground sm:p-8"><h2 className="text-2xl font-semibold">Report a security concern</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-primary-foreground/65">Do not include passwords, access tokens, student records, patient records, or other sensitive data in the first message. Our team will establish a suitable channel when needed.</p><Link to="/#contact" className="mt-6 inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-semibold text-accent-foreground">Contact Edvatiq<ArrowRight /></Link></div></section>
  </>;
}

const legalPaths = { terms: "/terms", privacy: "/privacy", refund: "/refund-policy" };
export function LegalPage({ kind }) {
  const params = useParams();
  const { site } = usePublicSite();
  const [state, setState] = useState({ document: null, loading: true, error: "" });
  const version = params.version;
  useEffect(() => {
    const controller = new AbortController();
    setState({ document: null, loading: true, error: "" });
    const current = site?.legal_documents?.[kind];
    if (!version && current?.content_markdown) { setState({ document: current, loading: false, error: "" }); return () => controller.abort(); }
    const path = version ? `/public/legal/${kind}/${version}` : "/public/legal/current";
    api.get(path, { signal: controller.signal, forceRefetch: true }).then(({ data }) => setState({ document: version ? data : data.documents?.[kind], loading: false, error: "" })).catch((error) => { if (error.code !== "ERR_CANCELED") setState({ document: null, loading: false, error: "This legal document is not available." }); });
    return () => controller.abort();
  }, [kind, version, site]);
  const title = state.document?.title || ({ terms: "Terms of Service", privacy: "Privacy Policy", refund: "Refund and Cancellation Policy" }[kind]);
  return <>
    <PageMeta title={title} description={`Read Edvatiq's ${title}.`} path={`${legalPaths[kind]}${version ? `/${version}` : ""}`} />
    <section className="border-b bg-surface-subtle"><div className="mx-auto max-w-[1120px] px-4 py-10 sm:px-6 sm:py-12 lg:px-8"><div className="overline">Legal</div><div className="mt-3 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-4xl font-semibold sm:text-5xl">{title}</h1>{state.document && <p className="mt-3 text-sm text-muted-foreground">Version {state.document.version} / Effective {new Date(state.document.effective_at || state.document.published_at).toLocaleDateString("en-IN", { dateStyle: "long" })}</p>}</div>{state.document && <button type="button" onClick={() => window.print()} className="inline-flex h-10 w-fit items-center rounded-xl border bg-card px-4 text-sm font-semibold hover:bg-secondary">Print document</button>}</div><div className="lg:hidden"><LegalLinks active={kind} /></div></div></section>
    <section className="mx-auto grid min-h-[360px] max-w-[1120px] items-start gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[200px_minmax(0,1fr)] lg:px-8 lg:py-14"><aside className="hidden lg:block"><div className="sticky top-24 rounded-xl border bg-card p-4"><div className="overline">Policies</div><LegalLinks active={kind} vertical /><p className="mt-5 border-t pt-4 text-xs leading-5 text-muted-foreground">Questions about these policies can be sent through our contact section.</p><Link to="/#contact" className="mt-3 inline-flex text-xs font-semibold text-accent">Contact Edvatiq</Link></div></aside><div aria-busy={state.loading}>{state.loading ? <div className="rounded-2xl border bg-card p-6 sm:p-8"><div className="space-y-4">{["w-3/4", "w-full", "w-full", "w-5/6", "w-full", "w-2/3"].map((width, index) => <div key={`${width}-${index}`} className={`h-4 animate-pulse rounded bg-secondary ${width}`} />)}</div></div> : state.error || !state.document ? <div className="rounded-2xl border bg-card p-6 sm:p-8"><h2 className="text-xl font-semibold">Document unavailable</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{state.error || "The operator has not published this document yet."}</p><Link to="/#contact" className="mt-5 inline-flex text-sm font-semibold text-accent">Contact support</Link></div> : <div className="rounded-2xl border bg-card p-5 shadow-sm sm:p-8 lg:p-10"><SafeMarkdown content={state.document.content_markdown} /></div>}</div></section>
  </>;
}

function LegalLinks({ active, vertical = false }) {
  const links = [["terms", "Terms", "/terms"], ["privacy", "Privacy", "/privacy"], ["refund", "Refund policy", "/refund-policy"]];
  return <nav aria-label="Legal documents" className={vertical ? "mt-3 flex flex-col gap-1" : "mt-7 flex gap-2 overflow-x-auto pb-1"}>{links.map(([value, label, to]) => <Link key={value} to={to} aria-current={active === value ? "page" : undefined} className={`shrink-0 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${active === value ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground"}`}>{label}</Link>)}</nav>;
}
