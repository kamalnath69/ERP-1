import React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormRootError } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Minus, Plus } from "@phosphor-icons/react";
import { toast } from "sonner";
import { useAdjustStockMutation } from "@/store/api/workspaceApi";
import { applyApiErrors, FORM_OPTIONS, stockAdjustmentSchema } from "@/lib/validation";

export default function StockAdjustmentDialog({ adjustment, onClose, onComplete }) {
  const increasing = adjustment.mode === "increase";
  const form = useForm({
    resolver: zodResolver(stockAdjustmentSchema),
    defaultValues: {
      location_id: adjustment.locationId || "",
      item_id: adjustment.item.id,
      direction: increasing ? "add" : "remove",
      quantity: "",
      reason: increasing ? "Stock received" : "Stock issued",
      batch_number: adjustment.batchNumber || "",
      expires_on: adjustment.expiresOn || "",
      reorder_level: adjustment.reorderLevelMilli != null ? String(adjustment.reorderLevelMilli / 1000) : "",
    },
    ...FORM_OPTIONS,
  });
  const { clearErrors, control, formState, handleSubmit, setError, watch } = form;
  const batchNumber = watch("batch_number");
  const [adjustStock, adjustState] = useAdjustStockMutation();
  const pending = formState.isSubmitting || adjustState.isLoading;

  const submit = handleSubmit(async (values) => {
    clearErrors("root.server");
    if (!increasing && Math.abs(values.quantity_delta_milli) > Number(adjustment.currentQuantityMilli || 0)) {
      setError("quantity", { type: "validate", message: "Quantity cannot exceed the stock currently available" }, { shouldFocus: true });
      return;
    }
    try {
      await adjustStock({
        location_id: values.location_id,
        item_id: values.item_id,
        quantity_delta_milli: values.quantity_delta_milli,
        reason: values.reason,
        batch_number: values.batch_number || "",
        expires_on: values.expires_on || null,
        reorder_level_milli: values.reorder_level_milli,
      }).unwrap();
      toast.success(increasing ? "Stock increased" : "Stock decreased");
      onClose();
      await onComplete?.();
    } catch (error) {
      const normalized = applyApiErrors(error, setError, {
        aliases: { quantity_delta_milli: "quantity", reorder_level_milli: "reorder_level" },
        fallback: "Could not update stock",
      });
      if (!Object.keys(normalized.fieldErrors).length) setError("root.server", { type: "server", message: normalized.message });
    }
  });

  return <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
    <DialogContent className="sm:max-w-lg" onInteractOutside={(event) => pending && event.preventDefault()}>
      <DialogHeader><DialogTitle className="flex items-center gap-3 font-display text-3xl">{increasing ? <Plus className="text-emerald-600" /> : <Minus className="text-destructive" />}{increasing ? "Increase" : "Decrease"} stock</DialogTitle></DialogHeader>
      <div className="flex justify-between gap-4 rounded-2xl bg-secondary/60 p-4">
        <div><div className="font-semibold">{adjustment.item.name}</div><div className="mt-1 text-xs text-muted-foreground">{adjustment.locationName || "Selected location"}{batchNumber ? ` / Batch ${batchNumber}` : ""}</div></div>
        {adjustment.currentQuantityMilli != null && <div className="text-right"><div className="font-display text-2xl">{adjustment.currentQuantityMilli / 1000}</div><div className="text-xs text-muted-foreground">currently available</div></div>}
      </div>
      <Form {...form}><form noValidate onSubmit={submit} className="mt-2 space-y-4">
        <ValidatedStockField control={control} name="quantity" label={`Quantity (${adjustment.item.unit})`}><Input autoFocus inputMode="decimal" /></ValidatedStockField>
        <ValidatedStockField control={control} name="reason" label="Reason"><Input placeholder={increasing ? "Purchase, return, opening stock..." : "Damage, internal use, correction..."} /></ValidatedStockField>
        <div className="grid grid-cols-2 gap-4">
          <ValidatedStockField control={control} name="batch_number" label="Batch"><Input disabled={!increasing && !!adjustment.batchNumber} /></ValidatedStockField>
          <ValidatedStockField control={control} name="expires_on" label="Expiry"><Input disabled={!increasing} type="date" /></ValidatedStockField>
        </div>
        <ValidatedStockField control={control} name="reorder_level" label="Low-stock threshold"><Input inputMode="decimal" /></ValidatedStockField>
        <div className={`rounded-xl p-3 text-sm ${increasing ? "bg-positive/10 text-positive" : "bg-destructive/10 text-destructive"}`}>{increasing ? "This quantity will be added to the selected batch." : "This quantity will be removed. Stock cannot go below zero."} Every change is recorded in the movement ledger.</div>
        <FormRootError error={formState.errors.root?.server} />
        <Button type="submit" variant={increasing ? "default" : "destructive"} loading={pending} loadingText="Updating stock..." className="w-full rounded-xl">{increasing ? "Increase" : "Decrease"} stock</Button>
      </form></Form>
    </DialogContent>
  </Dialog>;
}

function ValidatedStockField({ control, name, label, children }) {
  return <FormField control={control} name={name} render={({ field }) => <FormItem><FormLabel>{label}</FormLabel><FormControl>{React.cloneElement(children, { ...field, value: field.value ?? "" })}</FormControl><FormMessage /></FormItem>} />;
}
