import {
  docsManifest, loadDocumentationContent, searchDocumentation,
} from "./manifest";

test("documentation slugs are unique and cover every supported public guide", () => {
  const slugs = docsManifest.map((document) => document.slug);
  expect(new Set(slugs).size).toBe(slugs.length);
  expect(slugs).toEqual(expect.arrayContaining([
    "overview", "workspace-setup", "roles-and-audits", "edvatiq-ai", "core-modules",
    "gym", "salon", "clinic", "college-placement", "assessment-patterns", "data-exchange",
    "erp-pull", "erp-push", "erp-schemas", "billing", "troubleshooting", "security",
  ]));
  expect(docsManifest.every((document) => document.title && document.description && !("content" in document))).toBe(true);
});

test("documentation content is loaded on demand and remains public-safe", async () => {
  const markdown = (await Promise.all(docsManifest.map((document) => loadDocumentationContent(document.slug)))).join("\n");
  expect(markdown).toContain("# Edvatiq");
  expect(markdown).not.toMatch(/\/api\/(?:auth|super-admin|users|settings)\//);
  expect(markdown).toContain("/api/integrations/v1/openapi.json");
});

test("full-text search can find content that is not stored in manifest metadata", async () => {
  const results = await searchDocumentation("Idempotency-Key");
  expect(results.map((document) => document.slug)).toContain("erp-push");
});
