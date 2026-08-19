import React from "react";
import { ArrowRight } from "@phosphor-icons/react";

import {
  EntityAvatar,
  EntityProfileLink,
  EntityStatusBadge,
} from "@/components/entities/EntityProfile";
import { profilePath } from "@/lib/profileNavigation";
import { cn } from "@/lib/utils";

const UUID_PATTERN = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const INTERNAL_KEYS = new Set([
  "id", "profile_ref", "selection_ref", "query", "query_spec",
  "result_session_id", "clarification_id", "confirmation_token", "job_id",
  "undo_token", "security", "entity_refs", "entity_ids",
]);

function isInternalKey(key) {
  return INTERNAL_KEYS.has(key) || key.endsWith("_id") || key.startsWith("_");
}

function safeString(value) {
  if (value == null) return "";
  return String(value).replace(UUID_PATTERN, "").replace(/\s{2,}/g, " ").trim();
}

export function artifactFields(presentation) {
  return (presentation?.fields || [])
    .filter((field) => field?.key && !isInternalKey(field.key))
    .sort((left, right) => (left.priority || 100) - (right.priority || 100));
}

export function artifactValue(item, field) {
  if (!item || !field) return null;
  if (Object.hasOwn(item, field.key)) return item[field.key];
  if (item.values && Object.hasOwn(item.values, field.key)) return item.values[field.key];
  return null;
}

export function hasArtifactValue(value) {
  if (value == null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function relationText(value) {
  if (typeof value !== "object" || Array.isArray(value)) return safeString(value);
  const name = safeString(value.name || value.label || value.title);
  const code = safeString(value.code);
  if (name && code && name.toLocaleLowerCase() !== code.toLocaleLowerCase()) return `${name} (${code})`;
  return name || code;
}

function dateText(value, includeTime) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return safeString(value);
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    ...(includeTime ? { timeStyle: "short" } : {}),
  }).format(parsed);
}

export function formatArtifactValue(value, field = {}) {
  if (!hasArtifactValue(value)) return "";
  const format = field.format || "text";
  const numeric = Number(value);
  if (format === "currency_paise") {
    if (!Number.isFinite(numeric)) return safeString(value);
    return new Intl.NumberFormat("en-IN", {
      style: "currency", currency: "INR", maximumFractionDigits: 2,
    }).format(numeric / 100);
  }
  if (format === "percent") return Number.isFinite(numeric) ? `${numeric.toLocaleString("en-IN", { maximumFractionDigits: 2 })}%` : safeString(value);
  if (["decimal", "number"].includes(format)) return Number.isFinite(numeric) ? numeric.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : safeString(value);
  if (format === "boolean") return value ? "Yes" : "No";
  if (format === "date") return dateText(value, false);
  if (format === "datetime") return dateText(value, true);
  if (format === "status") return safeString(value).replaceAll("_", " ");
  if (format === "relation") return relationText(value);
  if (typeof value === "object") return "";
  return safeString(value);
}

function collectionItem(item) {
  if (typeof item !== "object" || item == null) return { title: safeString(item), meta: "" };
  const title = safeString(item.title || item.name || item.label || item.role || item.status);
  const details = [
    item.issuer,
    item.proficiency,
    item.status && item.status !== title ? item.status : null,
    item.completed_on ? dateText(item.completed_on, false) : null,
  ].map(safeString).filter(Boolean);
  return { title, meta: details.join(" / ") };
}

export function CollectionValue({ value, compact = false }) {
  const items = Array.isArray(value) ? value : [value];
  const normalized = items.map(collectionItem).filter((item) => item.title);
  if (!normalized.length) return null;
  const simple = normalized.every((item) => !item.meta);
  if (simple) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {normalized.slice(0, compact ? 6 : 12).map((item, index) => (
          <span key={`${item.title}-${index}`} className="rounded-full border border-primary/10 bg-primary/5 px-2.5 py-1 text-xs font-medium">
            {item.title}
          </span>
        ))}
      </div>
    );
  }
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {normalized.slice(0, compact ? 4 : 8).map((item, index) => (
        <div key={`${item.title}-${index}`} className="rounded-xl border bg-background/70 px-3 py-2.5">
          <div className="text-sm font-semibold">{item.title}</div>
          {item.meta && <div className="mt-0.5 text-xs text-muted-foreground">{item.meta}</div>}
        </div>
      ))}
    </div>
  );
}

