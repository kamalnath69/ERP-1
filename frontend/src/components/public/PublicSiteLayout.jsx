import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { ArrowRight, List, Phone, Sparkle, WhatsappLogo } from "@phosphor-icons/react";

import BrandLogo from "@/components/brand/BrandLogo";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { publicContactLinks } from "@/lib/publicContact";

const PublicSiteContext = createContext(null);

const navItems = [
  { label: "Product", to: "/#platform", section: "product" },
  { label: "Solutions", to: "/#industries", section: "solutions" },
  { label: "AI", to: "/#ai", section: "ai" },
  { label: "Custom projects", to: "/#services", section: "services" },
  { label: "Pricing", to: "/#pricing", section: "pricing" },
  { label: "Docs", to: "/docs", section: "resources" },
];

function usePublicCatalog() {
  const [state, setState] = useState({ site: null, catalog: null, loading: true, error: "" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: "" }));
    Promise.allSettled([
      api.get("/public/site", { forceRefetch: true }),
      api.get("/billing/public/plans", { forceRefetch: true }),
    ]).then(([siteResult, catalogResult]) => {
      if (!active) return;
      setState({
        site: siteResult.status === "fulfilled" ? siteResult.value.data : null,
        catalog: catalogResult.status === "fulfilled" ? catalogResult.value.data : null,
        loading: false,
        error: catalogResult.status === "rejected" ? "Pricing is temporarily unavailable." : "",
      });
    });
    return () => { active = false };
  }, [attempt]);
  return { ...state, retry: () => setAttempt((value) => value + 1) };
}

function sectionFor(pathname, hash) {
  if (pathname.startsWith("/contact")) return "contact";
  if (pathname.startsWith("/about")) return "company";
  if (["/security", "/terms", "/privacy", "/refund-policy"].some((path) => pathname.startsWith(path)) || pathname.startsWith("/docs")) return "resources";
  if (pathname === "/" && hash === "#industries") return "solutions";
  if (pathname === "/" && hash === "#ai") return "ai";
  if (pathname === "/" && hash === "#services") return "services";
  if (pathname === "/" && hash === "#pricing") return "pricing";
  if (pathname === "/" && hash === "#about") return "company";
  if (pathname === "/" && hash === "#contact") return "contact";
  return "product";
}

function publicCta(user, site, catalog) {
  if (user) return { label: "Open workspace", to: user.is_super_admin ? "/super" : "/app" };
  if (site && !site.legal_ready) return { label: "Book a demo", to: "/#contact" };
  if (catalog?.trial_enabled) return { label: "Start free", to: "/register?plan=trial" };
  if (catalog?.payment_available) return { label: "View plans", to: "/#pricing" };
  return { label: "Book a demo", to: "/#contact" };
}

export function usePublicSite() {
  return useContext(PublicSiteContext);
}

