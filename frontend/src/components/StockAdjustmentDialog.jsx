import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Minus, Plus } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useAdjustStockMutation } from "@/store/api/workspaceApi";

export default function StockAdjustmentDialog({ adjustment, onClose, onComplete }) {
  const increasing = adjustment.mode === "increase";
  const [form, setForm] = useState({
    quantity: "",
    reason: increasing ? "Stock received" : "Stock issued",
    batch_number: adjustment.batchNumber || "",
    expires_on: adjustment.expiresOn || "",
    reorder: adjustment.reorderLevelMilli != null ? adjustment.reorderLevelMilli / 1000 : "",
  });
  const [saving, setSaving] = useState(false);
  const [adjustStock] = useAdjustStockMutation();

  const submit = async (event) => {
    event.preventDefault();
    const quantityMilli = Math.round(Number(form.quantity) * 1000);
    if (!quantityMilli || quantityMilli < 0) {
      toast.error("Enter a quantity greater than zero");
      return;
    }
    if (!adjustment.locationId) {
      toast.error("Select an operating location first");
      return;
    }
    setSaving(true);
    try {
      await adjustStock({
        location_id: adjustment.locationId,
        item_id: adjustment.item.id,
        quantity_delta_milli: increasing ? quantityMilli : -quantityMilli,
        reason: form.reason.trim(),
        batch_number: form.batch_number.trim(),
        expires_on: form.expires_on || null,
        reorder_level_milli: form.reorder === "" ? null : Math.round(Number(form.reorder) * 1000),
      }).unwrap();
      toast.success(increasing ? "Stock increased" : "Stock decreased");
      onClose();
      await onComplete();
    } catch (error) {
      toast.error(error?.data?.detail || error.response?.data?.detail || "Could not update stock");
    } finally {
      setSaving(false);
    }
  };

  return <Dialog open onOpenChange={(open) => !open && onClose()}>
    <DialogContent className="sm:max-w-lg">
      <DialogHeader><DialogTitle className="font-display text-3xl flex items-center gap-3">{increasing ? <Plus className="text-emerald-600" /> : <Minus className="text-destructive" />}{increasing ? "Increase" : "Decrease"} stock</DialogTitle></DialogHeader>
      <div className="rounded-2xl bg-secondary/60 p-4 flex justify-between gap-4">
        <div><div className="font-semibold">{adjustment.item.name}</div><div className="text-xs text-muted-foreground mt-1">{adjustment.locationName || "Selected location"}{form.batch_number ? ` / Batch ${form.batch_number}` : ""}</div></div>
        {adjustment.currentQuantityMilli != null && <div className="text-right"><div className="font-display text-2xl">{adjustment.currentQuantityMilli / 1000}</div><div className="text-xs text-muted-foreground">currently available</div></div>}
      </div>
      <form onSubmit={submit} className="space-y-4 mt-2">
        <Field label={`Quantity (${adjustment.item.unit})`}><Input autoFocus required type="number" min="0.001" step="0.001" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} /></Field>
        <Field label="Reason"><Input required minLength={3} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} placeholder={increasing ? "Purchase, return, opening stock..." : "Damage, internal use, correction..."} /></Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Batch"><Input disabled={!increasing && !!adjustment.batchNumber} value={form.batch_number} onChange={(event) => setForm({ ...form, batch_number: event.target.value })} /></Field>
          <Field label="Expiry"><Input disabled={!increasing} type="date" value={form.expires_on} onChange={(event) => setForm({ ...form, expires_on: event.target.value })} /></Field>
        </div>
        <Field label="Low-stock threshold"><Input type="number" min="0" step="0.001" value={form.reorder} onChange={(event) => setForm({ ...form, reorder: event.target.value })} /></Field>
        <div className={`rounded-xl p-3 text-sm ${increasing ? "bg-positive/10 text-positive" : "bg-destructive/10 text-destructive"}`}>{increasing ? "This quantity will be added to the selected batch." : "This quantity will be removed. Stock cannot go below zero."} Every change is recorded in the movement ledger.</div>
        <Button type="submit" variant={increasing ? "default" : "destructive"} disabled={saving} className="w-full rounded-xl">{saving ? "Updating stock..." : `${increasing ? "Increase" : "Decrease"} stock`}</Button>
      </form>
    </DialogContent>
  </Dialog>;
}

function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
