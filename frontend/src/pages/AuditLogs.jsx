import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";

export default function AuditLogs() {
  const [logs, setLogs] = useState([]);
  useEffect(() => { api.get("/audit-logs").then((r) => setLogs(r.data)); }, []);
  return (
    <div className="space-y-6" data-testid="audit-page">
      <header>
        <div className="overline text-muted-foreground">Compliance</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Audit log</h1>
        <p className="text-sm text-muted-foreground mt-2">Every mutation and AI query, in one place.</p>
      </header>
      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3">Time</th>
                <th className="text-left px-4 py-3">Action</th>
                <th className="text-left px-4 py-3">Resource</th>
                <th className="text-left px-4 py-3">Tool</th>
                <th className="text-left px-4 py-3">IP</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 && <tr><td colSpan={5} className="text-center py-10 text-muted-foreground">No entries.</td></tr>}
              {logs.map((l) => (
                <tr key={l.id} className="border-t border-border">
                  <td className="px-4 py-2 font-mono text-xs">{new Date(l.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2 font-mono text-xs">{l.action}</td>
                  <td className="px-4 py-2 text-muted-foreground text-xs">{l.resource_type || "—"} {l.resource_id ? `· ${l.resource_id.slice(0, 8)}` : ""}</td>
                  <td className="px-4 py-2 font-mono text-xs">{l.tool || "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{l.ip_address || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
