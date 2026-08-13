import React, { useState } from "react";
import {
  ArrowRight, Briefcase, ChartLineUp, CheckCircle, DownloadSimple, FilePdf, FileXls,
  GraduationCap, Lock, Medal, Receipt, Student, Target, Wallet, WarningCircle,
} from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import BusinessChart from "@/components/charts/BusinessChart";
import {
  ChartPanel, DataTable, EmptyState, ErrorState, FilterToolbar, InsightPanel, MetricStrip,
  PageHeader, PageShell, PageSkeleton, QueuePanel, SegmentControl, StatusBadge, Surface,
} from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useBusiness } from "@/contexts/BusinessContext";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { useGetReportsQuery } from "@/store/api/workspaceApi";
import {
  useGetCollegeLeaderboardsQuery,
  useGetCollegePlacementDashboardQuery,
} from "@/features/college/collegeApi";

const initialRange = () => {
  const today = new Date();
  return {
    start: new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10),
    end: today.toISOString().slice(0, 10),
  };
};

export default function Reports() {
  const { organization } = useBusiness();
  return organization?.industry === "college" ? <CollegeReports /> : <BusinessReports />;
}

function BusinessReports() {
  const navigate = useNavigate();
  const { locationId } = useBusiness();
  const isCollege = false;
  const firstRange = initialRange();
  const [start, setStart] = useState(firstRange.start);
  const [end, setEnd] = useState(firstRange.end);
  const [filters, setFilters] = useState(firstRange);
  const [downloading, setDownloading] = useState(null);
  const reportQuery = useGetReportsQuery(
    { locationId, ...filters },
    withSkip(QUERY_POLICIES.analytical, !locationId),
  );
  const { data, isFetching, isLoading, error } = reportQuery;

  const apply = () => {
    if (start > end) {
      toast.error("The start date must be before the end date");
      return;
    }
    if (filters.start === start && filters.end === end) reportQuery.refetch();
    else setFilters({ start, end });
  };

  const download = async (type) => {
    if (downloading) return;
    setDownloading(type);
    try {
      const response = await api.get(`/reports/sales.${type}`, {
        params: { ...filters, location_id: locationId },
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `edvatiq-${isCollege ? "fees" : "sales"}-${filters.start}-${filters.end}.${type}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      toast.error("Could not generate this report");
    } finally {
      setDownloading(null);
    }
  };

  if (isLoading && !data) return <PageSkeleton />;
  if (error && !data) return <PageShell><ErrorState retry={reportQuery.refetch} /></PageShell>;

  const metrics = data?.metrics || (data ? [
    { id: "billed", label: "Billed", value: data.billed_paise, format: "money" },
    { id: "collected", label: "Collected", value: data.collected_paise, format: "money" },
    { id: "outstanding", label: "Outstanding", value: data.outstanding_paise, format: "money", tone: data.outstanding_paise ? "warning" : "neutral" },
    { id: "invoices", label: "Invoices", value: data.invoice_count },
  ] : []);
  const trend = data?.series?.find((series) => series.id === "sales_flow")?.points || [];
  const trendData = trend.map((point) => ({
    date: point.date,
    billed: Number(point.billed_paise || 0) / 100,
    collected: Number(point.collected_paise || 0) / 100,
  }));
  const statusBreakdown = data?.breakdowns?.find((item) => item.id === "invoice_status")?.items || [];
  const outstanding = data?.queues?.find((queue) => queue.id === "outstanding_invoices")?.items || [];
  const canExport = data?.capabilities?.exports !== false;

  return <PageShell className="reveal">
    <PageHeader
      eyebrow="Performance"
      title="Reports"
      description={isCollege ? "Fee collections, open balances, and export-ready finance records within your access." : "Live financial performance, collections, and export-ready records within your access."}
      actions={<span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground">
        <span className="h-1.5 w-1.5 rounded-full bg-positive" />
        Live through {filters.end}
      </span>}
    />

    <FilterToolbar className="gap-3 p-3">
      <DateField label="From" value={start} onChange={setStart} />
      <DateField label="To" value={end} onChange={setEnd} />
      <Button className="sm:ml-auto" variant="outline" onClick={apply} disabled={isFetching}>
        {isFetching ? "Updating..." : "Apply range"}
      </Button>
    </FilterToolbar>

    <MetricStrip metrics={metrics} loading={isFetching && !data} onMetric={() => navigate("/app/sales")} />

    {trendData.length || statusBreakdown.length ? <div className="grid min-w-0 items-stretch gap-5 xl:grid-cols-12">
      {trendData.length > 0 && <ChartPanel
        className={statusBreakdown.length ? "xl:col-span-8" : "xl:col-span-12"}
        title={isCollege ? "Fee flow" : "Sales flow"}
        subtitle={isCollege ? "Fees invoiced and payments captured in the selected period" : "Billed revenue and captured payments in the selected period"}
        action={<ChartLineUp size={20} className="text-muted-foreground" />}
        fillHeight
      >
        <BusinessChart
          data={trendData}
          type="area"
          format="money"
          series={[{ key: "billed", label: isCollege ? "Fees invoiced" : "Billed" }, { key: "collected", label: "Collected" }]}
          ariaLabel={isCollege ? "Fees invoiced and collected over time" : "Billed revenue and collections over time"}
        />
      </ChartPanel>}

      {statusBreakdown.length > 0 && <ChartPanel
        className={trendData.length ? "xl:col-span-4" : "xl:col-span-12"}
        title="Invoice state"
        subtitle="How invoices are distributed"
        action={<Receipt size={20} className="text-muted-foreground" />}
        fillHeight
      >
        <BusinessChart
          data={statusBreakdown}
          xKey="label"
          type="donut"
          series={[{ key: "value", label: "Invoices" }]}
          ariaLabel="Invoice status distribution"
        />
      </ChartPanel>}
    </div> : <EmptyState variant="section" alignment="left" icon={ChartLineUp} title="No financial activity in this range" description={`Invoices and captured payments recorded from ${filters.start} to ${filters.end} will appear here.`} />}

    <div className="grid min-w-0 items-start gap-5 xl:grid-cols-12">
      <QueuePanel
        className="xl:col-span-7"
        title={isCollege ? "Outstanding fees" : "Outstanding work"}
        subtitle="Highest open balances in this report period"
        action={<Button variant="ghost" size="sm" onClick={() => navigate("/app/sales")}>{isCollege ? "View fees" : "View sales"} <ArrowRight className="ml-1" /></Button>}
        items={outstanding}
        empty={<EmptyState variant="inline" icon={Receipt} title="Nothing outstanding" description="Every invoice in this period is settled or closed." className="m-4" />}
        renderItem={(item) => <button
          type="button"
          onClick={() => navigate("/app/sales")}
          className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-surface-hover"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-warning/10 text-warning"><Wallet size={18} /></span>
          <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{item.title}</span><span className="mt-0.5 block text-xs text-muted-foreground">{item.detail}</span></span>
          <StatusBadge status={item.status} />
        </button>}
      />

      <InsightPanel
        className="xl:col-span-5"
        title="Export centre"
        subtitle={canExport ? "Download the current permission-scoped report." : "Exports are not included in your current access."}
        icon={canExport ? DownloadSimple : Lock}
      >
        {canExport ? <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <ExportCard icon={FilePdf} title={isCollege ? "Fee PDF" : "Sales PDF"} detail="Presentation-ready summary" action={() => download("pdf")} loading={downloading === "pdf"} />
          <ExportCard icon={FileXls} title={isCollege ? "Fee workbook" : "Sales workbook"} detail="Detailed finance rows" action={() => download("xlsx")} loading={downloading === "xlsx"} />
        </div> : <EmptyState compact icon={Lock} title="Exports unavailable" description="You can still use every live report on this page." className="m-4" />}
      </InsightPanel>
    </div>
  </PageShell>;
}

function CollegeReports() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [windowDays, setWindowDays] = useState(30);
  const dashboard = useGetCollegePlacementDashboardQuery({});
  const canViewLeaderboards = can("college.readiness.view") && can("college.coding.view");
  const leaderboards = useGetCollegeLeaderboardsQuery(
    { window_days: windowDays, limit: 10 },
    withSkip(QUERY_POLICIES.analytical, !canViewLeaderboards),
  );
  const data = dashboard.data;
  const metrics = data?.metrics || {};
  const readinessRows = leaderboards.data?.readiness || [];
  const codingRows = leaderboards.data?.coding || [];

  if (dashboard.isLoading && !data) return <PageSkeleton />;
  if (dashboard.error && !data) return <PageShell><ErrorState title="Placement reports could not be loaded" description={dashboard.error?.data?.detail} retry={dashboard.refetch} /></PageShell>;

  const summary = [
    { id: "participating", label: "Participating students", value: metrics.participating_students, icon: Student },
    { id: "ready", label: "Placement ready", value: metrics.placement_ready, tone: "positive", icon: Target },
    { id: "support", label: "Needs support", value: metrics.needs_support, tone: metrics.needs_support ? "warning" : "neutral", icon: WarningCircle },
    { id: "placed", label: "Placed students", value: metrics.placed_students, icon: CheckCircle },
    { id: "drives", label: "Active drives", value: metrics.active_drives, icon: Briefcase },
    { id: "offers", label: "Offers", value: metrics.offers, icon: GraduationCap },
  ];
  const hasEvidence = Number(metrics.participating_students || 0) > 0;
  const readinessColumns = [
    { key: "rank", label: "Rank", render: (row) => row.rank || "-" },
    { key: "student", label: "Student", render: (row) => <div><div className="font-semibold">{row.name}</div><div className="mt-1 text-xs text-muted-foreground">{row.admission_number} · {row.program}</div></div> },
    { key: "score", label: "Readiness", render: (row) => row.score == null ? "-" : `${row.score}%` },
    { key: "coverage", label: "Evidence", render: (row) => `${row.coverage_percent || 0}%` },
    { key: "band", label: "Band", render: (row) => <StatusBadge status={row.band === "ready" ? "active" : row.band === "needs_support" ? "warning" : "pending"} label={String(row.band || "review").replaceAll("_", " ")} /> },
  ];

  return <PageShell className="reveal">
    <PageHeader
      eyebrow="Student success analytics"
      title="Placement reports"
      description="Compare readiness, attendance, academic evidence, coding progress, applications, and outcomes across the College."
      actions={<Button onClick={() => navigate("/app/college?section=placements")}>Open placement pipeline<ArrowRight className="ml-2" /></Button>}
    />

    {!hasEvidence ? <EmptyState variant="page" alignment="left" icon={GraduationCap} title="Placement evidence will appear here" description="Admit students and add academic, attendance, coding, or placement records to build reports." primaryAction={<Button onClick={() => navigate("/app/college?section=students")}>Open students</Button>} /> : <>
      <MetricStrip metrics={summary} loading={dashboard.isFetching && !data} />

      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-12">
        <ChartPanel className="xl:col-span-4" title="Readiness distribution" subtitle="Evidence-backed placement bands">
          <BusinessChart data={data?.readiness_distribution || []} xKey="label" type="donut" series={[{ key: "value", label: "Students" }]} height={280} ariaLabel="Student readiness distribution" />
        </ChartPanel>
        <ChartPanel className="xl:col-span-8" title="Batch attendance trend" subtitle="Average attendance across participating students">
          <BusinessChart data={data?.attendance_trend || []} xKey="date" type="area" series={[{ key: "attendance", label: "Attendance %" }]} height={280} ariaLabel="Batch attendance trend" />
        </ChartPanel>
      </div>

      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-12">
        <ChartPanel className="xl:col-span-7" title="Placement funnel" subtitle="Applications at each recruitment stage">
          <BusinessChart data={(data?.placement_funnel || []).filter((row) => row.value > 0)} xKey="label" type="bar" series={[{ key: "value", label: "Applications" }]} height={290} ariaLabel="Placement application funnel" />
        </ChartPanel>
        <ChartPanel className="xl:col-span-5" title="Offer outcomes" subtitle="Recorded decisions for placement offers">
          <BusinessChart data={data?.offer_outcomes || []} xKey="label" type="donut" series={[{ key: "value", label: "Offers" }]} height={290} ariaLabel="Placement offer outcomes" />
        </ChartPanel>
      </div>

      <Surface className="overflow-hidden">
        <div className="border-b px-4 py-4 sm:px-5"><h2 className="font-semibold">Department comparison</h2><p className="mt-1 text-xs text-muted-foreground">Readiness and outcomes by academic department.</p></div>
        <div className="divide-y">{(data?.department_comparison || []).map((row) => <div key={row.department_id} className="grid gap-3 px-4 py-4 sm:px-5 md:grid-cols-[minmax(180px,1fr)_repeat(4,minmax(80px,.45fr))] md:items-center"><div className="font-semibold">{row.department}</div><ReportValue label="Students" value={row.students} /><ReportValue label="Ready" value={row.ready} /><ReportValue label="Placed" value={row.placed} /><ReportValue label="Attendance" value={row.attendance == null ? "-" : `${row.attendance}%`} /></div>)}</div>
      </Surface>

      {canViewLeaderboards && <><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="text-lg font-semibold">Evidence leaderboards</h2><p className="mt-1 text-sm text-muted-foreground">Transparent rankings based only on verified College evidence.</p></div><SegmentControl value={windowDays} onChange={setWindowDays} items={[{ value: 30, label: "30 days" }, { value: 90, label: "90 days" }]} /></div>
      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-12">
        <Surface className="overflow-hidden xl:col-span-7"><div className="border-b px-4 py-4 sm:px-5"><h3 className="flex items-center gap-2 font-semibold"><Medal />Readiness leaders</h3></div><DataTable className="rounded-none border-0 shadow-none" loading={leaderboards.isLoading} rows={readinessRows} columns={readinessColumns} onRowClick={(row) => navigate(`/app/clients/${row.client_id}`)} empty={<EmptyState variant="inline" title="No rankable readiness evidence" description="Students remain visible after they meet the minimum evidence coverage." className="m-4" />} /></Surface>
        <ChartPanel className="xl:col-span-5" title="Coding leaders" subtitle="Solved problems from consented coding profiles">
          <BusinessChart data={codingRows.slice(0, 8).map((row) => ({ name: row.name, solved: row.total_solved }))} xKey="name" type="bar" series={[{ key: "solved", label: "Solved" }]} height={320} ariaLabel="Student coding leaderboard" />
        </ChartPanel>
      </div></>}
    </>}
  </PageShell>;
}

function ReportValue({ label, value }) {
  return <div className="flex items-center justify-between text-sm md:block"><span className="text-xs text-muted-foreground md:block">{label}</span><span className="font-semibold md:mt-1 md:block">{value}</span></div>;
}

function DateField({ label, value, onChange }) {
  return <label className="min-w-0 flex-1 sm:max-w-52">
    <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">{label}</span>
    <Input type="date" value={value} onChange={(event) => onChange(event.target.value)} />
  </label>;
}

function ExportCard({ icon: Icon, title, detail, action, loading }) {
  return <button
    type="button"
    onClick={action}
    disabled={loading}
    className="group flex min-h-28 flex-col items-start rounded-xl border bg-surface-subtle p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:bg-card hover:shadow-sm disabled:pointer-events-none disabled:opacity-60"
  >
    <span className="grid h-9 w-9 place-items-center rounded-lg bg-card text-accent shadow-sm"><Icon size={19} /></span>
    <span className="mt-3 text-sm font-semibold">{loading ? "Preparing..." : title}</span>
    <span className="mt-0.5 text-xs text-muted-foreground">{detail}</span>
  </button>;
}
