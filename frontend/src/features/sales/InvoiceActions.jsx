import React, { useEffect, useState } from "react";
import { Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

import { DrawerForm, Surface, formatMetric } from "@/components/system";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useRecordSalePaymentMutation, useVoidSaleInvoiceMutation } from "@/features/sales/salesApi";


export function PaymentDrawer({ invoice, onOpenChange, onCompleted }) {
  const [recordPayment, result] = useRecordSalePaymentMutation();
  const [form, setForm] = useState({ amount: "", method: "upi", reference: "" });
  const balance = invoice?.balance_paise ?? 0;
  useEffect(() => {
    if (invoice) setForm({ amount: "", method: "upi", reference: "" });
  }, [invoice]);
  const submit = async (event) => {
    event.preventDefault();
    const amount = Math.round(Number(form.amount) * 100);
    if (!amount || amount > balance) return;
    try {
      const payment = await recordPayment({
        invoiceId: invoice.id,
        amount_paise: amount,
        method: form.method,
        reference: form.reference || null,
        version: invoice.version,
        idempotency_key: crypto.randomUUID(),
      }).unwrap();
      toast.success("Payment recorded");
      onCompleted?.(payment);
      onOpenChange(false);
    } catch (error) {
      toast.error(error?.data?.detail || "Payment could not be recorded");
    }
  };
  return <DrawerForm
    open={Boolean(invoice)}
    onOpenChange={onOpenChange}
    title="Record payment"
    description={invoice ? `${invoice.invoice_number} has ${money(balance)} remaining.` : ""}
  >
    <form onSubmit={submit} className="space-y-5">
      <Field label="Amount (INR)"><Input required autoFocus type="number" min="0.01" max={balance / 100} step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} placeholder={(balance / 100).toFixed(2)} /></Field>
      <Button type="button" variant="outline" className="w-full" onClick={() => setForm({ ...form, amount: (balance / 100).toFixed(2) })}>Use full balance</Button>
      <Field label="Payment method"><Select value={form.method} onValueChange={(method) => setForm({ ...form, method })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["cash", "upi", "card", "bank"].map((method) => <SelectItem key={method} value={method}>{sentence(method)}</SelectItem>)}</SelectContent></Select></Field>
      <Field label="Reference"><Input value={form.reference} onChange={(event) => setForm({ ...form, reference: event.target.value })} maxLength={120} placeholder="Optional transaction reference" /></Field>
      <Button disabled={result.isLoading || !form.amount} className="w-full">{result.isLoading ? "Recording..." : "Confirm payment"}</Button>
    </form>
  </DrawerForm>;
}


export function VoidInvoiceDrawer({ invoice, onOpenChange, onCompleted }) {
  const [reason, setReason] = useState("");
  const [voidInvoice, result] = useVoidSaleInvoiceMutation();
  useEffect(() => {
    if (invoice) setReason("");
  }, [invoice]);
  const submit = async (event) => {
    event.preventDefault();
    if (reason.trim().length < 3) return;
    try {
      const updated = await voidInvoice({ invoiceId: invoice.id, reason: reason.trim(), version: invoice.version }).unwrap();
      toast.success("Invoice voided and balance updated");
      onCompleted?.(updated);
      onOpenChange(false);
    } catch (error) {
      toast.error(error?.data?.detail || "Invoice could not be voided");
    }
  };
  return <DrawerForm
    open={Boolean(invoice)}
    onOpenChange={onOpenChange}
    title="Void unpaid invoice"
    description={invoice ? `${invoice.invoice_number} will remain in history with the reason and responsible staff member.` : ""}
  >
    <form onSubmit={submit} className="space-y-5">
      <Surface className="border-danger/30 bg-danger/5 p-4">
        <div className="flex gap-3"><Warning className="mt-0.5 shrink-0 text-danger" size={20} /><p className="text-sm leading-6">Only a fully unpaid invoice can be voided. Paid and partially paid invoices require a future refund or credit-note workflow.</p></div>
      </Surface>
      <Field label="Mandatory reason"><Textarea autoFocus required minLength={3} maxLength={500} rows={5} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explain why this invoice is incorrect" /></Field>
      <Button disabled={result.isLoading || reason.trim().length < 3} className="w-full bg-danger text-white hover:bg-danger/90">{result.isLoading ? "Voiding..." : "Void invoice and clear balance"}</Button>
    </form>
  </DrawerForm>;
}


function Field({ label, children }) {
  return <div className="space-y-2"><Label>{label}</Label>{children}</div>;
}

function money(value) {
  return formatMetric(value, "money");
}

function sentence(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