export default function PublicSiteLayout() {
  const data = usePublicCatalog();
  const { user } = useAuth();
  const location = useLocation();
  const [observedSection, setObservedSection] = useState(null);
  const [scrolled, setScrolled] = useState(false);
  const active = observedSection || sectionFor(location.pathname, location.hash);
  const cta = useMemo(() => publicCta(user, data.site, data.catalog), [user, data.site, data.catalog]);

  useEffect(() => {
    if (!location.hash) {
      window.scrollTo({ top: 0, behavior: "auto" });
      return;
    }
    const timer = window.setTimeout(() => document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    return () => window.clearTimeout(timer);
  }, [location.pathname, location.hash]);

  useEffect(() => {
    if (location.pathname !== "/" || typeof IntersectionObserver === "undefined") {
      setObservedSection(null);
      return undefined;
    }
    const sections = [
      ["platform", "product"], ["industries", "solutions"], ["ai", "ai"],
      ["services", "services"], ["pricing", "pricing"],
    ];
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible) setObservedSection(visible.target.dataset.publicSection || null);
    }, { rootMargin: "-28% 0px -58%", threshold: [0.01, 0.2, 0.45] });
    sections.forEach(([id, section]) => {
      const node = document.getElementById(id);
      if (node) {
        node.dataset.publicSection = section;
        observer.observe(node);
      }
    });
    return () => observer.disconnect();
  }, [location.pathname]);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 12);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  return <PublicSiteContext.Provider value={data}>
    <div className="marketing-site flex min-h-screen flex-col bg-background text-foreground">
      <a href="#public-content" className="fixed left-4 top-3 z-[70] -translate-y-20 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-lg transition-transform focus:translate-y-0">Skip to content</a>
      <header className={`sticky top-0 z-50 border-b backdrop-blur-xl transition-[background-color,box-shadow] ${scrolled ? "bg-background/94 shadow-[0_8px_30px_hsl(var(--shadow-color)/.055)]" : "bg-background/82"}`}>
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-5 px-4 sm:px-6 lg:px-8">
          <Link to="/" className="shrink-0" aria-label="Edvatiq home">
            <BrandLogo nameClassName="font-marketing text-xl font-semibold" />
          </Link>
          <nav className="ml-auto hidden items-center gap-0.5 xl:flex" aria-label="Public navigation">
            {navItems.map((item) => <Link key={item.label} to={item.to} aria-current={active === item.section ? "page" : undefined} className={`rounded-lg px-3.5 py-2 text-sm font-medium transition-colors ${active === item.section ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}>{item.label}</Link>)}
          </nav>
          <div className="ml-auto hidden items-center gap-2 sm:flex xl:ml-3">
            {!user && <Link to="/login" className="rounded-xl px-4 py-2.5 text-sm font-semibold hover:bg-secondary">Sign in</Link>}
            <Link to={cta.to} className="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-sm transition-transform hover:-translate-y-0.5">{cta.label}<ArrowRight /></Link>
          </div>
          <Sheet>
            <SheetTrigger asChild><button type="button" className="ml-auto grid h-10 w-10 place-items-center rounded-xl border bg-card sm:ml-0 xl:hidden" aria-label="Open navigation"><List size={20} /></button></SheetTrigger>
            <SheetContent side="right" className="flex w-[88vw] max-w-sm flex-col p-0">
              <SheetHeader className="border-b px-5 py-5 text-left"><SheetTitle><BrandLogo markClassName="h-8 w-8 rounded-lg" nameClassName="text-base" /></SheetTitle></SheetHeader>
              <nav className="flex flex-1 flex-col gap-1 p-4" aria-label="Mobile public navigation">
                {navItems.map((item) => <SheetClose asChild key={item.label}><Link to={item.to} aria-current={active === item.section ? "page" : undefined} className={`rounded-xl px-4 py-3 text-sm font-semibold ${active === item.section ? "bg-secondary text-foreground" : "text-muted-foreground"}`}>{item.label}</Link></SheetClose>)}
                <div className="my-3 h-px bg-border" />
                <SheetClose asChild><Link to="/security" className="rounded-xl px-4 py-3 text-sm font-semibold text-muted-foreground">Security</Link></SheetClose>
                <SheetClose asChild><Link to="/#contact" className="rounded-xl px-4 py-3 text-sm font-semibold text-muted-foreground">Contact</Link></SheetClose>
              </nav>
              <div className="space-y-2 border-t p-4">
                {!user && <SheetClose asChild><Link to="/login" className="flex h-11 items-center justify-center rounded-xl border text-sm font-semibold">Sign in</Link></SheetClose>}
                <SheetClose asChild><Link to={cta.to} className="flex h-11 items-center justify-center gap-2 rounded-xl bg-primary text-sm font-semibold text-primary-foreground">{cta.label}<ArrowRight /></Link></SheetClose>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </header>
      <main id="public-content" className="flex-1"><Outlet /></main>
      <PublicFooter site={data.site} />
    </div>
  </PublicSiteContext.Provider>;
}

function PublicFooter({ site }) {
  const supportEmail = site?.support_email || "sales@edvatiq.com";
  const contact = publicContactLinks(site?.contact_phone);
  return <footer className="bg-primary text-primary-foreground">
    <div className="mx-auto max-w-[1440px] px-4 pb-8 pt-14 sm:px-6 lg:px-8 lg:pt-16">
      <div className="grid gap-10 border-b border-primary-foreground/12 pb-12 sm:grid-cols-2 lg:grid-cols-12">
        <div className="sm:col-span-2 lg:col-span-5"><Link to="/" className="inline-flex"><BrandLogo markClassName="h-10 w-10" nameClassName="font-marketing text-2xl font-semibold text-primary-foreground" /></Link><p className="mt-5 max-w-md text-sm leading-7 text-primary-foreground/58">Operating intelligence, focused software, and evidence-backed AI for organizations that need clearer work.</p><div className="mt-5 flex flex-col items-start gap-2 text-sm font-semibold"><a href={`mailto:${supportEmail}`} className="inline-flex items-center gap-2 text-accent hover:underline">{supportEmail}</a><a href={contact.tel} className="inline-flex items-center gap-2 text-primary-foreground/72 hover:text-primary-foreground"><Phone size={16} />{contact.display}</a><a href={contact.whatsapp} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-primary-foreground/72 hover:text-primary-foreground"><WhatsappLogo size={16} />WhatsApp</a></div></div>
        <FooterGroup title="Product" links={[["Platform", "/#platform"], ["Edvatiq AI", "/#ai"], ["Custom projects", "/#services"], ["Plans", "/#pricing"]]} />
        <FooterGroup title="Company" links={[["About", "/#about"], ["Security", "/security"], ["Contact", "/#contact"], ["Sign in", "/login"]]} />
        <FooterGroup title="Legal" links={[["Terms", "/terms"], ["Privacy", "/privacy"], ["Refund policy", "/refund-policy"]]} />
      </div>
      <div className="flex flex-col gap-3 pt-7 text-xs text-primary-foreground/45 sm:flex-row sm:items-center sm:justify-between"><span>Copyright {new Date().getFullYear()} Edvatiq. All rights reserved.</span><span className="inline-flex items-center gap-2"><Sparkle className="text-accent" />Built for responsible, evidence-backed work.</span></div>
    </div>
  </footer>;
}

function FooterGroup({ title, links }) {
  return <nav className="lg:col-span-2" aria-label={`${title} links`}><div className="text-xs font-semibold uppercase tracking-[0.15em] text-primary-foreground/40">{title}</div><div className="mt-5 flex flex-col items-start gap-3 text-sm text-primary-foreground/70">{links.map(([label, to]) => <Link key={label} to={to} className="hover:text-primary-foreground">{label}</Link>)}</div></nav>;
}