export function PresentationValue({ value, field, compact = false }) {
  if (["tags", "collection"].includes(field?.format) || Array.isArray(value)) {
    return <CollectionValue value={value} compact={compact} />;
  }
  const text = formatArtifactValue(value, field);
  return text || null;
}

function fallbackTitle(item) {
  return safeString(item?.name || item?.group || item?.client || item?.invoice_number || "Record");
}

export function ArtifactRecordCard({ item, presentation, compact = false }) {
  const fields = artifactFields(presentation).filter((field) => hasArtifactValue(artifactValue(item, field)));
  const titleField = fields.find((field) => field.role === "title");
  const subtitleFields = fields.filter((field) => field.role === "subtitle").slice(0, 2);
  const badgeField = fields.find((field) => field.role === "badge");
  const metricFields = fields.filter((field) => field.role === "metric").slice(0, compact ? 2 : 4);
  const detailFields = fields.filter((field) => field.role === "detail").slice(0, compact ? 2 : 3);
  const collectionFields = fields.filter((field) => field.role === "collection").slice(0, 1);
  const title = formatArtifactValue(artifactValue(item, titleField), titleField) || fallbackTitle(item);
  const path = profilePath(item?.profile_ref);
  return (
    <article className="group relative overflow-hidden rounded-2xl border bg-card shadow-[0_12px_32px_hsl(var(--primary)/.055)] transition duration-200 hover:-translate-y-0.5 hover:border-primary/25 hover:shadow-[0_16px_40px_hsl(var(--primary)/.09)]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-primary via-accent to-emerald-500" />
      <div className={cn("flex h-full flex-col", compact ? "p-3.5" : "p-4")}>
        <div className="flex items-start gap-3">
          {item?.rank ? (
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/12 text-amber-700">
              <span className="text-xs font-bold">#{item.rank}</span>
            </div>
          ) : (
            <EntityAvatar name={title} kind={item?.profile_ref?.kind} avatarUrl={item?.avatar_url} className="h-10 w-10 rounded-xl text-sm" />
          )}
          <div className="min-w-0 flex-1">
            <h4 className="truncate font-display text-lg font-semibold">{title}</h4>
            {!!subtitleFields.length && (
              <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-muted-foreground">
                {subtitleFields.map((field) => formatArtifactValue(artifactValue(item, field), field)).filter(Boolean).join(" / ")}
              </p>
            )}
          </div>
          {badgeField && <EntityStatusBadge value={artifactValue(item, badgeField)} />}
        </div>
        {!!metricFields.length && (
          <div className="mt-4 grid grid-cols-2 gap-2">
            {metricFields.map((field) => (
              <div key={field.key} className="rounded-xl bg-secondary/55 px-3 py-2.5">
                <div className="text-[10px] font-semibold uppercase tracking-[.1em] text-muted-foreground">{field.label}</div>
                <div className="mt-1 truncate text-sm font-semibold"><PresentationValue value={artifactValue(item, field)} field={field} compact /></div>
              </div>
            ))}
          </div>
        )}
        {!!detailFields.length && (
          <dl className="mt-4 space-y-2 border-t pt-3 text-xs">
            {detailFields.map((field) => (
              <div key={field.key} className="flex items-start justify-between gap-3">
                <dt className="text-muted-foreground">{field.label}</dt>
                <dd className="max-w-[62%] text-right font-medium"><PresentationValue value={artifactValue(item, field)} field={field} compact /></dd>
              </div>
            ))}
          </dl>
        )}
        {!!collectionFields.length && (
          <div className="mt-3 border-t pt-3">
            <CollectionValue value={artifactValue(item, collectionFields[0])} compact />
          </div>
        )}
        {path && (
          <EntityProfileLink
            profileRef={item.profile_ref}
            ariaLabel={`Open ${title} profile`}
            className="mt-auto inline-flex items-center gap-2 pt-4 text-sm font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Open profile <ArrowRight aria-hidden="true" />
          </EntityProfileLink>
        )}
      </div>
    </article>
  );
}

export function ArtifactCardGrid({ items = [], presentation, compact = false, limit }) {
  const visible = Number.isInteger(limit) ? items.slice(0, limit) : items;
  return (
    <div className={cn(
      "grid gap-3",
      compact ? "grid-cols-1" : "sm:grid-cols-2 xl:grid-cols-3",
    )}>
      {visible.map((item, index) => (
        <ArtifactRecordCard
          key={`${fallbackTitle(item)}-${item?.rank || index}`}
          item={item}
          presentation={presentation}
          compact={compact}
        />
      ))}
    </div>
  );
}
