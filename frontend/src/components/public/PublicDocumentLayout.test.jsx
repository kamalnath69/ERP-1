import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import PublicDocumentLayout, { DocumentNavLink } from "./PublicDocumentLayout";

function renderLayout(props = {}) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <PublicDocumentLayout
        title="Terms of Service"
        eyebrow="Authoritative policy"
        breadcrumbs={[{ label: "Resources", to: "/docs" }, { label: "Terms" }]}
        navigationTitle="Legal center"
        renderNavigation={() => <DocumentNavLink to="/terms" active title="Terms" />}
        {...props}
      >
        <h2 id="accounts">Accounts</h2>
      </PublicDocumentLayout>
    </MemoryRouter>,
  );
}

test("renders the shared document workspace, actions, navigation, and contents rail", () => {
  const html = renderLayout({ headings: [{ id: "accounts", title: "Accounts", level: 2 }] });

  expect(html).toContain("document-workspace");
  expect(html).toContain("Copy link");
  expect(html).toContain("Print");
  expect(html).toContain("Browse");
  expect(html).toContain("On this page");
  expect(html).toContain('aria-current="page"');
});

test("omits document actions and the contents rail when they are not useful", () => {
  const html = renderLayout({ headings: [], showActions: false });

  expect(html).not.toContain("Copy link");
  expect(html).not.toContain("On this page");
  expect(html).toContain("document-workspace");
});

test("reserves document actions and contents while an article is loading", () => {
  const html = renderLayout({
    headings: [],
    showActions: false,
    actionsLoading: true,
    contentsLoading: true,
    metaLoading: true,
  });

  expect(html).not.toContain("Copy link");
  expect(html).toContain("document-actions");
  expect(html).toContain("On this page");
  expect(html).toContain("animate-pulse");
});
