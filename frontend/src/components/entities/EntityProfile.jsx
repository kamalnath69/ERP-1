import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Package, User } from "@phosphor-icons/react";
import api from "@/lib/api";
import { profilePath } from "@/lib/profileNavigation";
import { workspaceApi } from "@/store/api/workspaceApi";
import { clientApi } from "@/features/clients/clientApi";
import { useBusiness } from "@/contexts/BusinessContext";

const secureImageCache = new Map();

function acquireSecureImage(url) {
  let entry = secureImageCache.get(url);
  if (!entry) {
    entry = { refs: 0, source: "", timer: null, promise: null };
    entry.promise = api.get(url, { responseType: "blob" }).then(({ data }) => {
      entry.source = URL.createObjectURL(data);
      return entry.source;
    }).catch((error) => {
      secureImageCache.delete(url);
      throw error;
    });
    secureImageCache.set(url, entry);
  }
  entry.refs += 1;
  if (entry.timer) { clearTimeout(entry.timer); entry.timer = null; }
  return entry;
}

function releaseSecureImage(url, entry) {
  entry.refs = Math.max(0, entry.refs - 1);
  if (entry.refs || entry.timer) return;
  entry.timer = setTimeout(() => {
    if (entry.refs || secureImageCache.get(url) !== entry) return;
    if (entry.source) URL.revokeObjectURL(entry.source);
    secureImageCache.delete(url);
  }, 60_000);
}

export function EntityAvatar({ name, kind, avatarUrl, className = "h-12 w-12" }) {
  const [source, setSource] = useState("");
  useEffect(() => {
    let active = true;
    if (!avatarUrl) { setSource(""); return undefined; }
    const entry = acquireSecureImage(avatarUrl);
    if (entry.source) setSource(entry.source);
    else entry.promise.then((value) => active && setSource(value)).catch(() => active && setSource(""));
    return () => { active = false; releaseSecureImage(avatarUrl, entry); };
  }, [avatarUrl]);
  const initial = String(name || "?").trim().charAt(0).toUpperCase();
  return <span className={`${className} shrink-0 overflow-hidden rounded-2xl bg-secondary text-foreground grid place-items-center font-display text-xl`}>
    {source ? <img src={source} alt={`${name || "Entity"} profile`} className="h-full w-full object-cover" /> : kind === "catalog" ? <Package size={22} /> : initial || <User size={22} />}
  </span>;
}

export function EntityStatusBadge({ value }) {
  if (value == null || value === "") return null;
  const normalized = String(value).toLowerCase();
  const tone = ["active", "healthy", "paid", "completed"].includes(normalized)
    ? "bg-emerald-100 text-emerald-800"
    : ["inactive", "cancelled", "blocked", "overdue"].includes(normalized)
      ? "bg-red-100 text-red-800" : "bg-secondary text-muted-foreground";
  return <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${tone}`}>{String(value).replaceAll("_", " ")}</span>;
}

export function EntityProfileLink({ profileRef, className = "", children, ariaLabel, onClick }) {
  const { path, source, prefetch } = useProfileDestination(profileRef);
  if (!path) return <span className={className}>{children}</span>;
  return <Link to={path} state={{ profileFrom: source }} aria-label={ariaLabel}
    onPointerEnter={prefetch} onFocus={prefetch} onClick={onClick} className={className}>{children}</Link>;
}

export function ProfileTableRow({ profileRef, className = "", children, ariaLabel }) {
  const navigate = useNavigate(); const { path, source, prefetch } = useProfileDestination(profileRef);
  const open = (event) => {
    if (!path || event.target.closest("a,button,input,select,textarea")) return;
    navigate(path, { state: { profileFrom: source } });
  };
  const keyDown = (event) => {
    if (!path || !["Enter", " "].includes(event.key)) return;
    event.preventDefault(); navigate(path, { state: { profileFrom: source } });
  };
  return <tr className={`${className} ${path ? "cursor-pointer hover:bg-secondary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent" : ""}`}
    role={path ? "link" : undefined} tabIndex={path ? 0 : undefined} aria-label={path ? ariaLabel : undefined}
    onClick={open} onKeyDown={keyDown} onPointerEnter={prefetch} onFocus={prefetch}>{children}</tr>;
}

export function ProfileBackLink({ fallback, children, className = "" }) {
  const navigate = useNavigate(); const location = useLocation();
  if (location.state?.profileFrom) return <button type="button" onClick={() => navigate(-1)} className={className}>{children}</button>;
  return <Link to={fallback} className={className}>{children}</Link>;
}

function useProfileDestination(profileRef) {
  const path = profilePath(profileRef); const location = useLocation();
  const { locationId } = useBusiness() || {};
  const prefetchClient = clientApi.usePrefetch("getClientWorkspace");
  const prefetchEmployee = workspaceApi.usePrefetch("getEmployeeProfile");
  const prefetchCatalog = workspaceApi.usePrefetch("getCatalogProfile");
  const prefetch = () => {
    if (!path) return;
    if (profileRef.kind === "client") prefetchClient({ clientId: profileRef.id, range: "30d" }, { ifOlderThan: 60 });
    if (profileRef.kind === "employee") prefetchEmployee(profileRef.id, { ifOlderThan: 120 });
    if (profileRef.kind === "catalog") prefetchCatalog({ itemId: profileRef.id, locationId }, { ifOlderThan: 60 });
  };
  return { path, source: `${location.pathname}${location.search}`, prefetch };
}

export function EntityCard({ item, details = [] }) {
  const name = item.display_name || item.name || "Business record";
  const hasProfile = Boolean(profilePath(item.profile_ref));
  const status = item.status ?? (typeof item.active === "boolean" ? (item.active ? "active" : "inactive") : null);
  const content = <>
    <div className="flex items-start justify-between gap-3">
      <EntityAvatar name={name} kind={item.profile_ref?.kind} avatarUrl={item.avatar_url} />
      <EntityStatusBadge value={status} />
    </div>
    <h4 className="mt-4 truncate font-display text-xl font-semibold">{name}</h4>
    <p className="mt-1 min-h-5 truncate text-sm text-muted-foreground">{item.display_meta || "View complete business profile"}</p>
    {!!details.length && <div className="mt-4 space-y-1.5 border-t pt-3 text-xs">{details.map(([label, value]) => <div key={label} className="flex justify-between gap-3"><span className="capitalize text-muted-foreground">{label.replaceAll("_", " ")}</span><span className="max-w-[60%] truncate text-right">{value}</span></div>)}</div>}
    {hasProfile && <div className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-accent">Open profile <ArrowRight /></div>}
  </>;
  if (!hasProfile) return <article className="rounded-2xl border bg-card p-5">{content}</article>;
  return <EntityProfileLink profileRef={item.profile_ref} ariaLabel={`Open ${name} profile`}
    className="block rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:border-accent hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">{content}</EntityProfileLink>;
}
