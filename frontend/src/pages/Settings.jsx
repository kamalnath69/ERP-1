import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

export default function Settings() {
  const { organization, refreshMe } = useAuth();
  const [flags, setFlags] = useState([]);
  const [aiProvider, setAiProvider] = useState(organization?.ai_provider || "openai");
  const [aiModel, setAiModel] = useState(organization?.ai_model || "gpt-5.4");

  useEffect(() => { api.get("/feature-flags").then((r) => setFlags(r.data)); }, []);

  const toggleFlag = async (id) => {
    await api.post(`/feature-flags/${id}/toggle`);
    api.get("/feature-flags").then((r) => setFlags(r.data));
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
    </div>
  );
}
