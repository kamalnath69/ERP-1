const PROFILE_ROUTES = {
  client: "/app/clients/",
  employee: "/app/team/",
  catalog: "/app/catalog/",
  invoice: "/app/sales/",
};

export const PROFILE_INTERNAL_FIELDS = new Set([
  "id", "client_id", "employee_id", "item_id", "profile_ref", "avatar_url",
  "display_name", "display_meta", "selection_ref", "kind", "confidence", "matched_by", "snapshot",
]);

export function profilePath(ref) {
  if (!ref || typeof ref !== "object") return null;
  const base = PROFILE_ROUTES[ref.kind];
  const id = typeof ref.id === "string" ? ref.id.trim() : "";
  return base && id ? `${base}${encodeURIComponent(id)}` : null;
}

export function profileRef(kind, id) {
  return kind && id ? { kind, id } : null;
}

export function visibleProfileFields(item, limit = 4) {
  return Object.entries(item || {})
    .filter(([key, value]) => !PROFILE_INTERNAL_FIELDS.has(key) && value != null && value !== "")
    .slice(0, limit);
}
