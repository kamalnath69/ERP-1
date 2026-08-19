import React, { lazy, Suspense } from "react";
import {
  ArrowRight, CheckCircle, ClockCounterClockwise, PushPin, Warning,
} from "@phosphor-icons/react";

import {
  ArtifactCardGrid, CollectionValue, PresentationValue, artifactFields,
  artifactValue, formatArtifactValue, hasArtifactValue,
} from "@/components/ai/ArtifactCards";
import {
  EntityAvatar, EntityProfileLink, EntityStatusBadge,
} from "@/components/entities/EntityProfile";
import { EmptyState } from "@/components/system";
import { Button } from "@/components/ui/button";
import { profilePath } from "@/lib/profileNavigation";
import { cn } from "@/lib/utils";

const AIChart = lazy(() => import("./AIChart"));
const HUMAN_FIELD = { format: "text" };
const humanText = (value) => formatArtifactValue(value, HUMAN_FIELD);

export default function ResponseBlocks({
  message, onViewAll, onPin, onConfirm, onUndo, onSelectEntity,
  onSuggestion, compact = false,
}) {
  const artifacts = message.artifacts || [];
  return (
    <div className={compact ? "mt-3 space-y-3" : "mt-4 space-y-4"}>
      {artifacts.map((block) => (
        <Block key={block.id} block={block} onViewAll={onViewAll} onPin={onPin}
          onConfirm={onConfirm} onUndo={onUndo} onSelectEntity={onSelectEntity}
          compact={compact} />
      ))}
      {!!message.suggestions?.length && onSuggestion && (
        <section className="px-1 pt-1" aria-label="Suggested follow-up questions">
          <div className="mb-2 text-xs font-semibold text-muted-foreground">You could also ask</div>
          <div className="flex flex-wrap gap-2">
            {message.suggestions.map((item, index) => (
              <button key={item.id || `${item.label}-${index}`} type="button"
                onClick={() => onSuggestion(item)}
                className="rounded-full border bg-card px-3 py-1.5 text-left text-xs font-medium text-muted-foreground transition hover:border-primary/30 hover:bg-primary/5 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {humanText(item.label)}
              </button>
            ))}
          </div>
        </section>
      )}
      {!!message.evidence?.length && <EvidencePanel evidence={message.evidence} compact={compact} />}
    </div>
  );
}

function Block({ block, onViewAll, onPin, onConfirm, onUndo, onSelectEntity, compact }) {
  const data = block.data || {};
  const normalized = data.query && !data.query_spec
    ? { ...block, data: { ...data, query_spec: data.query } } : block;
  if (block.type === "profile") return <ProfileArtifact block={block} compact={compact} />;
  if (["records", "ranking"].includes(block.type)) {
    return <RecordsArtifact block={normalized} onViewAll={onViewAll} onPin={onPin} compact={compact} />;
  }
  if (block.type === "comparison") return <ComparisonArtifact block={block} compact={compact} />;
  if (block.type === "metric") return <MetricArtifact block={block} compact={compact} />;
  if (block.type === "clarification") return <ClarificationArtifact block={block} onSelectEntity={onSelectEntity} compact={compact} />;
  if (block.type === "notice") return <NoticeArtifact block={block} compact={compact} />;
  if (block.type === "processing") return <ProcessingArtifact block={block} compact={compact} />;
  if (block.type === "sources") return <SourcesArtifact block={block} compact={compact} />;
  if (block.type === "chart") return <ChartArtifact block={block} compact={compact} />;
  if (block.type === "action") return <ActionCard data={data} title={block.title} onConfirm={onConfirm} onUndo={onUndo} compact={compact} />;
  return null;
}

