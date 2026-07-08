import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Plus, TrashSimple, FloppyDisk, Books, CalendarCheck, GraduationCap, DownloadSimple, UploadSimple } from "@phosphor-icons/react";

/**
 * Academic Config — tenant-defined exam types, attendance statuses, grade bands.
 * All rows are metadata; no hardcoded assumptions.
 */
export default function AcademicConfig() {
  const fileRef = React.useRef(null);
  const [importing, setImporting] = React.useState(false);

  const exportConfig = async () => {
    try {
      const { data } = await api.get("/config/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `athena-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Config exported");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Export failed");
    }
  };

  const onImportFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const mode = window.confirm(
        "Click OK to REPLACE existing config with the file (destructive).\n\n" +
        "Click Cancel to MERGE (upsert by code — non-destructive)."
      ) ? "replace" : "merge";
      const payload = {
        mode,
        terminology: parsed.terminology,
        exam_types: parsed.exam_types,
        attendance_statuses: parsed.attendance_statuses,
        grade_bands: parsed.grade_bands,
      };
      const { data } = await api.post("/config/import", payload);
      toast.success(`Imported (${mode}) — ${JSON.stringify(data.stats)}`);
      // Force a full page refresh so all tabs re-fetch
      window.location.reload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || err.message || "Import failed");
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="space-y-6" data-testid="academic-config-page">
      <header className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="overline text-muted-foreground">Configuration</div>
          <h1 className="text-4xl font-display font-bold tracking-tight mt-1">Academic Engine</h1>
          <p className="text-sm text-muted-foreground mt-2">
            Define your organization&apos;s own exam types, attendance statuses, and grading bands.
            Nothing here is hardcoded — everything you configure drives the ERP and the AI assistant.
          </p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept="application/json" onChange={onImportFile} className="hidden" data-testid="config-import-input" />
          <Button variant="outline" className="rounded-sm" onClick={() => fileRef.current?.click()} disabled={importing} data-testid="config-import-btn">
            <UploadSimple size={14} className="mr-2" /> {importing ? "Importing…" : "Import JSON"}
          </Button>
          <Button variant="outline" className="rounded-sm" onClick={exportConfig} data-testid="config-export-btn">
            <DownloadSimple size={14} className="mr-2" /> Export JSON
          </Button>
        </div>
      </header>

      <Tabs defaultValue="exam-types">
        <TabsList>
          <TabsTrigger value="exam-types"><Books size={14} className="mr-2" />Exam Types</TabsTrigger>
          <TabsTrigger value="attendance"><CalendarCheck size={14} className="mr-2" />Attendance Statuses</TabsTrigger>
          <TabsTrigger value="grades"><GraduationCap size={14} className="mr-2" />Grade Bands</TabsTrigger>
        </TabsList>
        <TabsContent value="exam-types"><ExamTypesTab /></TabsContent>
        <TabsContent value="attendance"><AttendanceStatusesTab /></TabsContent>
        <TabsContent value="grades"><GradeBandsTab /></TabsContent>
      </Tabs>
    </div>
  );
}

// ------------------------------------------------- reusable metadata table -- //

function MetaTable({ title, columns, rows, onSave, onDelete, blank }) {
  const [drafts, setDrafts] = useState({});
  const [newRow, setNewRow] = useState(blank);

  const setDraft = (id, key, val) => setDrafts((d) => ({ ...d, [id]: { ...(d[id] ?? {}), [key]: val } }));
  const rowValue = (row, key) => (drafts[row.id]?.[key] !== undefined ? drafts[row.id][key] : row[key]);
  const dirty = (id) => drafts[id] && Object.keys(drafts[id]).length > 0;

  return (
    <Card className="rounded-sm border-border">
      <CardHeader>
        <CardTitle className="font-display text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {columns.map((c) => (
                  <th key={c.key} className="text-left px-2 py-2 overline text-muted-foreground">
                    {c.label}
                  </th>
                ))}
                <th className="w-24 px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td className="text-center py-6 text-muted-foreground" colSpan={columns.length + 1}>
                    None configured yet.
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-border">
                  {columns.map((c) => (
                    <td key={c.key} className="px-2 py-2">
                      <CellEditor
                        column={c}
                        value={rowValue(r, c.key)}
                        onChange={(v) => setDraft(r.id, c.key, v)}
                      />
                    </td>
                  ))}
                  <td className="px-2 py-2 flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="rounded-sm"
                      disabled={!dirty(r.id)}
                      onClick={async () => {
                        await onSave(r.id, { ...r, ...drafts[r.id] });
                        setDrafts((d) => ({ ...d, [r.id]: {} }));
                      }}
                    >
                      <FloppyDisk size={12} />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="rounded-sm text-destructive"
                      onClick={() => onDelete(r.id)}
                    >
                      <TrashSimple size={12} />
                    </Button>
                  </td>
                </tr>
              ))}
              {/* Add-new row */}
              <tr className="bg-secondary/30">
                {columns.map((c) => (
                  <td key={c.key} className="px-2 py-2">
                    <CellEditor
                      column={c}
                      value={newRow[c.key]}
                      onChange={(v) => setNewRow((n) => ({ ...n, [c.key]: v }))}
                    />
                  </td>
                ))}
                <td className="px-2 py-2">
                  <Button
                    size="sm"
                    className="rounded-sm"
                    onClick={async () => {
                      await onSave(null, newRow);
                      setNewRow(blank);
                    }}
                  >
                    <Plus size={12} />
                  </Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function CellEditor({ column, value, onChange }) {
  if (column.type === "boolean") {
    return <Switch checked={!!value} onCheckedChange={onChange} />;
  }
  if (column.type === "number") {
    return (
      <Input
        type="number"
        step="any"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        className="rounded-sm h-8 w-24"
      />
    );
  }
  return (
    <Input
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-sm h-8"
      placeholder={column.placeholder}
    />
  );
}

