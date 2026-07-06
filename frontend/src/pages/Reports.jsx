import React, { useEffect, useState } from "react";
import api, { API_BASE } from "@/lib/api";
import { tokenStore } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FilePdf, FileXls, Download } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Reports() {
  const [sections, setSections] = useState([]);
  const [exams, setExams] = useState([]);
  const [sectionId, setSectionId] = useState("all");
  const [days, setDays] = useState(30);
  const [examId, setExamId] = useState("");

  useEffect(() => {
    api.get("/academic/sections").then((r) => setSections(r.data));
    api.get("/marks/exams").then((r) => setExams(r.data));
  }, []);

  const download = async (path, filename) => {
    try {
      const token = tokenStore.get();
      const res = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) { toast.error("Download failed"); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Download failed"); }
  };

  return (
    <div className="space-y-6" data-testid="reports-page">
      <header>
        <div className="overline text-muted-foreground">Reports</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Export center</h1>
        <p className="text-sm text-muted-foreground mt-2">Generate PDF and Excel reports directly from your data.</p>
      </header>

      <div className="grid md:grid-cols-3 gap-4">
        <ReportCard title="Students" desc="Full student directory">
          <div className="flex gap-2 mt-4">
            <Button onClick={() => download("/reports/students.pdf", "students.pdf")} className="rounded-sm flex-1" data-testid="dl-students-pdf"><FilePdf size={14} className="mr-2" /> PDF</Button>
            <Button onClick={() => download("/reports/students.xlsx", "students.xlsx")} variant="outline" className="rounded-sm flex-1" data-testid="dl-students-xlsx"><FileXls size={14} className="mr-2" /> Excel</Button>
          </div>
        </ReportCard>

        <ReportCard title="Attendance" desc="Aggregated by student · date range">
          <div className="mt-3 space-y-2">
            <div>
              <Label className="text-xs">Section</Label>
              <Select value={sectionId} onValueChange={setSectionId}>
                <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="all">All</SelectItem>{sections.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Last N days</Label>
              <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
                <SelectTrigger className="rounded-sm"><SelectValue /></SelectTrigger>
                <SelectContent>{[7, 15, 30, 60, 90].map((n) => <SelectItem key={n} value={String(n)}>{n} days</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-2">
              <Button onClick={() => download(`/reports/attendance.pdf?days=${days}${sectionId !== "all" ? `&section_id=${sectionId}` : ""}`, "attendance.pdf")} className="rounded-sm flex-1" data-testid="dl-att-pdf"><FilePdf size={14} className="mr-2" /> PDF</Button>
              <Button onClick={() => download(`/reports/attendance.xlsx?days=${days}${sectionId !== "all" ? `&section_id=${sectionId}` : ""}`, "attendance.xlsx")} variant="outline" className="rounded-sm flex-1" data-testid="dl-att-xlsx"><FileXls size={14} className="mr-2" /> Excel</Button>
            </div>
          </div>
        </ReportCard>

        <ReportCard title="Marks" desc="Per exam · with averages">
          <div className="mt-3 space-y-2">
            <div>
              <Label className="text-xs">Exam</Label>
              <Select value={examId} onValueChange={setExamId}>
                <SelectTrigger className="rounded-sm"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{exams.map((e) => <SelectItem key={e.id} value={e.id}>{e.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-2">
              <Button disabled={!examId} onClick={() => download(`/reports/marks.pdf?exam_id=${examId}`, "marks.pdf")} className="rounded-sm flex-1" data-testid="dl-marks-pdf"><FilePdf size={14} className="mr-2" /> PDF</Button>
              <Button disabled={!examId} onClick={() => download(`/reports/marks.xlsx?exam_id=${examId}`, "marks.xlsx")} variant="outline" className="rounded-sm flex-1" data-testid="dl-marks-xlsx"><FileXls size={14} className="mr-2" /> Excel</Button>
            </div>
          </div>
        </ReportCard>
      </div>
    </div>
  );
}

function ReportCard({ title, desc, children }) {
  return (
    <Card className="rounded-sm border-border">
      <CardContent className="p-5">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="font-display text-xl font-semibold tracking-tight">{title}</div>
            <div className="text-xs text-muted-foreground mt-1">{desc}</div>
          </div>
          <Download size={18} className="text-muted-foreground" />
        </div>
        {children}
      </CardContent>
    </Card>
  );
}
