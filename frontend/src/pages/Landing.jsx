import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowUpRight, Buildings, Sparkle, ShieldCheck, ChartLineUp, GraduationCap, Users } from "@phosphor-icons/react";

const HERO_IMG = "https://images.pexels.com/photos/21415155/pexels-photo-21415155.jpeg";
const FEATURE_IMG_1 = "https://images.pexels.com/photos/15316912/pexels-photo-15316912.jpeg";
const FEATURE_IMG_2 = "https://images.pexels.com/photos/6209565/pexels-photo-6209565.jpeg";

export default function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="landing-page">
      {/* NAV */}
      <nav className="border-b border-border">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-baseline gap-2" data-testid="brand-link">
            <span className="text-2xl font-display font-bold tracking-tight">Athena</span>
            <span className="overline">Education OS</span>
          </Link>
          <div className="flex items-center gap-3">
            <a href="#features" className="text-sm text-muted-foreground hover:text-foreground hidden md:inline">Platform</a>
            <a href="#pricing" className="text-sm text-muted-foreground hover:text-foreground hidden md:inline">Pricing</a>
            <Link to="/login" className="text-sm text-muted-foreground hover:text-foreground" data-testid="nav-login">Sign in</Link>
            <Link to="/register"><Button className="rounded-sm" data-testid="nav-register">Start free trial</Button></Link>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="absolute inset-0 grid-lines-bg opacity-40" />
        <div className="relative max-w-7xl mx-auto px-6 py-24 grid md:grid-cols-12 gap-8 items-center">
          <div className="md:col-span-7">
            <div className="overline mb-6 text-accent">Enterprise · Multi-tenant · AI-native</div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold leading-none tracking-tight">
              The Education <span className="accent-underline">Operating System</span> your school or college deserves.
            </h1>
            <p className="mt-8 text-base leading-relaxed max-w-xl text-muted-foreground">
              One codebase for K-12 and higher-ed. Roles, permissions, attendance, marks, analytics, and a ChatGPT-grade
              assistant that actually queries your data. Built for principals, not for pitch decks.
            </p>
            <div className="mt-10 flex flex-wrap gap-3">
              <Link to="/register">
                <Button size="lg" className="rounded-sm" data-testid="hero-cta-primary">
                  Start free · No credit card <ArrowUpRight size={16} className="ml-2" />
                </Button>
              </Link>
              <Link to="/login">
                <Button size="lg" variant="outline" className="rounded-sm" data-testid="hero-cta-secondary">
                  Sign in to demo
                </Button>
              </Link>
            </div>
            <div className="mt-10 flex flex-wrap gap-6 items-center text-xs font-mono uppercase tracking-widest text-muted-foreground">
              <span>ISO 27001 ready</span><span>·</span><span>SOC2 pathway</span><span>·</span><span>Deployed to K-12 & higher-ed</span>
            </div>
          </div>
          <div className="md:col-span-5 relative">
            <div className="relative overflow-hidden border border-border bg-secondary">
              <img src={HERO_IMG} alt="Modern campus" className="w-full h-[420px] object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent" />
              <div className="absolute bottom-0 left-0 right-0 p-6 text-white">
                <div className="text-[10px] uppercase tracking-widest opacity-70">Live snapshot · Demo College</div>
                <div className="mt-2 flex items-end justify-between">
                  <div>
                    <div className="font-display text-3xl">92.4%</div>
                    <div className="text-xs opacity-70">Attendance · last 30d</div>
                  </div>
                  <div>
                    <div className="font-display text-3xl">1,284</div>
                    <div className="text-xs opacity-70">Active students</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section id="features" className="border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="max-w-3xl">
            <div className="overline text-muted-foreground">What ships on day one</div>
            <h2 className="mt-3 text-2xl sm:text-3xl lg:text-4xl font-display font-bold tracking-tight">
              A control room for the entire institution.
            </h2>
          </div>
          <div className="mt-12 grid md:grid-cols-12 gap-6">
            <FeatureCard className="md:col-span-6 md:row-span-2" icon={Sparkle} title="Athena AI Assistant"
              desc="Ask anything in natural language. It calls the right tool, respects your permissions, and never fabricates.">
              <pre className="mt-4 text-xs font-mono bg-secondary p-3 border border-border overflow-x-auto">
{`> who is at risk in year 2 CSE?
[tool] search_students → 6 matches
[tool] risk_prediction  → 2 flagged
Suresh Kumar, Priya Reddy — low attendance / failed CS201`}
              </pre>
            </FeatureCard>
            <FeatureCard className="md:col-span-6" icon={ShieldCheck} title="Dynamic Roles & Permissions"
              desc="Build any role. Assign fine-grained scopes across campus, department, section, subject. No hardcoding." />
            <FeatureCard className="md:col-span-3" icon={Buildings} title="Multi-tenant" desc="One deployment, thousands of institutions, zero cross-tenant leakage." />
            <FeatureCard className="md:col-span-3" icon={ChartLineUp} title="Live Analytics" desc="Attendance, marks, at-risk cohorts. Board-ready dashboards." />
            <FeatureCard className="md:col-span-8" icon={GraduationCap} title="Students · Faculty · Parents"
              desc="Full lifecycle — admissions to alumni. Every stakeholder in one system.">
              <div className="mt-4 grid grid-cols-3 gap-4">
                <img src={FEATURE_IMG_2} alt="students" className="h-32 w-full object-cover border border-border" />
                <img src={FEATURE_IMG_1} alt="campus" className="h-32 w-full object-cover border border-border" />
                <div className="h-32 border border-border bg-secondary p-3 flex flex-col justify-between">
                  <div className="overline">Section 2A · CSE</div>
                  <div>
                    <div className="text-3xl font-display">42</div>
                    <div className="text-xs text-muted-foreground">enrolled</div>
                  </div>
                </div>
              </div>
            </FeatureCard>
            <FeatureCard className="md:col-span-4" icon={Users} title="School or College — same code" desc="Generic academic hierarchy adapts to your terminology." />
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <div className="max-w-3xl">
            <div className="overline text-muted-foreground">Pricing</div>
            <h2 className="mt-3 text-2xl sm:text-3xl lg:text-4xl font-display font-bold tracking-tight">Simple monthly plans, powered by Razorpay.</h2>
          </div>
          <div className="mt-12 grid md:grid-cols-3 gap-6">
            {[
              { name: "Starter", price: "₹4,999", desc: "Up to 500 students · core ERP", features: ["Students & Faculty", "Attendance & Marks", "3 admin seats"] },
              { name: "Pro", price: "₹14,999", desc: "Up to 5,000 students · full suite + AI", features: ["Everything in Starter", "Athena AI Assistant", "Analytics & Reports", "Unlimited seats"], featured: true },
              { name: "Enterprise", price: "₹49,999", desc: "Unlimited, multi-campus, SLA", features: ["Everything in Pro", "Multi-campus", "SSO / Custom SLA", "Priority support"] },
            ].map((p) => (
              <div key={p.name} className={`border ${p.featured ? "border-accent" : "border-border"} p-6 bg-card`}>
                <div className="flex items-baseline justify-between">
                  <h3 className="text-lg font-display font-semibold">{p.name}</h3>
                  {p.featured && <span className="overline text-accent">Popular</span>}
                </div>
                <div className="mt-4 text-4xl font-display font-bold">{p.price}<span className="text-sm text-muted-foreground font-sans">/mo</span></div>
                <p className="mt-2 text-sm text-muted-foreground">{p.desc}</p>
                <ul className="mt-6 space-y-2 text-sm">
                  {p.features.map((f) => <li key={f} className="flex gap-2"><span className="text-accent">•</span>{f}</li>)}
                </ul>
                <Link to="/register" className="mt-8 block">
                  <Button className="w-full rounded-sm" variant={p.featured ? "default" : "outline"} data-testid={`plan-cta-${p.name.toLowerCase()}`}>
                    Start with {p.name}
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="max-w-7xl mx-auto px-6 py-10 text-xs text-muted-foreground flex flex-wrap justify-between gap-4">
        <div>© {new Date().getFullYear()} Athena Education OS · Built for institutions that mean it.</div>
        <div className="font-mono uppercase tracking-widest">v1.0 · Multi-tenant · AI-first</div>
      </footer>
    </div>
  );
}

function FeatureCard({ icon: Icon, title, desc, children, className = "" }) {
  return (
    <div className={`border border-border p-6 bg-card ${className}`}>
      <Icon size={20} weight="bold" />
      <h3 className="mt-4 text-lg font-display font-semibold tracking-tight">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{desc}</p>
      {children}
    </div>
  );
}
