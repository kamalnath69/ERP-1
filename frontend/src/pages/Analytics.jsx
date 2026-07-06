import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid, LineChart, Line } from "recharts";

const COLORS = ["hsl(240 10% 15%)", "hsl(240 3.8% 46.1%)", "hsl(346 87% 43%)", "hsl(200 60% 40%)", "hsl(40 90% 50%)"];

export default function Analytics() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/dashboard").then((r) => setData(r.data)); }, []);
  if (!data) return <div className="text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="space-y-6" data-testid="analytics-page">
      <header>
        <div className="overline text-muted-foreground">Analytics</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Institution insights</h1>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        {[["students","Students"],["faculty","Faculty"],["departments","Depts"],["sections","Sections"],["subjects","Subjects"],["avg_attendance_30d","Att 30d %"]].map(([k, l]) => (
          <Card key={k} className="rounded-sm border-border"><CardContent className="p-4"><div className="overline">{l}</div><div className="font-display text-3xl mt-1" data-testid={`analytics-kpi-${k}`}>{data.kpis[k]}{k === "avg_attendance_30d" ? "%" : ""}</div></CardContent></Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="rounded-sm border-border">
          <CardHeader className="pb-2"><CardTitle className="font-display text-lg tracking-tight">Attendance trend</CardTitle></CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.attendance_trend}>
                <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="1 4" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
                <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
                <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                <Line type="monotone" dataKey="attendance_percent" stroke="hsl(var(--accent))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card className="rounded-sm border-border">
          <CardHeader className="pb-2"><CardTitle className="font-display text-lg tracking-tight">Department distribution</CardTitle></CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data.department_distribution} dataKey="students" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
                  {data.department_distribution.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card className="rounded-sm border-border lg:col-span-2">
          <CardHeader className="pb-2"><CardTitle className="font-display text-lg tracking-tight">Students per department</CardTitle></CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.department_distribution}>
                <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="1 4" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
                <YAxis tick={{ fontSize: 11, fontFamily: "IBM Plex Mono" }} />
                <Tooltip contentStyle={{ fontFamily: "IBM Plex Mono", fontSize: 12, borderRadius: 2 }} />
                <Bar dataKey="students" fill="hsl(var(--primary))" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