function ProfileArtifact({ block, compact }) {
  const data = block.data || {};
  const fields = artifactFields(block.presentation)
    .filter((field) => hasArtifactValue(artifactValue(data, field)));
  const titleField = fields.find((field) => field.role === "title");
  const subtitleFields = fields.filter((field) => field.role === "subtitle").slice(0, compact ? 1 : 3);
  const badgeField = fields.find((field) => field.role === "badge");
  const metricFields = fields.filter((field) => field.role === "metric").slice(0, 4);
  const detailFields = fields.filter((field) => field.role === "detail");
  const collectionFields = fields.filter((field) => field.role === "collection");
  const title = formatArtifactValue(artifactValue(data, titleField), titleField)
    || humanText(block.title) || "Profile";
  const groupedDetails = detailFields.reduce((groups, field) => {
    const name = field.group || "Details";
    groups[name] = [...(groups[name] || []), field];
    return groups;
  }, {});
  const path = profilePath(data.profile_ref);

  return (
    <section className="overflow-hidden rounded-[1.35rem] border bg-card shadow-[0_14px_38px_hsl(var(--primary)/.07)]">
      <div className={cn("relative overflow-hidden border-b bg-gradient-to-br from-primary/10 via-card to-emerald-500/5", compact ? "p-4" : "p-5 md:p-6")}>
        <div className="absolute -right-12 -top-16 h-36 w-36 rounded-full border-[22px] border-primary/5" aria-hidden="true" />
        <div className="relative flex items-start gap-4">
          <EntityAvatar name={title} kind={data.profile_ref?.kind} avatarUrl={data.avatar_url}
            className={compact ? "h-12 w-12 rounded-2xl" : "h-14 w-14 rounded-2xl text-lg"} />
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-bold uppercase tracking-[.18em] text-primary/70">Verified profile</div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <h3 className={cn("font-display font-semibold", compact ? "text-xl" : "text-2xl")}>{title}</h3>
              {badgeField && <EntityStatusBadge value={artifactValue(data, badgeField)} />}
            </div>
            {!!subtitleFields.length && (
              <p className="mt-1.5 max-w-3xl text-sm leading-6 text-muted-foreground">
                {subtitleFields.map((field) => formatArtifactValue(artifactValue(data, field), field)).filter(Boolean).join(" / ")}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className={compact ? "p-4" : "p-5 md:p-6"}>
        {!!metricFields.length && (
          <div className={cn("grid gap-2.5", compact ? "grid-cols-2" : "grid-cols-2 lg:grid-cols-4")}>
            {metricFields.map((field) => (
              <div key={field.key} className="rounded-2xl border bg-secondary/45 p-3.5">
                <div className="text-[10px] font-bold uppercase tracking-[.12em] text-muted-foreground">{field.label}</div>
                <div className="mt-1.5 text-lg font-semibold"><PresentationValue value={artifactValue(data, field)} field={field} compact /></div>
              </div>
            ))}
          </div>
        )}
        {!!Object.keys(groupedDetails).length && (
          <div className={cn("grid gap-3", metricFields.length && "mt-4", compact ? "grid-cols-1" : "md:grid-cols-2")}>
            {Object.entries(groupedDetails).map(([group, groupFields]) => (
              <section key={group} className="rounded-2xl border p-4">
                <h4 className="text-xs font-bold uppercase tracking-[.12em] text-muted-foreground">{group}</h4>
                <dl className="mt-3 space-y-2.5">
                  {groupFields.map((field) => (
                    <div key={field.key} className="flex items-start justify-between gap-4 text-sm">
                      <dt className="text-muted-foreground">{field.label}</dt>
                      <dd className="max-w-[62%] text-right font-medium"><PresentationValue value={artifactValue(data, field)} field={field} compact /></dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}
          </div>
        )}
        {!!collectionFields.length && (
          <div className={cn("grid gap-3", (metricFields.length || detailFields.length) && "mt-4", compact ? "grid-cols-1" : "lg:grid-cols-2")}>
            {collectionFields.map((field) => (
              <section key={field.key} className="rounded-2xl border p-4">
                <h4 className="mb-3 text-xs font-bold uppercase tracking-[.12em] text-muted-foreground">{field.label}</h4>
                <CollectionValue value={artifactValue(data, field)} compact={compact} />
              </section>
            ))}
          </div>
        )}
        {path && (
          <EntityProfileLink profileRef={data.profile_ref} ariaLabel={`Open ${title} full profile`}
            className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Open full profile <ArrowRight aria-hidden="true" />
          </EntityProfileLink>
        )}
      </div>
    </section>
  );
}

function RecordsArtifact({ block, onViewAll, onPin, compact }) {
  const data = block.data || {};
  const items = data.items || [];
  const previewLimit = compact ? 3 : (block.presentation?.preview_limit || 4);
  const total = Number(data.total ?? items.length);
  const hidden = items.length > previewLimit || data.has_more || total > previewLimit;
  const canViewAll = Boolean(onViewAll && hidden && (data.result_session_id || data.query_spec));
  const canPin = Boolean(onPin && data.result_session_id);
  const exact = data.count_is_exact !== false;
  const title = humanText(block.title) || (block.type === "ranking" ? "Ranking" : "Results");
  return (
    <section className="rounded-[1.35rem] border bg-card/75 p-3 shadow-[0_12px_34px_hsl(var(--primary)/.055)] md:p-4">
      <header className="mb-3 flex flex-wrap items-center justify-between gap-3 px-1">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[.17em] text-primary/65">{block.type === "ranking" ? "Ranked insight" : "Verified records"}</div>
          <div className="mt-1 flex flex-wrap items-baseline gap-2">
            <h3 className={cn("font-display font-semibold", compact ? "text-lg" : "text-xl")}>{title}</h3>
            <span className="text-xs text-muted-foreground">{exact ? `${total.toLocaleString("en-IN")} found` : `${items.length.toLocaleString("en-IN")} shown`}</span>
          </div>
        </div>
        {(canPin || canViewAll) && (
          <div className="flex gap-2">
            {canPin && <Button size="sm" variant="ghost" className="rounded-xl"
              onClick={() => onPin({ sessionId: data.result_session_id, querySpec: data.query_spec, title })}><PushPin /> Pin</Button>}
            {canViewAll && <Button size="sm" className="rounded-xl"
              onClick={() => onViewAll({ sessionId: data.result_session_id, querySpec: data.query_spec, title })}>
              View all {exact && total ? total.toLocaleString("en-IN") : ""}
            </Button>}
          </div>
        )}
      </header>
      {items.length
        ? <ArtifactCardGrid items={items} presentation={block.presentation} compact={compact} limit={previewLimit} />
        : <EmptyState variant="inline" icon={Warning} title="No matching records" description="Try changing the name, date, or filter in your question." />}
    </section>
  );
}

function ComparisonArtifact({ block, compact }) {
  const data = block.data || {};
  const rows = data.groups || data.items || [];
  const metricRows = Array.isArray(data.metrics) && data.metrics.every((item) => typeof item === "object") ? data.metrics : [];
  return (
    <section className="rounded-[1.35rem] border bg-card/80 p-4 shadow-[0_12px_34px_hsl(var(--primary)/.055)] md:p-5">
      <div className="text-[10px] font-bold uppercase tracking-[.17em] text-primary/65">Side-by-side insight</div>
      <h3 className="mt-1 font-display text-xl font-semibold">{humanText(block.title) || "Comparison"}</h3>
      {!!rows.length && <div className="mt-4"><ArtifactCardGrid items={rows} presentation={block.presentation} compact={compact} /></div>}
      {!!metricRows.length && (
        <div className="mt-4 grid gap-2">
          {metricRows.map((row, index) => {
            const field = artifactFields(block.presentation).find((item) => item.key === row.field) || HUMAN_FIELD;
            return (
              <div key={`${row.field || "metric"}-${index}`} className="grid gap-3 rounded-2xl border bg-secondary/35 p-3 sm:grid-cols-[1fr_auto_auto] sm:items-center">
                <div className="font-semibold">{field.label || humanText(row.field)?.replaceAll("_", " ") || "Metric"}</div>
                <div className="text-sm"><span className="text-muted-foreground">Placed </span>{formatArtifactValue(row.placed_average, field) || "Not available"}</div>
                <div className="text-sm"><span className="text-muted-foreground">Unplaced </span>{formatArtifactValue(row.unplaced_average, field) || "Not available"}</div>
              </div>
            );
          })}
        </div>
      )}
      {!rows.length && !metricRows.length && <ScalarMetrics data={data} presentation={block.presentation} compact={compact} />}
    </section>
  );
}

function ScalarMetrics({ data, presentation, compact }) {
  const fields = artifactFields(presentation).filter((field) => hasArtifactValue(artifactValue(data, field)));
  if (!fields.length) return null;
  return (
    <div className={cn("mt-4 grid gap-2.5", compact ? "grid-cols-1" : "sm:grid-cols-2 lg:grid-cols-3")}>
      {fields.map((field) => (
        <div key={field.key} className="rounded-2xl border bg-secondary/40 p-4">
          <div className="text-[10px] font-bold uppercase tracking-[.12em] text-muted-foreground">{field.label}</div>
          <div className="mt-1.5 text-xl font-semibold"><PresentationValue value={artifactValue(data, field)} field={field} compact /></div>
        </div>
      ))}
    </div>
  );
}

function MetricArtifact({ block, compact }) {
  const data = block.data || {};
  const items = data.items || [];
  return (
    <section className="rounded-[1.35rem] border bg-gradient-to-br from-primary/8 via-card to-card p-4 shadow-[0_12px_34px_hsl(var(--primary)/.055)] md:p-5">
      <div className="text-[10px] font-bold uppercase tracking-[.17em] text-primary/65">Verified metric</div>
      <h3 className="mt-1 font-display text-xl font-semibold">{humanText(block.title) || "Analysis"}</h3>
      <ScalarMetrics data={data} presentation={block.presentation} compact={compact} />
      {!!items.length && <div className="mt-4"><ArtifactCardGrid items={items} presentation={block.presentation} compact={compact} limit={compact ? 3 : 4} /></div>}
    </section>
  );
}

function ClarificationArtifact({ block, onSelectEntity, compact }) {
  const data = block.data || {};
  const options = data.options || [];
  if (!options.length) return null;
  return (
    <section className={cn("rounded-[1.35rem] border bg-card shadow-sm", compact ? "p-3" : "p-4")}>
      <div className="text-[10px] font-bold uppercase tracking-[.17em] text-primary/65">Choose one</div>
      <h3 className="mt-1 font-display text-lg font-semibold">{humanText(block.title) || "Clarify the request"}</h3>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {options.map((option, index) => (
          <button key={`${humanText(option.label)}-${index}`} type="button" disabled={!option.entity || !onSelectEntity}
            onClick={() => onSelectEntity?.(data.clarification_id, option.entity)}
            className="rounded-xl border bg-background px-3 py-2.5 text-left text-sm transition hover:border-primary/30 hover:bg-primary/5 disabled:cursor-default disabled:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <span className="block font-semibold">{humanText(option.label)}</span>
            {option.meta && <span className="mt-0.5 block text-xs text-muted-foreground">{humanText(option.meta)}</span>}
          </button>
        ))}
      </div>
    </section>
  );
}

function NoticeArtifact({ block, compact }) {
  const unavailable = Array.isArray(block.data?.unavailable_fields) ? block.data.unavailable_fields : [];
  const detail = unavailable.length
    ? `Unavailable in your current access: ${unavailable.map((item) => humanText(item).replaceAll("_", " ")).filter(Boolean).join(", ")}.`
    : humanText(block.data?.message || block.data?.reason) || "Some requested details are not available in the current authorized view.";
  return (
    <section className={cn("rounded-2xl border border-amber-500/30 bg-amber-500/8", compact ? "p-3" : "p-4")}>
      <div className="flex gap-3"><Warning className="mt-0.5 shrink-0 text-amber-700" aria-hidden="true" />
        <div><div className="text-sm font-semibold">{humanText(block.title) || "Access notice"}</div><div className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</div></div>
      </div>
    </section>
  );
}

function ProcessingArtifact({ block, compact }) {
  return (
    <section className={cn("rounded-2xl border bg-secondary/25", compact ? "p-3" : "p-4")}>
      <div className="flex items-center gap-3"><ClockCounterClockwise className="text-primary" /><div><div className="text-sm font-semibold">{humanText(block.title) || "Analysis queued"}</div><div className="mt-0.5 text-xs text-muted-foreground">This larger authorized analysis will finish in the background.</div></div></div>
    </section>
  );
}

function SourcesArtifact({ block, compact }) {
  const items = block.data?.items || [];
  if (!items.length) return null;
  return (
    <details className="rounded-2xl border bg-card/75">
      <summary className={cn("cursor-pointer list-none font-medium", compact ? "px-3 py-2.5 text-xs" : "px-4 py-3 text-sm")}>{humanText(block.title) || "Sources"}</summary>
      <div className="grid gap-2 border-t p-3">
        {items.map((item, index) => (
          <div key={`${humanText(item.document || item.name || item.title)}-${index}`} className="rounded-xl bg-secondary/35 p-3 text-xs">
            <div className="font-semibold">{humanText(item.document || item.name || item.title) || "Authorized source"}</div>
            {item.excerpt && <div className="mt-1 line-clamp-3 text-muted-foreground">{humanText(item.excerpt)}</div>}
          </div>
        ))}
      </div>
    </details>
  );
}

function ChartArtifact({ block, compact }) {
  return (
    <section className={cn("rounded-[1.35rem] border bg-card/85 shadow-[0_8px_26px_hsl(var(--primary)/.04)]", compact ? "p-3" : "p-4 md:p-5")}>
      <div className="text-[10px] font-bold uppercase tracking-[.17em] text-primary/65">Trend and comparison</div>
      <h3 className="mt-1 font-display text-xl font-semibold">{humanText(block.title)}</h3>
      <Suspense fallback={<div className={cn("mt-3 animate-pulse rounded-xl bg-secondary", compact ? "h-44" : "h-72")} />}>
        <AIChart data={block.data || {}} className={compact ? "h-44" : undefined} />
      </Suspense>
    </section>
  );
}

function EvidencePanel({ evidence, compact }) {
  return (
    <details className="overflow-hidden rounded-2xl border bg-card/65">
      <summary className={cn("cursor-pointer list-none font-medium text-muted-foreground", compact ? "px-3 py-2.5 text-xs" : "px-4 py-3 text-sm")}>Evidence and scope ({evidence.length})</summary>
      <div className="divide-y border-t">
        {evidence.map((item, index) => (
          <div key={`${humanText(item.source)}-${index}`} className="px-4 py-3 text-xs text-muted-foreground">
            <div className="font-semibold text-foreground">{humanText(item.source) || "Authorized ERP records"}</div>
            <div className="mt-1">{humanText(item.authorized_scope)}{item.sample_size != null ? ` / sample ${Number(item.sample_size).toLocaleString("en-IN")}` : ""}{item.coverage_percent != null ? ` / ${Number(item.coverage_percent).toLocaleString("en-IN")}% coverage` : ""}</div>
            {!!Object.keys(item.definitions || {}).length && <div className="mt-1">{Object.values(item.definitions).map(humanText).filter(Boolean).join(" / ")}</div>}
          </div>
        ))}
      </div>
    </details>
  );
}

function actionFormat(key) {
  if (key.endsWith("_paise")) return { format: "currency_paise" };
  if (key.endsWith("_at")) return { format: "datetime" };
  if (key.endsWith("_on")) return { format: "date" };
  return HUMAN_FIELD;
}

function safeActionChanges(changes) {
  return Object.entries(changes || {}).filter(([key, value]) => (
    key !== "id" && !key.endsWith("_id") && !key.startsWith("_") && hasArtifactValue(value)
  ));
}

function ActionCard({ data, title, onConfirm, onUndo, compact = false }) {
  const completed = ["completed", "undone"].includes(data.status);
  const changes = safeActionChanges(data.preview?.changes).slice(0, 8);
  return (
    <section className="overflow-hidden rounded-[1.35rem] border bg-card/90 shadow-[0_8px_26px_hsl(var(--primary)/.05)]">
      <div className="border-b bg-gradient-to-r from-primary/10 via-transparent to-emerald-500/10 px-4 py-3"><div className="text-[10px] font-bold uppercase tracking-[.17em] text-primary/65">Ready for review</div><div className="mt-0.5 text-sm font-semibold">Business action</div></div>
      <div className={compact ? "p-3" : "p-4 md:p-5"}>
        <div className="flex gap-3">
          <div className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl", completed ? "bg-emerald-500/15 text-emerald-700" : "bg-primary/15 text-primary")}>{completed ? <CheckCircle /> : <ClockCounterClockwise />}</div>
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold">{humanText(title || data.preview?.title)}</h3>
            {!!changes.length && <div className={cn("mt-3 grid gap-2 text-xs", compact ? "grid-cols-1" : "sm:grid-cols-2")}>{changes.map(([key, value]) => (
              <div key={key} className="rounded-xl border bg-secondary/35 p-2.5"><span className="text-muted-foreground">{key.replaceAll("_", " ")}: </span>{formatArtifactValue(value, actionFormat(key))}</div>
            ))}</div>}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {data.status === "pending_confirmation" && <Button size="sm" className="rounded-xl" onClick={() => onConfirm?.(data)}>Review and confirm</Button>}
              {data.status === "completed" && data.undo_expires_at && new Date(data.undo_expires_at) > new Date() && <Button size="sm" variant="outline" className="rounded-xl" onClick={() => onUndo?.(data)}><ClockCounterClockwise /> Undo</Button>}
              <span className="text-xs capitalize text-muted-foreground">{humanText(data.status).replaceAll("_", " ")}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
