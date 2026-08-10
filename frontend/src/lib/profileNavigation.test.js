import { profilePath, visibleProfileFields } from "./profileNavigation";

test("resolves only allowlisted profile kinds", () => {
  expect(profilePath({ kind: "client", id: "client-1" })).toBe("/app/clients/client-1");
  expect(profilePath({ kind: "employee", id: "employee-1" })).toBe("/app/team/employee-1");
  expect(profilePath({ kind: "catalog", id: "item-1" })).toBe("/app/catalog/item-1");
  expect(profilePath({ kind: "invoice", id: "invoice-1" })).toBe("/app/sales/invoice-1");
  expect(profilePath({ kind: "client", id: "" })).toBeNull();
});

test("removes routing metadata and raw identifiers from visible fields", () => {
  const fields = visibleProfileFields({ id: "1", client_id: "2", profile_ref: { kind: "client", id: "2" }, display_name: "Kamal", status: "active" });
  expect(fields).toEqual([["status", "active"]]);
});
