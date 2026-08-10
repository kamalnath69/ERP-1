import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import Settings, {
  SETTINGS_DRAFT_PREFIX, normalizeSettingsSection, readSettingsDrafts, writeSettingsDrafts,
} from "./Settings";

const mockSettingsData = {
  organization: {
    id: "org-1", name: "Pulse Fitness", legal_name: "Pulse Fitness Private Limited",
    industry: "gym", timezone: "Asia/Kolkata", currency: "INR", gstin: "33ABCDE1234F1Z5",
    invoice_prefix: "PF", contact_email: "hello@pulse.test", contact_phone: "9884000000",
    description: "A modern fitness studio", settings_version: 3,
  },
  locations: [{
    id: "location-1", name: "Main Studio", code: "MAIN", address: "48 Cathedral Road",
    city: "Chennai", state: "Tamil Nadu", postal_code: "600086", phone: "9884000001",
    gstin: "33ABCDE1234F1Z5", is_primary: true, version: 1,
  }],
  tax: { prices_include_tax: true, default_tax_rate_bps: 1800 },
  operations: {
    attendance_edit_window_minutes: 60, class_booking_window_days: 30,
    default_freeze_limit_days: 30, allow_checkin_without_membership: false,
  },
  communications: {
    appointment_reminders: true, payment_reminders: true,
    membership_reminders: true, follow_up_reminders: false,
  },
  security: { mfa_policy: "privileged" },
  privacy: { conversation_retention_days: 90 },
  modules: ["ai", "gym", "sales"],
  integrations: {
    security_email: { ready: true },
    whatsapp: { ready: false },
    payments: { managed_by_platform: true },
    storage: { managed_by_platform: true },
    ai: { managed_by_platform: true },
  },
  pending_industry_request: null,
  audit: [{ id: "audit-1", action: "settings.identity.updated", actor: "Kamal", created_at: "2026-08-04T10:00:00Z" }],
  capabilities: {
    identity_manage: true, locations_manage: true, tax_manage: true,
    operations_manage: true, communications_manage: true, security_manage: true,
    privacy_manage: true, audit_view: true,
  },
};

const mockPermissions = new Set(["roles.manage", "billing.view"]);
const mockRefetch = jest.fn();
const mockSaveSection = jest.fn();

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ can: (code) => mockPermissions.has(code) }),
}));

jest.mock("@/contexts/BusinessContext", () => ({
  useBusiness: () => ({ refresh: jest.fn() }),
}));

jest.mock("@/features/settings/settingsApi", () => ({
  useGetSettingsWorkspaceQuery: () => ({ data: mockSettingsData, isLoading: false, error: null, refetch: mockRefetch }),
  useUpdateSettingsSectionMutation: () => [mockSaveSection, { isLoading: false }],
  useCreateLocationMutation: () => [jest.fn(), { isLoading: false }],
  useUpdateLocationMutation: () => [jest.fn(), { isLoading: false }],
  useRequestIndustryMigrationMutation: () => [jest.fn(), { isLoading: false }],
}));

afterEach(() => {
  mockSettingsData.capabilities.identity_manage = true;
  mockSettingsData.capabilities.audit_view = true;
  mockPermissions.clear();
  mockPermissions.add("roles.manage");
  mockPermissions.add("billing.view");
  window.sessionStorage.clear();
  jest.clearAllMocks();
});

test("renders the restrained settings console and omits non-operational pages", () => {
  const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/app/settings"]}><Settings /></MemoryRouter>);

  expect(html).toContain("Organization settings");
  expect(html).toContain('data-secondary-sidebar-layout="true"');
  expect(html).toContain('aria-label="Settings sections"');
  expect(html).toContain("Business profile");
  expect(html).toContain("Locations");
  expect(html).toContain("Tax &amp; invoicing");
  expect(html).toContain("Sign-in policy");
  expect(html).toContain("Audit log");
  expect(html).toContain('href="/app/me"');
  expect(html).toContain('href="/app/access"');
  expect(html).toContain('href="/app/billing"');
  expect(html).not.toContain("Configuration snapshot");
  expect(html).not.toContain("Connected services");
  expect(html).not.toContain("Available modules");
  expect(html).not.toContain("Workflow rules");
  expect(html).not.toContain("Communication preferences");
  expect(html).not.toContain("Data &amp; privacy");
  expect(html).not.toContain("Credentials stay protected");
  expect(html).not.toContain("Manage the organization details and policies your team relies on.");
});

test("normalizes removed and unavailable section links to business profile", () => {
  expect(normalizeSettingsSection("overview", true)).toBe("identity");
  expect(normalizeSettingsSection("integrations", true)).toBe("identity");
  expect(normalizeSettingsSection("privacy", true)).toBe("identity");
  expect(normalizeSettingsSection("audit", false)).toBe("identity");
  expect(normalizeSettingsSection("tax", true)).toBe("tax");

  const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/app/settings?section=modules"]}><Settings /></MemoryRouter>);
  expect(html).toContain("Business profile");
  expect(html).toContain("Company details");
});

test("shows an honest read-only profile without save controls", () => {
  mockSettingsData.capabilities.identity_manage = false;
  const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/app/settings"]}><Settings /></MemoryRouter>);

  expect(html).toContain("View only");
  expect(html).toContain("<fieldset disabled");
  expect(html).not.toContain("Unsaved changes");
  expect(html).not.toContain("Save changes");
});

test("hides related administration links when permissions are unavailable", () => {
  mockPermissions.clear();
  const html = renderToStaticMarkup(<MemoryRouter initialEntries={["/app/settings"]}><Settings /></MemoryRouter>);

  expect(html).toContain('href="/app/me"');
  expect(html).not.toContain('href="/app/access"');
  expect(html).not.toContain('href="/app/billing"');
});

test("stores drafts by organization and invalidates them when the server version changes", () => {
  const baseline = {
    identity: { name: "Pulse", timezone: "Asia/Kolkata" },
    tax: { prices_include_tax: false, default_tax_rate_bps: 0 },
  };
  const sections = { identity: { name: "Pulse Labs", timezone: "Asia/Kolkata" } };

  writeSettingsDrafts("org-1", 3, sections);
  expect(readSettingsDrafts("org-1", 3, baseline)).toEqual({ sections, stale: false });
  expect(readSettingsDrafts("org-1", 4, baseline)).toEqual({ sections: {}, stale: true });
  expect(window.sessionStorage.getItem(`${SETTINGS_DRAFT_PREFIX}:org-1`)).toBeNull();
});

test("keeps a business profile draft while navigating to another settings section", () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => root.render(<MemoryRouter initialEntries={["/app/settings"]}><Settings /></MemoryRouter>));
  const nameInput = [...container.querySelectorAll("input")].find((input) => input.value === "Pulse Fitness");
  const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  act(() => {
    valueSetter.call(nameInput, "Pulse Fitness Labs");
    nameInput.dispatchEvent(new Event("input", { bubbles: true }));
  });

  expect(container.textContent).toContain("Unsaved changes");
  expect(JSON.parse(window.sessionStorage.getItem(`${SETTINGS_DRAFT_PREFIX}:org-1`)).sections.identity.name).toBe("Pulse Fitness Labs");

  const taxButton = [...container.querySelectorAll("button")].find((button) => button.textContent.trim() === "Tax & invoicing");
  act(() => taxButton.click());
  expect(container.textContent).toContain("Defaults applied when new operational invoices are prepared.");
  expect(container.querySelector('[aria-label="Business profile has unsaved changes"]')).not.toBeNull();

  act(() => root.unmount());
  container.remove();
  delete global.IS_REACT_ACT_ENVIRONMENT;
});
