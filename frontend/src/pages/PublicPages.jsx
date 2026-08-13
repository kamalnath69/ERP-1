import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowRight, Database, FileText, Fingerprint, LockKey, Receipt, Scales,
  ShieldCheck, UsersThree,
} from "@phosphor-icons/react";

import PageMeta from "@/components/public/PageMeta";
import PublicDocumentLayout, {
  DocumentNavLink, DocumentOverview, DocumentSkeleton,
} from "@/components/public/PublicDocumentLayout";
import SafeMarkdown, { markdownHeadings } from "@/components/public/SafeMarkdown";
import { usePublicSite } from "@/components/public/PublicSiteLayout";
import { legalDocumentDate, withoutMarkdownTitle } from "@/lib/legalDocuments";
import {
  clearPublicLegalDocumentCache, loadPublicLegalDocument,
} from "@/lib/publicLegalDocuments";


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

const LEGAL_DOCUMENTS = {
  terms: {
    label: "Terms of Service",
    shortLabel: "Terms",
    path: "/terms",
    icon: Scales,
    railLabel: "Service agreement",
    description: "The agreement governing accounts, subscriptions, acceptable use, integrations, AI, and service access.",
  },
  privacy: {
    label: "Privacy Policy",
    shortLabel: "Privacy",
    path: "/privacy",
    icon: ShieldCheck,
    railLabel: "Data practices",
    description: "How Edvatiq handles account, organization, operational, academic, and integration data.",
  },
  refund: {
    label: "Refund and Cancellation Policy",
    shortLabel: "Refunds",
    path: "/refund-policy",
    icon: Receipt,
    railLabel: "Billing remedies",
    description: "How renewals, cancellations, duplicate charges, service issues, and approved refunds are handled.",
  },
};

export function LegalPage({ kind }) {
  const params = useParams();
  const { site } = usePublicSite();
  const version = params.version;
  const definition = LEGAL_DOCUMENTS[kind];
  const requestKey = `${kind}:${version || "current"}`;
  const [state, setState] = useState({ key: "", document: null, status: "loading", error: "" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setState({ key: requestKey, document: null, status: "loading", error: "" });
    loadPublicLegalDocument(kind, version)
      .then((document) => { if (active) setState({ key: requestKey, document, status: "ready", error: "" }); })
      .catch(() => { if (active) setState({ key: requestKey, document: null, status: "error", error: "This legal document is not available." }); });
    return () => { active = false; };
  }, [attempt, kind, requestKey, version]);

  const stateIsCurrent = state.key === requestKey;
  const document = stateIsCurrent ? state.document : null;
  const loading = !stateIsCurrent || state.status === "loading";
  const error = stateIsCurrent && state.status === "error" ? state.error : "";
  const title = document?.title || definition.label;
  const markdown = useMemo(() => withoutMarkdownTitle(document?.content_markdown), [document?.content_markdown]);
  const headings = useMemo(() => markdownHeadings(markdown), [markdown]);
  const currentVersion = site?.legal_documents?.[kind]?.version;
  const historical = Boolean(version && currentVersion && Number(version) !== Number(currentVersion));
  const retry = () => {
    clearPublicLegalDocumentCache();
    setAttempt((value) => value + 1);
  };

  return <>
    <PageMeta title={title} description={definition.description} path={`${definition.path}${version ? `/${version}` : ""}`} />
    <PublicDocumentLayout
      title={title}
      eyebrow="Authoritative policy"
      meta={document ? <>Effective {legalDocumentDate(document)}</> : null}
      metaLoading={loading}
      breadcrumbs={[{ label: "Resources", to: "/docs" }, { label: "Legal center" }, { label: definition.shortLabel }]}
      navigationTitle="Legal center"
      navigationLabel="Legal document"
      renderNavigation={({ close }) => <LegalNavigation active={kind} onNavigate={close} />}
      headings={headings}
      showActions={Boolean(document)}
      actionsLoading={loading}
      contentsLoading={loading}
    >
      <div aria-busy={loading}>{loading ? <DocumentSkeleton /> : error || !document ? <div className="mx-auto max-w-3xl py-10"><div className="grid h-11 w-11 place-items-center rounded-xl border bg-secondary"><FileText /></div><h2 className="mt-5 text-2xl font-semibold">Document unavailable</h2><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">{error || "The operator has not published this document yet."}</p><div className="mt-5 flex flex-wrap items-center gap-4"><button type="button" onClick={retry} className="inline-flex h-10 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground">Try again</button><Link to="/#contact" className="inline-flex items-center gap-2 text-sm font-semibold text-accent">Contact support<ArrowRight /></Link></div></div> : <div className="mx-auto max-w-3xl">
        {historical && <div className="mb-7 flex items-start gap-3 rounded-xl border border-warning/25 bg-warning-soft p-4 text-sm"><FileText className="mt-0.5 shrink-0 text-warning" /><div><div className="font-semibold text-foreground">You are reading an archived policy</div><p className="mt-1 leading-6 text-muted-foreground">This publication is retained for reference. A newer policy may contain updated terms.</p><Link to={definition.path} className="mt-2 inline-flex font-semibold text-foreground underline underline-offset-4">Open active policy</Link></div></div>}
        <DocumentOverview>{definition.description}</DocumentOverview>
        <SafeMarkdown content={markdown} className="document-prose" />
        <div className="mt-12 border-t pt-7"><div className="overline">Questions about this policy?</div><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">Contact Edvatiq for policy questions. Do not include passwords, payment credentials, health records, or student records in the first message.</p><Link to="/#contact" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-accent">Contact Edvatiq<ArrowRight /></Link></div>
      </div>}</div>
    </PublicDocumentLayout>
  </>;
}

function LegalNavigation({ active, onNavigate }) {
  return <><div className="px-3 py-2"><div className="overline">Legal center</div><p className="mt-2 text-xs leading-5 text-muted-foreground">Policies and historical records</p></div><nav aria-label="Legal documents" className="mt-3 space-y-1">{Object.entries(LEGAL_DOCUMENTS).map(([value, definition]) => {
    const Icon = definition.icon;
    return <DocumentNavLink key={value} to={definition.path} active={active === value} icon={Icon} title={definition.shortLabel} meta={definition.railLabel} onClick={onNavigate} />;
  })}</nav><div className="mt-6 border-t px-3 pt-5"><div className="text-xs font-semibold">Need policy help?</div><p className="mt-1.5 text-xs leading-5 text-muted-foreground">Reach the monitored Edvatiq contact channel.</p><Link to="/#contact" onClick={onNavigate} className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-accent">Contact us<ArrowRight /></Link></div></>;
}
