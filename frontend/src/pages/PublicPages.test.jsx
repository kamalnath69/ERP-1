import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const mocks = vi.hoisted(() => ({
  clear: vi.fn(),
  load: vi.fn(),
}));

vi.mock("@/components/public/PublicSiteLayout", () => ({
  usePublicSite: () => ({ site: { legal_documents: { terms: { version: 1 } } } }),
}));

vi.mock("@/lib/publicLegalDocuments", () => ({
  clearPublicLegalDocumentCache: mocks.clear,
  loadPublicLegalDocument: mocks.load,
}));

import { LegalPage } from "./PublicPages";

test("keeps a legal page in its document loading state until content is ready", async () => {
  let resolveDocument;
  mocks.load.mockReturnValue(new Promise((resolve) => { resolveDocument = resolve; }));
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<MemoryRouter initialEntries={["/terms"]}><Routes><Route path="/terms" element={<LegalPage kind="terms" />} /></Routes></MemoryRouter>);
    await Promise.resolve();
  });

  expect(container.querySelector('[aria-label="Loading document"]')).not.toBeNull();
  expect(container.textContent).not.toContain("Document unavailable");

  await act(async () => {
    resolveDocument({
      id: "terms-current",
      title: "Terms of Service",
      effective_at: "2026-08-13T00:00:00Z",
      content_markdown: "# Terms of Service\n\n## Accounts\n\nUse your account responsibly.",
    });
    await Promise.resolve();
  });

  expect(container.querySelector('[aria-label="Loading document"]')).toBeNull();
  expect(container.textContent).toContain("Use your account responsibly.");
  expect(container.textContent).not.toContain("Document unavailable");

  act(() => root.unmount());
  container.remove();
  delete global.IS_REACT_ACT_ENVIRONMENT;
});
