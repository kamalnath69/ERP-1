import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Robot, Plus, TrashSimple, Info } from "@phosphor-icons/react";

/**
 * UserAIScopes — manage per-user AI Access Scopes.
 * Props:
 *   userId: string
 *   canManage: boolean (true if current viewer has ai.scopes.manage or roles.manage)
 */
export default function UserAIScopes({ userId, canManage }) {
  const [scopes, setScopes] = useState([]);
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(true);

  // add form
  const [type, setType] = useState("");
  const [typeMode, setTypeMode] = useState("preset"); // 'preset' | 'custom'
  const [customType, setCustomType] = useState("");
  const [value, setValue] = useState("");
  const [customValue, setCustomValue] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        api.get(`/users/${userId}/scopes`),
        api.get(`/scopes/catalog`),
      ]);
      setScopes(s.data);
      setCatalog(c.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load scopes");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const currentType = typeMode === "custom" ? customType.trim() : type;
  const hasPicker = catalog?.pickers?.[currentType]?.length > 0;
  const finalValue = hasPicker ? value : customValue.trim();

  const addScope = async () => {
    if (!currentType || !finalValue) {
      toast.error("Pick a scope type and a value");
      return;
    }
    setSaving(true);
    try {
      await api.post(`/users/${userId}/scopes`, {
        scope_type: currentType,
        scope_value: finalValue,
      });
      toast.success("Scope added");
      setType("");
      setCustomType("");
      setValue("");
      setCustomValue("");
      setTypeMode("preset");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add scope");
    } finally {
      setSaving(false);
    }
  };

  const removeScope = async (id) => {
    if (!window.confirm("Remove this AI access scope?")) return;
    try {
      await api.delete(`/scopes/${id}`);
      toast.success("Scope removed");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to remove");
    }
  };

  const grouped = useMemo(() => {
    const m = new Map();
    for (const s of scopes) {
      if (!m.has(s.scope_type)) m.set(s.scope_type, []);
      m.get(s.scope_type).push(s);
    }
    return Array.from(m.entries());
  }, [scopes]);

  const labelForValue = (t, v) => {
    const p = catalog?.pickers?.[t]?.find((x) => x.value === v);
    return p ? p.label : v;
  };

  const allTypes = useMemo(() => {
    const merged = new Set([
      ...(catalog?.known_types || []),
      ...(catalog?.tenant_types || []),
    ]);
    return Array.from(merged).sort();
  }, [catalog]);

  return (
    <Card className="rounded-sm border-border" data-testid="ai-scopes-panel">
      <CardHeader>
        <CardTitle className="font-display text-lg flex items-center gap-2">
          <Robot size={16} className="text-accent" /> AI Access Scopes
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-xs text-muted-foreground flex items-start gap-2">
          <Info size={14} className="mt-0.5 shrink-0" />
          <span>
            Scopes control which data this user can query through the AI assistant.
            <b> No scopes = full tenant access.</b> Add scopes to restrict — e.g. a HOD
            with a <code className="font-mono text-[11px]">department</code> scope can only ask about
            students in that department. Any scope type is accepted (<i>free-form</i>); known types
            drive AI SQL filters.
          </span>
        </div>

        {/* Existing scopes */}
        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : scopes.length === 0 ? (
          <div className="border border-dashed border-border p-4 text-sm text-muted-foreground">
            No scopes attached — user has <b>full tenant</b> AI access.
            Assign the user as a class advisor or add faculty assignments to auto-scope them,
            or use the form below to add explicit scopes.
          </div>
        ) : (
          <div className="space-y-3">
            {grouped.map(([t, items]) => (
              <div key={t} className="border border-border">
                <div className="px-3 py-2 bg-secondary/40 overline flex items-center justify-between">
                  <span>{t}</span>
                  {catalog?.known_types?.includes(t) ? null : (
                    <Badge variant="outline" className="rounded-sm text-[10px]">custom</Badge>
                  )}
                </div>
                <ul className="divide-y divide-border">
                  {items.map((s) => (
                    <li
                      key={s.id || `${s.scope_type}:${s.scope_value}`}
                      className={`px-3 py-2 flex items-center justify-between text-sm ${s.is_implicit ? "bg-secondary/30" : ""}`}
                      data-testid={`scope-row-${s.id || s.scope_value}`}
                    >
                      <div className="flex-1">
                        <div className="font-medium flex items-center gap-2">
                          <span>{labelForValue(s.scope_type, s.scope_value)}</span>
                          {s.is_implicit && (
                            <Badge variant="outline" className="rounded-sm text-[10px] uppercase">
                              auto · {s.source === "faculty_assignment" ? "assignment" : s.source === "section_advisor" ? "advisor" : "implicit"}
                            </Badge>
                          )}
                        </div>
                        <div className="text-[11px] font-mono text-muted-foreground">
                          {s.scope_value}
                        </div>
                      </div>
                      {canManage && !s.is_implicit && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="rounded-sm text-destructive"
                          onClick={() => removeScope(s.id)}
                          data-testid={`scope-remove-${s.id}`}
                        >
                          <TrashSimple size={14} />
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {/* Add form */}
        {canManage && (
          <div className="border border-border p-3 space-y-3" data-testid="scope-add-form">
            <div className="overline">Add a scope</div>
            <div className="grid md:grid-cols-3 gap-3">
              <div>
                <Label className="overline text-muted-foreground">Scope type</Label>
                <div className="mt-1 flex gap-2">
                  {typeMode === "preset" ? (
                    <Select value={type} onValueChange={setType}>
                      <SelectTrigger className="rounded-sm" data-testid="scope-type-select">
                        <SelectValue placeholder="Choose…" />
                      </SelectTrigger>
                      <SelectContent>
                        {allTypes.map((t) => (
                          <SelectItem key={t} value={t}>{t}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      value={customType}
                      onChange={(e) => setCustomType(e.target.value)}
                      placeholder="custom_type"
                      className="rounded-sm"
                      data-testid="scope-type-custom"
                    />
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="rounded-sm"
                    onClick={() => setTypeMode((m) => (m === "preset" ? "custom" : "preset"))}
                    data-testid="scope-type-toggle"
                  >
                    {typeMode === "preset" ? "Custom" : "Preset"}
                  </Button>
                </div>
              </div>

              <div className="md:col-span-2">
                <Label className="overline text-muted-foreground">Value</Label>
                <div className="mt-1">
                  {hasPicker ? (
                    <Select value={value} onValueChange={setValue}>
                      <SelectTrigger className="rounded-sm" data-testid="scope-value-select">
                        <SelectValue placeholder="Choose value…" />
                      </SelectTrigger>
                      <SelectContent>
                        {catalog.pickers[currentType].map((p) => (
                          <SelectItem key={p.value} value={p.value}>
                            {p.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      value={customValue}
                      onChange={(e) => setCustomValue(e.target.value)}
                      placeholder={
                        currentType === "faculty_assignment"
                          ? "subject_id:section_id"
                          : "free-form value"
                      }
                      className="rounded-sm"
                      data-testid="scope-value-custom"
                    />
                  )}
                </div>
              </div>
            </div>
            <div className="flex justify-end">
              <Button
                onClick={addScope}
                disabled={saving || !currentType || !finalValue}
                className="rounded-sm"
                data-testid="scope-add-btn"
              >
                <Plus size={14} className="mr-2" /> {saving ? "Adding…" : "Add scope"}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
