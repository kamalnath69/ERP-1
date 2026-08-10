import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Books } from "@phosphor-icons/react";

import {
  ChartPanel, EmptyState, PanelGrid, RemoteCombobox, ResponsiveCardGrid, SplitPane,
} from "./index";

test("renders purpose-specific empty states with actions and steps", () => {
  const html = renderToStaticMarkup(<EmptyState
    variant="page"
    alignment="left"
    icon={Books}
    title="Create your library"
    description="Start with one useful document."
    primaryAction={<button type="button">Upload document</button>}
    steps={[{ title: "Choose file" }, { title: "Set visibility" }, { title: "Use securely" }]}
  />);

  expect(html).toContain('data-empty-state="page"');
  expect(html).toContain("Create your library");
  expect(html).toContain("Upload document");
  expect(html).toContain("Choose file");
  expect(html).toContain("Use securely");
});

test("keeps compact backward compatibility without using a page-sized state", () => {
  const html = renderToStaticMarkup(<EmptyState compact title="Nothing waiting" />);

  expect(html).toContain('data-empty-state="section"');
  expect(html).not.toContain('data-empty-state="page"');
});

test("natural panel layouts do not opt into equal-height stretching", () => {
  const natural = renderToStaticMarkup(<PanelGrid><div>Short</div><div>Long</div></PanelGrid>);
  const equal = renderToStaticMarkup(<PanelGrid mode="equal"><div>One</div><div>Two</div></PanelGrid>);
  const split = renderToStaticMarkup(<SplitPane primary={<div>Primary</div>} secondary={<div>Secondary</div>} />);

  expect(natural).toContain("items-start");
  expect(natural).not.toContain("items-stretch");
  expect(equal).toContain("items-stretch");
  expect(split).toContain("items-start");
});

test("responsive card grids expose a safe configurable minimum width", () => {
  const html = renderToStaticMarkup(<ResponsiveCardGrid minWidth="15rem"><div>Card</div></ResponsiveCardGrid>);

  expect(html).toContain("responsive-card-grid");
  expect(html).toContain("--responsive-card-min:15rem");
});

test("chart panels fill their row only when explicitly requested", () => {
  const natural = renderToStaticMarkup(<ChartPanel title="Trend"><div>Chart</div></ChartPanel>);
  const filled = renderToStaticMarkup(<ChartPanel title="Trend" fillHeight><div>Chart</div></ChartPanel>);

  expect(natural).not.toContain("workspace-panel flex h-full");
  expect(filled).toContain("h-full");
});

test("remote combobox keeps the selected record visible before opening search", () => {
  const html = renderToStaticMarkup(<RemoteCombobox
    value="student-2"
    selectedItem={{ id: "student-2", name: "Ananya Rao" }}
    items={[]}
    placeholder="Choose student"
  />);

  expect(html).toContain("Ananya Rao");
  expect(html).toContain('role="combobox"');
  expect(html).toContain('aria-expanded="false"');
});
