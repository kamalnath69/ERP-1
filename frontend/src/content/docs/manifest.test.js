import { docsManifest } from "./manifest";

test("documentation slugs are unique and cover every supported public guide", () => {
  const slugs = docsManifest.map((document) => document.slug);
  expect(new Set(slugs).size).toBe(slugs.length);
  expect(slugs).toEqual(expect.arrayContaining([
    "overview", "workspace-setup", "roles-and-audits", "edvatiq-ai", "core-modules",
    "gym", "salon", "clinic", "college-placement", "erp-pull", "erp-push",
    "erp-schemas", "billing", "troubleshooting", "security",
  ]));
  expect(docsManifest.every((document) => document.title && document.description && document.content.startsWith("# "))).toBe(true);
});

test("public documentation does not link to private browser or platform APIs", () => {
  const markdown = docsManifest.map((document) => document.content).join("\n");
  expect(markdown).not.toMatch(/\/api\/(?:auth|super-admin|users|settings)\//);
  expect(markdown).toContain("/api/integrations/v1/openapi.json");
});
