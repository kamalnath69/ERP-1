import {
  Buildings, CheckCircle, GraduationCap, SquaresFour, UsersThree,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function progress(placed, total) {
  return total ? Math.round((Number(placed || 0) / Number(total)) * 100) : 0;
}

function ScopeMetric({ icon: Icon, value, label }) {
  return <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><Icon size={14} />{value} {label}</span>;
}

function BatchCard({ item, selected, onClick }) {
  const placement = progress(item.placed_count, item.student_count);
  return <button
    type="button"
    onClick={onClick}
    aria-pressed={selected}
    className={cn(
      "group rounded-2xl border p-4 text-left transition-[border-color,background-color,box-shadow,transform] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      selected ? "border-primary bg-primary text-primary-foreground shadow-sm" : "bg-card hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-sm",
    )}
  >
    <div className="flex items-start justify-between gap-3">
      <span className={cn("grid h-9 w-9 place-items-center rounded-xl", selected ? "bg-white/10" : "bg-primary/10 text-primary")}><GraduationCap size={20} weight="duotone" /></span>
      <span className={cn("text-xs font-semibold", selected ? "text-primary-foreground/70" : "text-muted-foreground")}>{item.student_count} students</span>
    </div>
    <div className="mt-4 font-display text-xl font-semibold">{item.label}</div>
    <div className={cn("mt-1 text-xs", selected ? "text-primary-foreground/70" : "text-muted-foreground")}>{item.department_count} departments / {item.section_count} sections</div>
    <div className={cn("mt-4 h-1.5 overflow-hidden rounded-full", selected ? "bg-white/20" : "bg-secondary")}><span className={cn("block h-full rounded-full", selected ? "bg-accent" : "bg-primary")} style={{ width: `${placement}%` }} /></div>
    <div className={cn("mt-2 text-[11px]", selected ? "text-primary-foreground/70" : "text-muted-foreground")}>{placement}% placed</div>
  </button>;
}

function DepartmentCard({ item, year, selected, onClick }) {
  return <button
    type="button"
    onClick={onClick}
    aria-pressed={selected}
    className={cn(
      "rounded-2xl border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      selected ? "border-primary bg-primary/5 ring-1 ring-primary/10" : "bg-card hover:border-primary/30 hover:bg-surface-subtle",
    )}
  >
    <div className="flex items-start justify-between gap-3"><span className="rounded-lg bg-secondary px-2 py-1 text-[11px] font-bold tracking-wide text-primary">{item.code}</span>{selected && <CheckCircle className="text-positive" weight="fill" />}</div>
    <div className="mt-3 line-clamp-2 font-semibold">{item.name}</div>
    <div className="mt-1 text-xs text-muted-foreground">Class of {year}</div>
    <div className="mt-4 flex flex-wrap gap-x-3 gap-y-1"><ScopeMetric icon={UsersThree} value={item.student_count} label="students" /><ScopeMetric icon={SquaresFour} value={item.section_count} label="sections" /></div>
  </button>;
}

function SectionCard({ item, program, department, selected, onClick }) {
  return <button
    type="button"
    onClick={onClick}
    aria-pressed={selected}
    className={cn(
      "rounded-2xl border px-4 py-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      selected ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:border-primary/30 hover:bg-surface-subtle",
    )}
  >
    <div className="flex items-center justify-between gap-3"><span className="font-semibold">{item.name}</span><span className={cn("text-xs font-semibold", selected ? "text-primary-foreground/65" : "text-muted-foreground")}>{item.student_count}</span></div>
    <div className={cn("mt-1 truncate text-xs", selected ? "text-primary-foreground/70" : "text-muted-foreground")}>{program.code} / {department.code} / Semester {item.current_semester}</div>
    <div className={cn("mt-3 flex gap-3 text-[11px]", selected ? "text-primary-foreground/70" : "text-muted-foreground")}><span>{item.placed_count} placed</span><span>{item.unplaced_count} unplaced</span></div>
  </button>;
}

export default function AcademicScopeNavigator({
  data,
  loading,
  error,
  retry,
  value,
  onChange,
  title = "Find students by class, department, and section",
  clearLabel = "View all students",
}) {
  const batches = data?.items || [];
  const selectedBatch = batches.find((item) => String(item.graduation_year) === String(value.graduationYear));
  const selectedDepartment = selectedBatch?.departments?.find((item) => item.id === value.departmentId);
  const sectionRows = (selectedDepartment?.programs || []).flatMap((program) =>
    (program.sections || []).map((section) => ({ section, program })),
  );

  if (loading) return <section className="surface-card p-5" aria-label="Loading academic structure"><div className="h-5 w-48 animate-pulse rounded bg-secondary" /><div className="mt-4 grid gap-3 sm:grid-cols-3">{[1, 2, 3].map((item) => <div key={item} className="h-40 animate-pulse rounded-2xl bg-secondary/70" />)}</div></section>;
  if (error && !data) return <section className="surface-card flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div><div className="font-semibold">Academic structure could not be loaded</div><p className="mt-1 text-xs text-muted-foreground">The student directory is still available below.</p></div>{retry && <Button variant="outline" size="sm" onClick={retry}>Try again</Button>}</section>;
  if (!batches.length) return null;

  const chooseBatch = (item) => onChange({ graduationYear: item.graduation_year, departmentId: null, cohortId: null });
  const chooseDepartment = (item) => onChange({ graduationYear: selectedBatch.graduation_year, departmentId: item.id, cohortId: null });
  const chooseSection = (item) => onChange({ graduationYear: selectedBatch.graduation_year, departmentId: selectedDepartment.id, cohortId: item.id });

  return <section className="surface-card overflow-hidden" aria-label="Academic batch and section navigation">
    <header className="flex flex-col gap-3 border-b bg-surface-subtle/50 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div><div className="overline">Academic structure</div><h2 className="mt-1 font-display text-xl font-semibold">{title}</h2></div>
      {(value.graduationYear || value.departmentId || value.cohortId) && <Button variant="ghost" size="sm" onClick={() => onChange({ graduationYear: null, departmentId: null, cohortId: null })}>{clearLabel}</Button>}
    </header>
    <div className="space-y-5 p-4 sm:p-5">
      <div>
        <div className="mb-2.5 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><GraduationCap />Graduation batch</div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{batches.map((item) => <BatchCard key={item.graduation_year} item={item} selected={selectedBatch?.graduation_year === item.graduation_year} onClick={() => chooseBatch(item)} />)}</div>
      </div>
      {selectedBatch && <div className="border-t pt-5">
        <div className="mb-2.5 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><Buildings />Departments in {selectedBatch.label}</div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{selectedBatch.departments.map((item) => <DepartmentCard key={item.id} item={item} year={selectedBatch.graduation_year} selected={selectedDepartment?.id === item.id} onClick={() => chooseDepartment(item)} />)}</div>
      </div>}
      {selectedDepartment && <div className="border-t pt-5">
        <div className="mb-2.5 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><SquaresFour />Sections in {selectedDepartment.code}</div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{sectionRows.map(({ section, program }) => <SectionCard key={section.id} item={section} program={program} department={selectedDepartment} selected={value.cohortId === section.id} onClick={() => chooseSection(section)} />)}</div>
      </div>}
    </div>
  </section>;
}
