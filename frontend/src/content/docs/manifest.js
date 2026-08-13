const markdownLoaders = import.meta.glob("./*.md", {
  query: "?raw",
  import: "default",
});

/**
 * @typedef {Object} DocumentationPage
 * @property {string} group
 * @property {string} slug
 * @property {string} title
 * @property {string} description
 */

const documentDefinitions = [
  { source: "./overview.md", group: "Get started", slug: "overview", title: "Overview", description: "Understand Edvatiq and choose a useful starting workflow." },
  { source: "./workspace-setup.md", group: "Get started", slug: "workspace-setup", title: "Workspace setup", description: "Configure identity, locations, and a safe rollout." },
  { source: "./roles-and-audits.md", group: "Platform", slug: "roles-and-audits", title: "Roles and audits", description: "Permissions, scopes, sensitive actions, and accountability." },
  { source: "./edvatiq-ai.md", group: "Platform", slug: "edvatiq-ai", title: "Edvatiq AI", description: "Evidence-backed answers, language, personalization, and actions." },
  { source: "./core-modules.md", group: "Platform", slug: "core-modules", title: "Core modules", description: "People, calendar, sales, inventory, documents, and reports." },
  { source: "./gym.md", group: "Industry guides", slug: "gym", title: "Gym and fitness", description: "Membership, check-in, coaching, and billing workflows." },
  { source: "./salon.md", group: "Industry guides", slug: "salon", title: "Salon and spa", description: "Appointments, preferences, checkout, and inventory." },
  { source: "./clinic.md", group: "Industry guides", slug: "clinic", title: "Outpatient clinic", description: "Clinical permissions and encounter workflows." },
  { source: "./college-placement.md", group: "Industry guides", slug: "college-placement", title: "College placement", description: "Readiness, eligibility, pipeline, and ERP boundaries." },
  { source: "./assessment-patterns.md", group: "College data", slug: "assessment-patterns", title: "Assessment patterns", description: "Configure institution-specific exams, metrics, calculations, versions, and readiness mappings." },
  { source: "./data-exchange.md", group: "College data", slug: "data-exchange", title: "Data Exchange", description: "Manual, Excel, CSV, ERP, API, preview, update, and export workflows." },
  { source: "./erp-pull.md", group: "College ERP", slug: "erp-pull", title: "ERP pull", description: "HTTPS connector mapping, pagination, staging, and ownership." },
  { source: "./erp-push.md", group: "College ERP", slug: "erp-push", title: "ERP push API", description: "Credentials, requests, idempotency, and partial results." },
  { source: "./erp-schemas.md", group: "College ERP", slug: "erp-schemas", title: "Resource schemas", description: "Canonical student, academic, and clearance fields." },
  { source: "./billing.md", group: "Account", slug: "billing", title: "Plans and billing", description: "Registration, subscriptions, credits, tax, and refunds." },
  { source: "./troubleshooting.md", group: "Help", slug: "troubleshooting", title: "Troubleshooting", description: "Resolve session, integration, and data-scope issues." },
  { source: "./security.md", group: "Help", slug: "security", title: "Integration security", description: "Secret handling, network controls, and tenant isolation." },
];

/** @type {DocumentationPage[]} */
export const docsManifest = documentDefinitions.map(({ source: _source, ...document }) => Object.freeze(document));

export const docsBySlug = Object.freeze(Object.fromEntries(docsManifest.map((document) => [document.slug, document])));

const loaderBySlug = Object.fromEntries(documentDefinitions.map(({ slug, source }) => [slug, markdownLoaders[source]]));
const contentCache = new Map();

export function filterDocumentationMetadata(query = "") {
  const value = normalizeSearchValue(query);
  if (!value) return docsManifest;
  return docsManifest.filter((document) => normalizeSearchValue(`${document.group} ${document.title} ${document.description}`).includes(value));
}

export function loadDocumentationContent(slug) {
  if (contentCache.has(slug)) return contentCache.get(slug);
  const loader = loaderBySlug[slug];
  if (!loader) return Promise.reject(new Error("Documentation guide not found"));

  const request = Promise.resolve(loader())
    .then((content) => String(content || ""))
    .catch((error) => {
      contentCache.delete(slug);
      throw error;
    });
  contentCache.set(slug, request);
  return request;
}

export async function searchDocumentation(query = "") {
  const value = normalizeSearchValue(query);
  if (!value) return docsManifest;

  const results = await Promise.all(docsManifest.map(async (document) => {
    const metadata = normalizeSearchValue(`${document.group} ${document.title} ${document.description}`);
    if (metadata.includes(value)) return document;
    try {
      const content = await loadDocumentationContent(document.slug);
      return normalizeSearchValue(content).includes(value) ? document : null;
    } catch {
      return null;
    }
  }));
  return results.filter(Boolean);
}

function normalizeSearchValue(value) {
  return String(value).trim().toLowerCase().replace(/\s+/g, " ");
}