// ------------------------------------------------------------ Exam Types tab //

function ExamTypesTab() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/config/exam-types").then((r) => setRows(r.data)).catch(() => toast.error("Failed to load"));
  useEffect(() => { load(); }, []);
  const save = async (id, body) => {
    try {
      if (id) await api.patch(`/config/exam-types/${id}`, body);
      else await api.post(`/config/exam-types`, body);
      toast.success("Saved");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  const del = async (id) => {
    if (!window.confirm("Delete exam type?")) return;
    await api.delete(`/config/exam-types/${id}`);
    toast.success("Deleted"); load();
  };
  return (
    <MetaTable
      title="Assessment types (weightage, max marks, finality)"
      rows={rows}
      onSave={save}
      onDelete={del}
      blank={{ code: "", name: "", weightage_default: 0, max_marks_default: 100, is_final: false, display_order: 0, is_active: true, description: "" }}
      columns={[
        { key: "code", label: "Code", placeholder: "mid_sem" },
        { key: "name", label: "Name", placeholder: "Mid Semester" },
        { key: "weightage_default", label: "Weightage %", type: "number" },
        { key: "max_marks_default", label: "Max marks", type: "number" },
        { key: "is_final", label: "Final?", type: "boolean" },
        { key: "display_order", label: "Order", type: "number" },
      ]}
    />
  );
}

function AttendanceStatusesTab() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/config/attendance-statuses").then((r) => setRows(r.data)).catch(() => toast.error("Failed"));
  useEffect(() => { load(); }, []);
  const save = async (id, body) => {
    try {
      if (id) await api.patch(`/config/attendance-statuses/${id}`, body);
      else await api.post(`/config/attendance-statuses`, body);
      toast.success("Saved"); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  const del = async (id) => {
    if (!window.confirm("Delete status?")) return;
    await api.delete(`/config/attendance-statuses/${id}`);
    toast.success("Deleted"); load();
  };
  return (
    <MetaTable
      title="Attendance status catalogue"
      rows={rows}
      onSave={save}
      onDelete={del}
      blank={{ code: "", label: "", counts_as_present: false, is_leave: false, color: "", display_order: 0, is_active: true }}
      columns={[
        { key: "code", label: "Code", placeholder: "OD" },
        { key: "label", label: "Label", placeholder: "On Duty" },
        { key: "counts_as_present", label: "Counts present?", type: "boolean" },
        { key: "is_leave", label: "Leave?", type: "boolean" },
        { key: "color", label: "Color", placeholder: "#3b82f6" },
        { key: "display_order", label: "Order", type: "number" },
      ]}
    />
  );
}

function GradeBandsTab() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/config/grade-bands").then((r) => setRows(r.data)).catch(() => toast.error("Failed"));
  useEffect(() => { load(); }, []);
  const save = async (id, body) => {
    try {
      if (id) await api.patch(`/config/grade-bands/${id}`, body);
      else await api.post(`/config/grade-bands`, body);
      toast.success("Saved"); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  const del = async (id) => {
    if (!window.confirm("Delete grade band?")) return;
    await api.delete(`/config/grade-bands/${id}`);
    toast.success("Deleted"); load();
  };
  return (
    <MetaTable
      title="Grading scale (percent ranges → letter grade)"
      rows={rows}
      onSave={save}
      onDelete={del}
      blank={{ min_percent: 0, max_percent: 100, grade: "", grade_point: 0, description: "", display_order: 0, is_active: true }}
      columns={[
        { key: "min_percent", label: "Min %", type: "number" },
        { key: "max_percent", label: "Max %", type: "number" },
        { key: "grade", label: "Grade", placeholder: "A+" },
        { key: "grade_point", label: "GP", type: "number" },
        { key: "description", label: "Description", placeholder: "Excellent" },
        { key: "display_order", label: "Order", type: "number" },
      ]}
    />
  );
}
