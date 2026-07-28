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
  ArrowUpRight, Warning, TrendUp, ChartLineUp, Sparkle,
  ChatCircleDots, ClipboardText, GraduationCap, CalendarBlank,
} from "@phosphor-icons/react";
import { fetchWidgets, selectWidgets, selectDashboardLoading } from "@/store/slices/dashboardSlice";

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

      {loading && !data ? <div className="text-sm text-muted-foreground">Loading widgets...</div> : null}

      {data && (
        <>
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

          <div className="grid lg:grid-cols-2 gap-4">
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
                        <div className="text-[11px] text-muted-foreground">{s.roll_no || "-"} · {s.sessions} sessions</div>
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
                        <div className="text-[11px] text-muted-foreground">{s.roll_no || "-"} · {s.exams} exams</div>
                      </div>
                      <Badge variant="outline" className="rounded-sm border-accent text-accent">
                        {s.avg_pct}%
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Widget>
          </div>

          <Widget title="Leadership focus" icon={ChartLineUp}>
            <div className="grid md:grid-cols-3 gap-3 text-sm">
              <MiniStat label="Students" value={data.kpis.students} />
              <MiniStat label="Faculty" value={data.kpis.faculty} />
              <MiniStat label="Attendance" value={`${data.kpis.avg_attendance_30d}%`} />
            </div>
            <p className="mt-4 text-sm text-muted-foreground">
              This first release is centered on day-to-day academic execution for principals and teachers:
              student oversight, staff allocation, attendance discipline, marks, AI-assisted insights, and reporting.
            </p>
          </Widget>
        </>
      )}

      <div className="grid md:grid-cols-3 gap-4">
        <QuickCard icon={ChatCircleDots} title="Ask Athena" to="/app/ai" desc="Get answers from your data with the right access controls." />
        <QuickCard icon={CalendarBlank} title="Mark attendance" to="/app/attendance" desc="Handle attendance for any section in a few clicks." />
        <QuickCard icon={ClipboardText} title="Publish marks" to="/app/marks" desc="Enter, review, and publish exam results." />
      </div>
    </div>
  );
}

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
