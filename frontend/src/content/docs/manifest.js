import overview from "./overview.md?raw";
import workspaceSetup from "./workspace-setup.md?raw";
import rolesAndAudits from "./roles-and-audits.md?raw";
import edvatiqAi from "./edvatiq-ai.md?raw";
import coreModules from "./core-modules.md?raw";
import gym from "./gym.md?raw";
import salon from "./salon.md?raw";
import clinic from "./clinic.md?raw";
import collegePlacement from "./college-placement.md?raw";
import erpPull from "./erp-pull.md?raw";
import erpPush from "./erp-push.md?raw";
import erpSchemas from "./erp-schemas.md?raw";
import billing from "./billing.md?raw";
import troubleshooting from "./troubleshooting.md?raw";
import security from "./security.md?raw";

/**
 * @typedef {Object} DocumentationPage
 * @property {string} group
 * @property {string} slug
 * @property {string} title
 * @property {string} description
 * @property {string} content
 */

/** @type {DocumentationPage[]} */
export const docsManifest = [
  { group: "Get started", slug: "overview", title: "Overview", description: "Understand Edvatiq and choose a useful starting workflow.", content: overview },
  { group: "Get started", slug: "workspace-setup", title: "Workspace setup", description: "Configure identity, locations, and a safe rollout.", content: workspaceSetup },
  { group: "Platform", slug: "roles-and-audits", title: "Roles and audits", description: "Permissions, scopes, sensitive actions, and accountability.", content: rolesAndAudits },
  { group: "Platform", slug: "edvatiq-ai", title: "Edvatiq AI", description: "Evidence-backed answers, language, personalization, and actions.", content: edvatiqAi },
  { group: "Platform", slug: "core-modules", title: "Core modules", description: "People, calendar, sales, inventory, documents, and reports.", content: coreModules },
  { group: "Industry guides", slug: "gym", title: "Gym and fitness", description: "Membership, check-in, coaching, and billing workflows.", content: gym },
  { group: "Industry guides", slug: "salon", title: "Salon and spa", description: "Appointments, preferences, checkout, and inventory.", content: salon },
  { group: "Industry guides", slug: "clinic", title: "Outpatient clinic", description: "Clinical permissions and encounter workflows.", content: clinic },
  { group: "Industry guides", slug: "college-placement", title: "College placement", description: "Readiness, eligibility, pipeline, and ERP boundaries.", content: collegePlacement },
  { group: "College ERP", slug: "erp-pull", title: "ERP pull", description: "HTTPS connector mapping, pagination, staging, and ownership.", content: erpPull },
  { group: "College ERP", slug: "erp-push", title: "ERP push API", description: "Credentials, requests, idempotency, and partial results.", content: erpPush },
  { group: "College ERP", slug: "erp-schemas", title: "Resource schemas", description: "Canonical student, academic, and clearance fields.", content: erpSchemas },
  { group: "Account", slug: "billing", title: "Plans and billing", description: "Registration, subscriptions, credits, tax, and refunds.", content: billing },
  { group: "Help", slug: "troubleshooting", title: "Troubleshooting", description: "Resolve session, integration, and data-scope issues.", content: troubleshooting },
  { group: "Help", slug: "security", title: "Integration security", description: "Secret handling, network controls, and tenant isolation.", content: security },
];

export const docsBySlug = Object.fromEntries(docsManifest.map((document) => [document.slug, document]));
