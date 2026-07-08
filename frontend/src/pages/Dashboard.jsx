import React, { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  BarChart, Bar,
} from "recharts";
import {
  ArrowUpRight, Warning, TrendUp, Bank, Briefcase, CalendarDots, Bell,
  ChartLineUp, Sparkle, ChatCircleDots, ClipboardText, GraduationCap,
} from "@phosphor-icons/react";
import { fetchWidgets, selectWidgets, selectDashboardLoading } from "@/store/slices/dashboardSlice";

// -----------------------------------------------------------------------------
// Enterprise dashboard — 8+ widgets driven by /api/analytics/widgets.
// -----------------------------------------------------------------------------
export default function Dashboard() {
  const { user, organization, can } = useAuth();
  const dispatch = useDispatch();
  const data = useSelector(selectWidgets);
  const loading = useSelector(selectDashboardLoading);

  useEffect(() => {
    if (can("analytics.view")) dispatch(fetchWidgets());
  }, [dispatch, can]);

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Header ------------------------------------------------------------ */}
      <header className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <div className="overline text-muted-foreground">Overview</div>
          <h1 className="text-4xl font-display font-bold tracking-tight mt-1">
            Good {greeting()}, {user?.first_name}.
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {organization?.name} · {organization?.org_type}
            {data?.generated_at && <span className="ml-2 text-[11px]">· refreshed {timeAgo(data.generated_at)}</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/app/ai" className="text-xs border border-border px-3 py-2 hover:bg-secondary flex items-center gap-2">
            <Sparkle size={14} /> Ask Athena
          </Link>
          <Link to="/app/reports" className="text-xs border border-border px-3 py-2 hover:bg-secondary flex items-center gap-2">
            <ClipboardText size={14} /> Reports
          </Link>
        </div>
      </header>

      {loading && !data ? <div className="text-sm text-muted-foreground">Loading widgets…</div> : null}

      {data && (
        <>
          {/* KPIs strip ---------------------------------------------------- */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              ["students", "Students"],
              ["faculty", "Faculty"],
              ["departments", "Departments"],
              ["subjects", "Subjects"],
              ["sections", "Sections"],
              ["avg_attendance_30d", "Attendance 30d"],
            ].map(([k, label]) => (
              <Card key={k} className="rounded-sm border-border">
                <CardContent className="p-4">
                  <div className="overline">{label}</div>
                  <div className="mt-2 font-display text-3xl font-bold" data-testid={`kpi-${k}`}>
                    {data.kpis[k]}{k === "avg_attendance_30d" ? "%" : ""}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Row: Attendance trend + Department distribution -------------- */}
          <div className="grid lg:grid-cols-3 gap-4">
            <Widget title="Attendance · last 14 days" icon={TrendUp} className="lg:col-span-2">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.attendance_trend}>
                    <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="1 4" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" domain={[0, 100]} />
                    <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                    <Line type="monotone" dataKey="attendance_percent" stroke="hsl(var(--accent))" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Widget>

            <Widget title="Students by department" icon={GraduationCap}>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.department_distribution}>
                    <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="1 4" />
                    <XAxis dataKey="name" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" />
                    <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                    <Bar dataKey="students" fill="hsl(var(--primary))" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Widget>
          </div>

          {/* Row: At-risk + Top performers + Fees ------------------------- */}
          <div className="grid lg:grid-cols-3 gap-4">
            <Widget title="At-risk students" icon={Warning} tone="warning" linkTo="/app/attendance" linkLabel="Review">
              {data.at_risk.length === 0 ? (
                <EmptyState msg="No students below 75% attendance in the last 30 days." />
              ) : (
                <ul className="divide-y divide-border" data-testid="widget-at-risk">
                  {data.at_risk.map((s) => (
                    <li key={s.student_id} className="py-2 flex items-center justify-between text-sm">
                      <div>
                        <Link to={`/app/students/${s.student_id}`} className="font-medium hover:underline">
                          {s.name}
                        </Link>
                        <div className="text-[11px] text-muted-foreground">{s.roll_no || "—"} · {s.sessions} sessions</div>
                      </div>
                      <Badge variant="outline" className="rounded-sm border-destructive text-destructive">
                        {s.attendance_pct}%
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Widget>

            <Widget title="Top performers" icon={TrendUp} linkTo="/app/marks" linkLabel="View marks">
              {data.top_performers.length === 0 ? (
                <EmptyState msg="No published exams yet." />
              ) : (
                <ul className="divide-y divide-border" data-testid="widget-top-performers">
                  {data.top_performers.slice(0, 6).map((s) => (
                    <li key={s.student_id} className="py-2 flex items-center justify-between text-sm">
                      <div>
                        <Link to={`/app/students/${s.student_id}`} className="font-medium hover:underline">
                          {s.name}
                        </Link>
                        <div className="text-[11px] text-muted-foreground">{s.roll_no || "—"} · {s.exams} exams</div>
                      </div>
                      <Badge variant="outline" className="rounded-sm border-accent text-accent">
                        {s.avg_pct}%
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Widget>

            <Widget title="Fees" icon={Bank} linkTo="/app/fees" linkLabel="Open fees">
              <div className="space-y-3 text-sm" data-testid="widget-fees">
                <div className="flex items-baseline justify-between">
                  <span className="text-muted-foreground">Collected</span>
                  <span className="font-display text-2xl font-bold">₹{formatMoney(data.fees.collected)}</span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-muted-foreground">Pending</span>
                  <span className="font-mono">₹{formatMoney(data.fees.pending)}</span>
                </div>
                <div className="h-2 bg-secondary overflow-hidden rounded-sm">
                  <div
                    className="h-full bg-accent"
                    style={{ width: `${Math.min(100, data.fees.collection_rate)}%` }}
                  />
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {data.fees.invoices} invoices · {data.fees.collection_rate}% collected
                </div>
              </div>
            </Widget>
          </div>

          {/* Row: Placements + Calendar + Notifications ------------------- */}
          <div className="grid lg:grid-cols-3 gap-4">
            <Widget title="Placements" icon={Briefcase} linkTo="/app/placements" linkLabel="Open">
              <div className="grid grid-cols-2 gap-3 text-sm" data-testid="widget-placements">
                <MiniStat label="Offers" value={data.placements.offers} />
                <MiniStat label="Accepted" value={data.placements.accepted} />
                <MiniStat label="Avg pkg" value={`${data.placements.avg_lpa} L`} />
                <MiniStat label="Max pkg" value={`${data.placements.max_lpa} L`} />
              </div>
              <div className="mt-3 text-[11px] text-muted-foreground">
                Placement rate: {data.placements.placement_rate}%
              </div>
            </Widget>

            <Widget title="Upcoming calendar" icon={CalendarDots} linkTo="/app/calendar" linkLabel="Full calendar">
              {data.calendar.length === 0 ? (
                <EmptyState msg="No upcoming events in the next 30 days." />
              ) : (
                <ul className="divide-y divide-border" data-testid="widget-calendar">
                  {data.calendar.map((e) => (
                    <li key={e.id} className="py-2 flex items-start justify-between text-sm">
                      <div>
                        <div className="font-medium">{e.title}</div>
                        <div className="text-[11px] text-muted-foreground uppercase tracking-widest">{e.kind}</div>
                      </div>
                      <span className="font-mono text-[11px]">{e.event_date}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Widget>

            <Widget
              title={`Notifications${data.notifications.unread ? ` · ${data.notifications.unread} unread` : ""}`}
              icon={Bell}
              linkTo="/app/notifications"
              linkLabel="Open"
            >
              {data.notifications.recent.length === 0 ? (
                <EmptyState msg="You're all caught up." />
              ) : (
                <ul className="divide-y divide-border" data-testid="widget-notifications">
                  {data.notifications.recent.map((n) => (
                    <li key={n.id} className={`py-2 text-sm ${n.is_read ? "opacity-60" : ""}`}>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="rounded-sm text-[10px] uppercase">
                          {n.kind}
                        </Badge>
                        <span className="font-medium">{n.title}</span>
                      </div>
                      {n.body && <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">{n.body}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </Widget>
          </div>

          {/* Recent activity full-width ---------------------------------- */}
          <Widget title="Recent activity" icon={ChartLineUp} linkTo="/app/audit" linkLabel="Open audit log">
            {data.activity.length === 0 ? (
              <EmptyState msg="No activity yet." />
            ) : (
              <ul className="divide-y divide-border" data-testid="widget-activity">
                {data.activity.map((a) => (
                  <li key={a.id} className="py-2 flex items-center justify-between text-sm">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-[11px] font-mono text-muted-foreground w-32 truncate">
                        {a.action}
                      </span>
                      <span className="text-sm truncate">
                        <span className="font-medium">{a.user_name}</span>{" "}
                        {a.resource_type ? <span className="text-muted-foreground">· {a.resource_type}</span> : null}
                      </span>
                    </div>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {timeAgo(a.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Widget>
        </>
      )}

      {/* Quick actions ---------------------------------------------------- */}
      <div className="grid md:grid-cols-3 gap-4">
        <QuickCard icon={ChatCircleDots} title="Ask Athena" to="/app/ai" desc="Get answers from your data — no SQL required." />
        <QuickCard icon={CalendarDots} title="Mark attendance" to="/app/attendance" desc="One tap present/absent for any section." />
        <QuickCard icon={ClipboardText} title="Publish marks" to="/app/marks" desc="Bulk enter or edit, publish when ready." />
      </div>
    </div>
  );
}

// ----- Sub components ------------------------------------------------------- //

function Widget({ title, icon: Icon, children, linkTo, linkLabel, tone, className = "" }) {
  return (
    <Card className={`rounded-sm border-border ${className}`}>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="font-display text-base tracking-tight flex items-center gap-2">
          {Icon ? <Icon size={16} className={tone === "warning" ? "text-destructive" : "text-accent"} /> : null}
          {title}
        </CardTitle>
        {linkTo && (
          <Link to={linkTo} className="text-[11px] uppercase tracking-widest text-muted-foreground hover:text-foreground flex items-center gap-1">
            {linkLabel || "Open"} <ArrowUpRight size={12} />
          </Link>
        )}
      </CardHeader>
      <CardContent className="pt-2">{children}</CardContent>
    </Card>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="border border-border p-2 rounded-sm">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className="font-display text-xl font-bold mt-1">{value}</div>
    </div>
  );
}

function EmptyState({ msg }) {
  return <div className="text-sm text-muted-foreground py-4">{msg}</div>;
}

function QuickCard({ icon: Icon, title, desc, to }) {
  return (
    <Link to={to} className="border border-border p-5 hover:bg-secondary transition-colors bg-card block group">
      <div className="flex items-start justify-between">
        <div className="font-display text-lg font-semibold tracking-tight flex items-center gap-2">
          {Icon && <Icon size={18} />} {title}
        </div>
        <ArrowUpRight size={16} className="group-hover:text-accent transition-colors" />
      </div>
      <p className="text-sm text-muted-foreground mt-2">{desc}</p>
    </Link>
  );
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 18) return "afternoon";
  return "evening";
}

function formatMoney(n) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(n || 0);
}

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const s = Math.round((now - then) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
