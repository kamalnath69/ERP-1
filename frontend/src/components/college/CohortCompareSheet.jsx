import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import { MagnifyingGlass, Plus, Scales, X } from "@phosphor-icons/react";

import { DrawerForm, EmptyState, Surface } from "@/components/system";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";

function flattenCohorts(data) {
  return (data?.items || []).flatMap((batch) => batch.departments.flatMap((department) =>
    department.programs.flatMap((program) => program.sections.map((section) => ({
      ...section,
      graduation_year: batch.graduation_year,
      department_name: department.name,
      department_code: department.code,
      program_name: program.name,
      program_code: program.code,
      search: `${batch.label} ${department.name} ${department.code} ${program.name} ${program.code} ${section.name} ${section.code}`.toLowerCase(),
    }))),
  ));
}

export default function CohortCompareSheet({ data, selectedIds = [], onApply }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState(selectedIds);
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const rows = useMemo(() => flattenCohorts(data), [data]);
  const selected = rows.filter((row) => selectedIds.includes(row.id));
  const visible = deferredSearch ? rows.filter((row) => row.search.includes(deferredSearch)) : rows;

  useEffect(() => {
    if (!open) return;
    setDraft(selectedIds);
    setSearch("");
  }, [open, selectedIds]);

  if (!rows.length) return null;
  const toggle = (id) => setDraft((current) => current.includes(id)
    ? current.filter((value) => value !== id)
    : current.length < 50 ? [...current, id] : current);

  return <>
    <Surface className="overflow-hidden">
      <div className="flex flex-col gap-3 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div className="flex min-w-0 items-center gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><Scales /></span><div className="min-w-0"><div className="font-semibold">Compare cohorts</div><p className="mt-0.5 text-xs text-muted-foreground">Combine sections or graduation years without changing the college hierarchy.</p></div></div>
        <Button variant="outline" onClick={() => setOpen(true)}>{selected.length ? "Change comparison" : <><Plus className="mr-2" />Select cohorts</>}</Button>
      </div>
      {selected.length > 0 && <div className="flex flex-wrap gap-2 border-t bg-surface-subtle/45 px-4 py-3 sm:px-5">{selected.map((row) => <button key={row.id} type="button" onClick={() => onApply(selectedIds.filter((id) => id !== row.id))} className="inline-flex max-w-full items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs font-semibold transition-colors hover:border-primary/30"><span className="truncate">{row.department_code} / {row.program_code} / {row.section || "GENERAL"} / {row.graduation_year}</span><X size={13} className="shrink-0 text-muted-foreground" /></button>)}<Button size="sm" variant="ghost" onClick={() => onApply([])}>Clear comparison</Button></div>}
    </Surface>

    <DrawerForm open={open} onOpenChange={setOpen} title="Compare student cohorts" description="Choose up to 50 institution-defined batches or sections. Your selection is preserved in the page URL.">
      <div className="space-y-4">
        <div className="relative"><MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input className="pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search class, department, program, or section" /></div>
        <div className="flex items-center justify-between text-xs text-muted-foreground"><span>{draft.length} selected</span><span>Maximum 50</span></div>
        <div className="max-h-[56dvh] divide-y overflow-y-auto rounded-xl border">{visible.length ? visible.map((row) => <label key={row.id} className="flex cursor-pointer items-start gap-3 p-3.5 transition-colors hover:bg-surface-hover"><Checkbox className="mt-0.5" checked={draft.includes(row.id)} onCheckedChange={() => toggle(row.id)} /><span className="min-w-0 flex-1"><span className="block font-semibold">{row.department_code} / {row.program_code} / {row.section || "GENERAL"}</span><span className="mt-1 block text-xs text-muted-foreground">Class of {row.graduation_year} / {row.student_count} students</span></span></label>) : <EmptyState variant="inline" title="No cohorts match this search" description="Try a department, program, section, or graduation year." />}</div>
        <div className="sticky bottom-0 flex flex-col-reverse gap-2 bg-card pt-2 sm:flex-row sm:justify-end"><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!draft.length} onClick={() => { onApply(draft); setOpen(false); }}>Apply comparison</Button></div>
      </div>
    </DrawerForm>
  </>;
}
