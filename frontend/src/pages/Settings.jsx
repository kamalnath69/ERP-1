import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import { FloppyDisk } from "@phosphor-icons/react";

export default function Settings() {
  const { organization, refreshMe } = useAuth();
  const [flags, setFlags] = useState([]);
  const [aiProvider, setAiProvider] = useState(organization?.ai_provider || "openai");
  const [aiModel, setAiModel] = useState(organization?.ai_model || "gpt-5.4");

  // Terminology
  const [terms, setTerms] = useState({});
  const [defaults, setDefaults] = useState({});
  const [savingTerms, setSavingTerms] = useState(false);

  useEffect(() => { api.get("/feature-flags").then((r) => setFlags(r.data)); }, []);
  useEffect(() => {
    api.get("/settings/terminology").then((r) => {
      setTerms(r.data.terms || {});
      setDefaults(r.data.defaults || {});
    }).catch(() => {});
  }, []);

  const toggleFlag = async (id) => {
    await api.post(`/feature-flags/${id}/toggle`);
    api.get("/feature-flags").then((r) => setFlags(r.data));
  };

  const saveTerms = async () => {
    setSavingTerms(true);
    try {
      await api.put("/settings/terminology", { terms });
      toast.success("Terminology saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally {
      setSavingTerms(false);
    }
  };

  // AI provider is per-org; only super admin currently has patch endpoint, but Principal can also see this.
  // Simple client-only preview: real save requires super-admin PATCH which is out of scope for tenant settings here.

  return (
    <div className="space-y-6" data-testid="settings-page">
      <header>
        <div className="overline text-muted-foreground">Settings</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Organization</h1>
      </header>

      <Card className="rounded-sm border-border">
        <CardContent className="p-6">
          <div className="overline">Profile</div>
          <div className="grid md:grid-cols-3 gap-4 mt-4 text-sm">
            <div><div className="text-xs text-muted-foreground">Name</div><div>{organization?.name}</div></div>
            <div><div className="text-xs text-muted-foreground">Slug</div><div className="font-mono">{organization?.slug}</div></div>
            <div><div className="text-xs text-muted-foreground">Type</div><div className="font-mono uppercase">{organization?.org_type}</div></div>
            <div><div className="text-xs text-muted-foreground">Plan</div><div className="font-mono uppercase">{organization?.plan}</div></div>
            <div><div className="text-xs text-muted-foreground">AI provider</div><div className="font-mono">{organization?.ai_provider}</div></div>
            <div><div className="text-xs text-muted-foreground">AI model</div><div className="font-mono">{organization?.ai_model}</div></div>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm border-border">
        <CardContent className="p-6">
          <div className="overline">Feature flags</div>
          <div className="mt-4 space-y-3">
            {flags.map((f) => (
              <div key={f.id} className="flex items-center justify-between border border-border p-3">
                <div>
                  <div className="font-mono text-sm">{f.flag}</div>
                  <div className="text-xs text-muted-foreground">Enable or disable per organization</div>
                </div>
                <Switch checked={f.enabled} onCheckedChange={() => toggleFlag(f.id)} data-testid={`flag-${f.flag}`} />
              </div>
            ))}
            {flags.length === 0 && <div className="text-sm text-muted-foreground">No flags configured.</div>}
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-sm border-border" data-testid="terminology-card">
        <CardContent className="p-6">
          <div className="flex items-baseline justify-between">
            <div>
              <div className="overline">Terminology</div>
              <p className="text-xs text-muted-foreground mt-1">
                Rename hierarchy labels for your organization. E.g. call &ldquo;Department&rdquo;
                a &ldquo;Faculty&rdquo; if you are a university, or call &ldquo;Section&rdquo; a &ldquo;Batch&rdquo;.
                Empty values fall back to the default.
              </p>
            </div>
            <Button size="sm" className="rounded-sm" onClick={saveTerms} disabled={savingTerms} data-testid="save-terminology">
              <FloppyDisk size={12} className="mr-2" /> {savingTerms ? "Saving…" : "Save"}
            </Button>
          </div>
          <div className="mt-4 grid md:grid-cols-2 gap-3">
            {Object.entries(defaults).map(([k, defaultLabel]) => (
              <div key={k} className="flex items-center gap-3 border border-border p-3">
                <div className="w-28 shrink-0">
                  <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Key</div>
                  <div className="font-mono text-xs">{k}</div>
                </div>
                <div className="flex-1">
                  <Input
                    value={terms[k] ?? ""}
                    placeholder={defaultLabel}
                    onChange={(e) => setTerms((t) => ({ ...t, [k]: e.target.value }))}
                    className="rounded-sm h-8"
                    data-testid={`term-${k}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
