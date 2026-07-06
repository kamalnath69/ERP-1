import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, BarChart, Bar } from "recharts";
import { ArrowUpRight } from "@phosphor-icons/react";
import { Link } from "react-router-dom";

export default function Dashboard() {
  const { user, organization, can } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!can("analytics.view")) { setLoading(false); return; }
    api.get("/analytics/dashboard").then((r) => setData(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [can]);

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <header className="flex items-baseline justify-between">
        <div>
          <div className="overline text-muted-foreground">Overview</div>
          <h1 className="text-4xl font-display font-bold tracking-tight mt-1">
            Good {greeting()}, {user?.first_name}.
          </h1>
          <p className="text-sm text-muted-foreground mt-2">{organization?.name} · {organization?.org_type}</p>
        </div>
      </header>

      {loading ? <div className="text-sm text-muted-foreground">Loading…</div> : null}

      {data && (
        <>
          <div className="grid md:grid-cols-3 lg:grid-cols-6 gap-4">
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
            <Card className="rounded-sm border-border lg:col-span-2">
              <CardHeader className="flex flex-row items-baseline justify-between pb-2">
                <CardTitle className="font-display text-lg tracking-tight">Attendance · last 14 days</CardTitle>
                <span className="overline">%</span>
              </CardHeader>
              <CardContent className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.attendance_trend}>
                    <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="1 4" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" />
                    <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                    <Line type="monotone" dataKey="attendance_percent" stroke="hsl(var(--accent))" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card className="rounded-sm border-border">
              <CardHeader className="pb-2"><CardTitle className="font-display text-lg tracking-tight">Students by department</CardTitle></CardHeader>
              <CardContent className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.department_distribution}>
                    <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="1 4" />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" />
                    <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} stroke="hsl(var(--muted-foreground))" />
                    <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                    <Bar dataKey="students" fill="hsl(var(--primary))" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </>
      )}

      <div className="grid md:grid-cols-3 gap-4">
        <QuickCard title="Ask Athena" to="/app/ai" desc="Get answers from your data — no SQL required." />
        <QuickCard title="Mark attendance" to="/app/attendance" desc="One tap present/absent for any section." />
        <QuickCard title="Publish marks" to="/app/marks" desc="Bulk enter or edit, publish when ready." />
      </div>
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 18) return "afternoon";
  return "evening";
}

function QuickCard({ title, desc, to }) {
  return (
    <Link to={to} className="border border-border p-5 hover:bg-secondary transition-colors bg-card block group">
      <div className="flex items-start justify-between">
        <div className="font-display text-lg font-semibold tracking-tight">{title}</div>
        <ArrowUpRight size={16} className="group-hover:text-accent transition-colors" />
      </div>
      <p className="text-sm text-muted-foreground mt-2">{desc}</p>
    </Link>
  );
}
