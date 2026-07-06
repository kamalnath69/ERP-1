import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { CheckCircle } from "@phosphor-icons/react";

export default function Billing() {
  const [plans, setPlans] = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [invoices, setInvoices] = useState([]);

  const load = async () => {
    const [p, s, i] = await Promise.all([api.get("/billing/plans"), api.get("/billing/subscription"), api.get("/billing/invoices")]);
    setPlans(p.data.plans);
    setSubscription(s.data.subscription);
    setInvoices(i.data);
  };
  useEffect(() => { load(); }, []);

  const upgrade = async (plan) => {
    try {
      const { data } = await api.post("/billing/orders", { plan });
      toast("Order created", { description: `Order ${data.order_id || data.invoice_id}` });
      // In the absence of live Razorpay keys, use dev-only mock-pay endpoint.
      await api.post(`/billing/orders/${data.invoice_id}/mock-pay`);
      toast.success(`Upgraded to ${plan}`);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Payment failed");
    }
  };

  return (
    <div className="space-y-6" data-testid="billing-page">
      <header>
        <div className="overline text-muted-foreground">Billing</div>
        <h1 className="text-3xl font-display font-bold tracking-tight mt-1">Subscription & invoices</h1>
      </header>

      <Card className="rounded-sm border-border">
        <CardContent className="p-6 flex items-baseline justify-between flex-wrap gap-4">
          <div>
            <div className="overline">Current plan</div>
            <div className="font-display text-3xl mt-1 uppercase" data-testid="current-plan">{subscription?.plan || "trial"}</div>
            <div className="text-xs text-muted-foreground mt-1">Status: {subscription?.status || "trialing"}</div>
          </div>
          <div className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Powered by Razorpay
          </div>
        </CardContent>
      </Card>

      <div className="grid md:grid-cols-3 gap-4">
        {plans.map((p) => (
          <Card key={p.id} className="rounded-sm border-border">
            <CardContent className="p-6">
              <div className="font-display text-xl tracking-tight">{p.name}</div>
              <div className="mt-3 font-display text-3xl font-bold">₹{p.price_inr.toLocaleString()}<span className="text-sm font-sans text-muted-foreground">/mo</span></div>
              <ul className="mt-4 space-y-2 text-sm">
                {p.features.map((f) => <li key={f} className="flex gap-2"><CheckCircle size={14} className="text-accent mt-0.5" /> {f}</li>)}
              </ul>
              <Button onClick={() => upgrade(p.id)} className="mt-6 w-full rounded-sm" variant={p.id === "pro" ? "default" : "outline"} data-testid={`upgrade-${p.id}-btn`}>
                Upgrade to {p.name}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="rounded-sm border-border">
        <CardContent className="p-0">
          <div className="px-4 py-3 overline border-b border-border">Invoices</div>
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-widest">
              <tr>
                <th className="text-left px-4 py-3">Date</th>
                <th className="text-left px-4 py-3">Description</th>
                <th className="text-right px-4 py-3">Amount</th>
                <th className="text-left px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {invoices.length === 0 && <tr><td colSpan={4} className="text-center py-10 text-muted-foreground">No invoices yet.</td></tr>}
              {invoices.map((i) => (
                <tr key={i.id} className="border-t border-border">
                  <td className="px-4 py-2 font-mono text-xs">{new Date(i.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2">{i.description}</td>
                  <td className="px-4 py-2 text-right font-mono">₹{i.amount.toLocaleString()}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-1 rounded-sm font-mono uppercase ${i.status === "paid" ? "bg-emerald-100 text-emerald-800" : "bg-muted"}`}>{i.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
