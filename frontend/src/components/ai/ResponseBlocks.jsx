import React, { lazy, Suspense, useLayoutEffect, useRef, useState } from "react";
import {
  ArrowSquareOut,
  CheckCircle,
  ClockCounterClockwise,
  PushPin,
  Warning,
} from "@phosphor-icons/react";
import { Button } from "../ui/button";
import { EmptyState } from "../system";
import {
  EntityAvatar,
  EntityCard,
  EntityProfileLink,
  ProfileTableRow,
} from "../entities/EntityProfile";
import {
  PROFILE_INTERNAL_FIELDS,
  visibleProfileFields,
} from "@/lib/profileNavigation";

const AIChart = lazy(() => import("./AIChart"));

function valueText(value, key = "") {
  if (value == null || value === "") return "-";
  if (key.endsWith("_paise"))
    return `INR ${(Number(value) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  if (key.endsWith("_milli"))
    return (Number(value) / 1000).toLocaleString("en-IN", { maximumFractionDigits: 3 });
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object")
    return Array.isArray(value)
      ? value.map((item) => valueText(item)).join(", ")
      : Object.entries(value)
          .map(([k, v]) => `${k.replaceAll("_", " ")}: ${valueText(v)}`)
          .join(" / ");
  if (/(_at|_on)$/.test(key) && !Number.isNaN(Date.parse(value)))
    return new Date(value).toLocaleString("en-IN", {
      dateStyle: "medium",
      timeStyle: key.endsWith("_at") ? "short" : undefined,
    });
  return String(value);
}

export default function ResponseBlocks({
  message,
  onViewAll,
  onPin,
  onConfirm,
  onUndo,
  onSelectEntity,
  compact = false,
}) {
  return (
    <div className={compact ? "mt-3 space-y-3" : "mt-4 space-y-4"}>
      {(message.blocks || []).map((block) => (
        <Block
          key={block.id}
          block={block}
          onViewAll={onViewAll}
          onPin={onPin}
          onConfirm={onConfirm}
          onUndo={onUndo}
          onSelectEntity={onSelectEntity}
          compact={compact}
        />
      ))}
      {!!message.citations?.length && (
        <section className="overflow-hidden rounded-2xl border bg-card/85 shadow-[0_8px_26px_hsl(var(--primary)/.04)]">
          <div className={`flex items-center justify-between border-b bg-secondary/35 ${compact ? "px-3 py-2.5" : "px-4 py-3"}`}><div><div className="overline">Reference material</div><div className="mt-0.5 text-sm font-semibold">Sources used</div></div><span className="rounded-full bg-background px-2.5 py-1 text-[10px] font-semibold text-muted-foreground">{message.citations.length}</span></div>
          <div className={compact ? "mt-2 space-y-1.5" : "mt-3 space-y-2"}>
            {message.citations.map((item, index) => (
              <a
                key={`${item.document_id}-${index}`}
                href={item.href}
                target="_blank"
                rel="noreferrer"
                className={`group mx-3 block rounded-xl border bg-background/60 transition hover:border-accent/50 hover:shadow-sm ${compact ? "mb-2 p-2.5" : "mb-3 p-3"}`}
              >
                <div className="flex items-center justify-between gap-3 text-sm font-medium">
                  <span className="flex min-w-0 items-center gap-2"><span className="text-[10px] text-muted-foreground">{String(index + 1).padStart(2, "0")}</span><span className="truncate">{item.document}</span></span>
                  <ArrowSquareOut className="shrink-0 text-muted-foreground group-hover:text-accent" />
                </div>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                  {item.excerpt}
                </p>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Block({ block, onViewAll, onPin, onConfirm, onUndo, onSelectEntity, compact }) {
  const data = block.data || {};
  if (block.type === "text") return null;
  if (block.type === "kpi_grid")
    return (
      <section className="overflow-hidden rounded-2xl border bg-card/85 shadow-[0_8px_26px_hsl(var(--primary)/.04)]">
        <div className={`border-b bg-secondary/30 ${compact ? "px-3 py-2.5" : "px-4 py-3"}`}><div className="overline">Live business view</div><h3 className="mt-0.5 font-display text-lg font-semibold">{block.title || "Business snapshot"}</h3></div>
        <div className={`grid gap-px bg-border ${compact ? "grid-cols-2" : "grid-cols-1 sm:grid-cols-2 xl:grid-cols-3"}`}>
        {(data.items || []).map((item, index) => (
          <div key={item.label} className={`relative bg-card ${compact ? "p-3" : "p-4 md:p-5"}`}>
            <span className={`absolute left-0 top-4 h-8 w-0.5 rounded-full ${index === 0 ? "bg-accent" : "bg-border"}`} />
            <div className="text-[11px] font-medium text-muted-foreground">{item.label}</div>
            <div className={`mt-2 font-display font-bold ${compact ? "text-xl" : "text-2xl md:text-3xl"}`}>
              {item.format === "money"
                ? valueText(item.value, "amount_paise")
                : Number(item.value || 0).toLocaleString("en-IN")}
            </div>
          </div>
        ))}
        </div>
      </section>
    );
  if (block.type === "chart")
    return (
      <section className={`rounded-2xl border bg-card/85 shadow-[0_8px_26px_hsl(var(--primary)/.04)] ${compact ? "p-3" : "p-4 md:p-5"}`}>
        <div className="overline">Trend and comparison</div><h3 className="mt-1 font-display text-xl font-semibold">{block.title}</h3>
        <Suspense
          fallback={
            <div className={`${compact ? "h-44" : "h-72"} mt-3 animate-pulse rounded-xl bg-secondary`} />
          }
        >
          <AIChart data={data} className={compact ? "h-44" : undefined} />
        </Suspense>
      </section>
    );
  if (block.type === "entity_cards")
    return (
      <EntityCards
        block={block}
        onViewAll={onViewAll}
        onPin={onPin}
        onSelectEntity={onSelectEntity}
        compact={compact}
      />
    );
  if (block.type === "table")
    return <Records block={block} onViewAll={onViewAll} onPin={onPin} compact={compact} />;
  if (block.type === "action")
    return (
      <ActionCard
        data={data}
        title={block.title}
        onConfirm={onConfirm}
        onUndo={onUndo}
        compact={compact}
      />
    );
  if (block.type === "alert")
    return (
      <div className="rounded-2xl border border-amber-500/35 bg-amber-500/10 p-4 text-amber-950 dark:text-amber-100 flex gap-3 shadow-sm">
        <span className="h-9 w-9 shrink-0 rounded-xl bg-amber-500/15 grid place-items-center"><Warning /></span>
        <div><div className="text-sm font-semibold">Needs your attention</div><div className="mt-1 text-sm opacity-80">{valueText(data.message)}</div></div>
      </div>
    );
  return null;
}

function EntityCards({ block, onViewAll, onPin, onSelectEntity, compact = false }) {
  const data = block.data || {};
  const rawItems = data.items || [];
  const items = canonicalEntityCards(rawItems);
  const { gridRef, visibleCount, rowHeight } = useFirstRowPreview(items.length);
  const canonicalCount = items.length < rawItems.length ? items.length : undefined;
  const total = Number(canonicalCount ?? data.total ?? rawItems.length);
  const canOpenOverflow = Boolean(
    onViewAll && (data.result_session_id || data.query_spec),
  );
  const previewCount = canOpenOverflow ? visibleCount : items.length;
  const hasHiddenOverflow = canOpenOverflow && (
    previewCount < items.length || total > rawItems.length
  );
  return (
    <section className="space-y-3">
      <RecordsHeader
        block={block}
        onViewAll={onViewAll}
        onPin={onPin}
        visibleCount={canonicalCount}
        hasHiddenOverflow={hasHiddenOverflow}
        compact={compact}
      />
      {items.length ? (
        <div
          ref={gridRef}
          className="grid gap-3 overflow-hidden"
          style={{
            gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 17rem), 1fr))",
            maxHeight: previewCount < items.length && rowHeight ? `${rowHeight}px` : undefined,
          }}
        >
          {items.map((item, index) => {
            const details = visibleProfileFields(item, compact ? 4 : 6)
              .filter(
                ([key]) =>
                  !["name", "status", "active", "phone", "type"].includes(key),
              )
              .slice(0, compact ? 2 : 3)
              .map(([key, value]) => [key, valueText(value, key)]);
            return (
              <div
                key={item.id || index}
                className={`space-y-2 ${index >= previewCount ? "invisible pointer-events-none select-none" : ""}`}
                aria-hidden={index >= previewCount || undefined}
              >
                <EntityCard item={item} details={details} />
                {item.selection_ref && onSelectEntity && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="w-full rounded-xl"
                    onClick={() => onSelectEntity(item)}
                  >
                    Use this record
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      ) : <EmptyState
        variant="inline"
        icon={Warning}
        title="No matching records"
        description="Try a different name or broaden your question."
      />}
    </section>
  );
}

function RecordsHeader({ block, onViewAll, onPin, visibleCount, hasHiddenOverflow = false, embedded = false, compact = false }) {
  const data = block.data || {};
  const count = visibleCount ?? data.total ?? data.items?.length ?? 0;
  const canPin = Boolean(data.result_session_id && onPin);
  const canViewAll = Boolean(
    onViewAll && (
      data.result_session_id || (hasHiddenOverflow && data.query_spec)
    ),
  );
  return (
    <header className={`${embedded ? "border-b bg-secondary/30" : "rounded-2xl border bg-card/85 shadow-[0_8px_26px_hsl(var(--primary)/.04)]"} ${compact ? "p-3" : "p-4"} flex flex-wrap justify-between gap-3 items-center`}>
      <div>
        <div className="overline">Current records</div>
        <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2"><h3 className={`font-display font-semibold ${compact ? "text-lg" : "text-xl"}`}>{block.title}</h3><p className="text-xs text-muted-foreground">{Number(count).toLocaleString("en-IN")} found</p></div>
      </div>
      {(canPin || canViewAll) && (
        <div className="flex gap-2">
          {canPin && (
            <Button
              size="sm"
              variant="ghost"
              className="rounded-xl"
              onClick={() => onPin({ sessionId: data.result_session_id, querySpec: data.query_spec, title: block.title })}
            >
              <PushPin /> Pin
            </Button>
          )}
          {canViewAll && (
            <Button
              size="sm"
              className="rounded-xl"
              onClick={() => onViewAll({ sessionId: data.result_session_id, querySpec: data.query_spec, title: block.title })}
            >
              View all
            </Button>
          )}
        </div>
      )}
    </header>
  );
}

export function measureFirstRow(children) {
  const nodes = Array.from(children || []);
  if (!nodes.length) return { visibleCount: 0, rowHeight: 0 };
  const firstTop = nodes[0].offsetTop;
  const firstRow = nodes.filter((node) => Math.abs(node.offsetTop - firstTop) <= 1);
  const rowBottom = Math.max(
    ...firstRow.map((node) => node.offsetTop + node.offsetHeight),
  );
  return {
    visibleCount: Math.max(firstRow.length, 1),
    rowHeight: Math.max(rowBottom - firstTop, 0),
  };
}

function useFirstRowPreview(itemCount) {
  const gridRef = useRef(null);
  const [layout, setLayout] = useState({ visibleCount: itemCount, rowHeight: 0 });

  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid || !itemCount) {
      setLayout({ visibleCount: itemCount, rowHeight: 0 });
      return undefined;
    }
    const measure = () => {
      const next = measureFirstRow(grid.children);
      setLayout((current) => (
        current.visibleCount === next.visibleCount && current.rowHeight === next.rowHeight
          ? current
          : next
      ));
    };
    measure();

    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(measure);
      observer.observe(grid);
      Array.from(grid.children).forEach((child) => observer.observe(child));
      return () => observer.disconnect();
    }
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [itemCount]);

  return { gridRef, ...layout };
}

function canonicalEntityCards(items) {
  const grouped = new Map();
  items.forEach((item, index) => {
    const profile = item.profile_ref;
    const canonicalCatalog = profile?.kind === "catalog" && ["catalog", "inventory"].includes(item.kind);
    const key = canonicalCatalog
      ? `${profile.kind}:${profile.id}`
      : `${item.kind || "record"}:${item.id || index}`;
    grouped.set(key, [...(grouped.get(key) || []), item]);
  });
  return [...grouped.values()].map((candidates) => {
    const preferred = candidates.find((candidate) => candidate.kind === "catalog") || candidates[0];
    const inventory = candidates.filter((candidate) => candidate.kind === "inventory");
    const embeddedStock = preferred.snapshot?.stock;
    if (!inventory.length && !embeddedStock) return { ...preferred };
    return {
      ...preferred,
      stock_levels: embeddedStock?.level_count ?? inventory.length,
      stock_quantity_milli: embeddedStock?.total_quantity_milli
        ?? inventory.reduce((sum, candidate) => sum + Number(candidate.snapshot?.quantity_milli || candidate.quantity_milli || 0), 0),
      low_stock_levels: embeddedStock?.low_level_count
        ?? inventory.filter((candidate) => candidate.status === "low").length,
    };
  });
}

function Records({ block, onViewAll, onPin, compact = false }) {
  const data = block.data || {};
  const items = data.items || [];
  const columns = (
    data.columns?.length
      ? data.columns
      : [...new Set(items.flatMap((item) => Object.keys(item)))]
  )
    .filter((key) => !PROFILE_INTERNAL_FIELDS.has(key) && !key.endsWith("_id"))
    .slice(0, 6);
  if (compact) {
    const preview = items.slice(0, 3);
    return (
      <section className="overflow-hidden rounded-2xl border bg-card/85 shadow-[0_8px_26px_hsl(var(--primary)/.04)]">
        <RecordsHeader
          block={block}
          onViewAll={onViewAll}
          onPin={onPin}
          embedded
          compact
          hasHiddenOverflow={items.length > preview.length || Number(data.total || 0) > items.length}
        />
        {preview.length ? <div className="divide-y">
          {preview.map((item, index) => {
            const titleKey = columns[0];
            const title = item.display_name || item.name || valueText(item[titleKey], titleKey);
            const details = columns.slice(1, 3).map((key) => `${key.replaceAll("_", " ")}: ${valueText(item[key], key)}`);
            const content = <>
              <span className="block truncate text-sm font-semibold">{title}</span>
              {!!details.length && <span className="mt-1 block line-clamp-2 text-xs text-muted-foreground">{details.join(" / ")}</span>}
            </>;
            return item.profile_ref ? (
              <EntityProfileLink key={item.id || index} profileRef={item.profile_ref} className="block px-3 py-3 transition-colors hover:bg-secondary/50">
                {content}
              </EntityProfileLink>
            ) : <div key={item.id || index} className="px-3 py-3">{content}</div>;
          })}
        </div> : <EmptyState variant="inline" icon={Warning} title="No matching records" description="Try changing the name, date, or filter in your question." />}
      </section>
    );
  }
  return (
    <section className="rounded-2xl border bg-card/85 overflow-hidden shadow-[0_8px_26px_hsl(var(--primary)/.04)]">
      <RecordsHeader block={block} onViewAll={onViewAll} onPin={onPin} embedded />
      {items.length ? (
        <div className="premium-scrollbar overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-secondary/45">
              <tr>
                {columns.map((key) => (
                  <th
                    key={key}
                    className="text-left text-[10px] font-semibold uppercase tracking-[.12em] text-muted-foreground px-4 py-3 whitespace-nowrap"
                  >
                    {key.replaceAll("_", " ")}
                  </th>
                ))}
                {items.some((item) => item.profile_ref) && (
                  <th className="px-4 py-3" />
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <ProfileTableRow
                  key={item.id || index}
                  profileRef={item.profile_ref}
                  ariaLabel={`Open ${item.display_name || item.name || "record"} profile`}
                  className="border-t transition-colors"
                >
                  {columns.map((key, columnIndex) => (
                    <td key={key} className="px-4 py-3 max-w-64 truncate">
                      {columnIndex === 0 && item.profile_ref ? (
                        <div className="flex items-center gap-2.5">
                          <EntityAvatar
                            name={item.display_name || item.name}
                            kind={item.profile_ref.kind}
                            avatarUrl={item.avatar_url}
                            className="h-9 w-9 rounded-xl text-sm"
                          />
                          <EntityProfileLink
                            profileRef={item.profile_ref}
                            className="font-medium hover:text-accent"
                          >
                            {valueText(item[key], key)}
                          </EntityProfileLink>
                        </div>
                      ) : (
                        valueText(item[key], key)
                      )}
                    </td>
                  ))}
                  {items.some((row) => row.profile_ref) && (
                    <td className="px-4 py-3 text-right">
                      {item.profile_ref && (
                        <EntityProfileLink
                          profileRef={item.profile_ref}
                          className="text-xs font-semibold text-accent"
                        >
                          Open profile
                        </EntityProfileLink>
                      )}
                    </td>
                  )}
                </ProfileTableRow>
              ))}
            </tbody>
          </table>
        </div>
      ) : <EmptyState
        variant="inline"
        icon={Warning}
        title="No matching records"
        description="Try changing the name, date, or filter in your question."
      />}
    </section>
  );
}

function ActionCard({ data, title, onConfirm, onUndo, compact = false }) {
  const completed = ["completed", "undone"].includes(data.status);
  return (
    <section className="overflow-hidden rounded-2xl border bg-card/90 shadow-[0_8px_26px_hsl(var(--primary)/.05)]">
      <div className="border-b bg-gradient-to-r from-accent/10 via-transparent to-emerald-500/10 px-4 py-3"><div className="overline">Ready for your review</div><div className="mt-0.5 text-sm font-semibold">Business action</div></div>
      <div className={compact ? "p-3" : "p-4 md:p-5"}>
      <div className="flex gap-3">
        <div className={`w-10 h-10 shrink-0 rounded-xl grid place-items-center ${completed ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" : "bg-accent/15 text-accent"}`}>
          {completed ? <CheckCircle /> : <ClockCounterClockwise />}
        </div>
        <div className="flex-1">
          <h3 className="font-semibold">{title || data.preview?.title}</h3>
          <div className={`mt-2 grid gap-2 text-xs ${compact ? "grid-cols-1" : "sm:grid-cols-2"}`}>
            {Object.entries(data.preview?.changes || {})
              .slice(0, 8)
              .map(([key, value]) => (
                <div key={key} className="rounded-xl border bg-secondary/35 p-2.5">
                  <span className="text-muted-foreground capitalize">
                    {key.replaceAll("_", " ")}:{" "}
                  </span>
                  {valueText(value, key)}
                </div>
              ))}
          </div>
          <div className="flex gap-2 mt-3">
            {data.status === "pending_confirmation" && (
              <Button size="sm" className="rounded-xl" onClick={() => onConfirm(data)}>
                Review and confirm
              </Button>
            )}
            {data.status === "completed" &&
              data.undo_expires_at &&
              new Date(data.undo_expires_at) > new Date() && (
                <Button
                  size="sm"
                  variant="outline"
                  className="rounded-xl"
                  onClick={() => onUndo(data)}
                >
                  <ClockCounterClockwise /> Undo
                </Button>
              )}
            <span className="text-xs text-muted-foreground self-center capitalize">
              {data.status?.replaceAll("_", " ")}
            </span>
          </div>
        </div>
      </div>
      </div>
    </section>
  );
}
