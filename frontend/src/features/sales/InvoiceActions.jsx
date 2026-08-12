import React, { useEffect, useRef } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

import { DrawerForm, Surface, formatMetric } from "@/components/system";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useRecordSalePaymentMutation, useVoidSaleInvoiceMutation } from "@/features/sales/salesApi";
import { applyApiErrors, FORM_OPTIONS, invoicePaymentSchema, invoiceVoidSchema } from "@/lib/validation";

const paymentDefaults = { amount: "", method: "upi", reference: "", version: "" };
const voidDefaults = { reason: "", version: "" };

export function PaymentDrawer({ invoice, onOpenChange, onCompleted }) {
  const [recordPayment, result] = useRecordSalePaymentMutation();
  const form = useForm({ resolver: zodResolver(invoicePaymentSchema), defaultValues: paymentDefaults, ...FORM_OPTIONS });
  const { clearErrors, control, formState, handleSubmit, reset, setError, setValue } = form;
  const balance = invoice?.balance_paise ?? 0;
  const idempotencyKey = useRef(crypto.randomUUID());
  useEffect(() => {
    if (!invoice) return;
    reset({ ...paymentDefaults, version: invoice.version || "" });
    idempotencyKey.current = crypto.randomUUID();
  }, [invoice, reset]);
  const pending = formState.isSubmitting || result.isLoading;
  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    if (values.amount_paise > balance) {
      setError("amount", { type: "validate", message: `Payment cannot exceed the remaining balance of ${money(balance)}` }, { shouldFocus: true });
      return;
    }
    try {
      const payment = await recordPayment({
        invoiceId: invoice.id,
        amount_paise: values.amount_paise,
        method: values.method,
        reference: values.reference || null,
        version: values.version,
        idempotency_key: idempotencyKey.current,
      }).unwrap();
      toast.success("Payment recorded");
      onCompleted?.(payment);
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { aliases: { amount_paise: "amount" }, fallback: "Payment could not be recorded" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <DrawerForm open={Boolean(invoice)} onOpenChange={(open) => { if (!open && !pending) onOpenChange(false); }} title="Record payment" description={invoice ? `${invoice.invoice_number} has ${money(balance)} remaining.` : ""}>
    <Form {...form}><form noValidate onSubmit={submit} className="space-y-5">
      <InvoiceField control={control} name="amount" label="Amount (INR)"><Input autoFocus inputMode="decimal" placeholder={(balance / 100).toFixed(2)} /></InvoiceField>
      <Button type="button" variant="outline" className="w-full" disabled={pending} onClick={() => setValue("amount", (balance / 100).toFixed(2), { shouldDirty: true, shouldValidate: true })}>Use full balance</Button>
      <FormField control={control} name="method" render={({ field }) => <FormItem><FormLabel>Payment method</FormLabel><Select value={field.value} onValueChange={field.onChange}><FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl><SelectContent>{["cash", "upi", "card", "bank"].map((method) => <SelectItem key={method} value={method}>{sentence(method)}</SelectItem>)}</SelectContent></Select><FormMessage /></FormItem>} />
      <InvoiceField control={control} name="reference" label="Reference"><Input maxLength={120} placeholder="Optional transaction reference" /></InvoiceField>
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" loading={pending} loadingText="Recording..." className="w-full">Confirm payment</Button>
    </form></Form>
  </DrawerForm>;
}

export function VoidInvoiceDrawer({ invoice, onOpenChange, onCompleted }) {
  const [voidInvoice, result] = useVoidSaleInvoiceMutation();
  const form = useForm({ resolver: zodResolver(invoiceVoidSchema), defaultValues: voidDefaults, ...FORM_OPTIONS });
  const { control, formState, handleSubmit, reset, setError } = form;
  useEffect(() => { if (invoice) reset({ reason: "", version: invoice.version || "" }); }, [invoice, reset]);
  const pending = formState.isSubmitting || result.isLoading;
  const submit = handleSubmit(async (values) => {
    try {
      const updated = await voidInvoice({ invoiceId: invoice.id, reason: values.reason, version: values.version }).unwrap();
      toast.success("Invoice voided and balance updated");
      onCompleted?.(updated);
      onOpenChange(false);
    } catch (error) {
      const normalized = applyApiErrors(error, setError, { fallback: "Invoice could not be voided" });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });
  return <DrawerForm open={Boolean(invoice)} onOpenChange={(open) => { if (!open && !pending) onOpenChange(false); }} title="Void unpaid invoice" description={invoice ? `${invoice.invoice_number} will remain in history with the reason and responsible staff member.` : ""}>
    <Form {...form}><form noValidate onSubmit={submit} className="space-y-5">
      <Surface className="border-danger/30 bg-danger/5 p-4"><div className="flex gap-3"><Warning className="mt-0.5 shrink-0 text-danger" size={20} /><p className="text-sm leading-6">Only a fully unpaid invoice can be voided. Paid and partially paid invoices require a future refund or credit-note workflow.</p></div></Surface>
      <InvoiceField control={control} name="reason" label="Mandatory reason"><Textarea autoFocus maxLength={500} rows={5} placeholder="Explain why this invoice is incorrect" /></InvoiceField>
      <FormRootError error={formState.errors.root?.server} />
      <Button type="submit" loading={pending} loadingText="Voiding..." className="w-full bg-danger text-white hover:bg-danger/90">Void invoice and clear balance</Button>
    </form></Form>
  </DrawerForm>;
}

function InvoiceField({ control, name, label, children }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />;
}

function money(value) { return formatMetric(value, "money"); }
function sentence(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
