import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import ResponseBlocks, { measureFirstRow } from "./ResponseBlocks";
import { baseApi } from "@/store/api/baseApi";

const store = configureStore({ reducer: { [baseApi.reducerPath]: baseApi.reducer }, middleware: (getDefault) => getDefault().concat(baseApi.middleware) });
const render = (children) => renderToStaticMarkup(<Provider store={store}><MemoryRouter>{children}</MemoryRouter></Provider>);

test("renders structured records without passing objects to React", () => {
  const html = render(<ResponseBlocks message={{ blocks: [{
    id: "clients", type: "table", title: "Clients",
    data: { total: 12, result_session_id: "result-1", items: [{ id: "1", name: "Kamal", details: { status: "active" } }] },
  }] }} onViewAll={() => {}} onPin={() => {}} onConfirm={() => {}} onUndo={() => {}} />);
  expect(html).toContain("status: active");
  expect(html).toContain("View all");
});

test("does not expose internal tool traces", () => {
  const html = render(<ResponseBlocks message={{ blocks: [{ id: "summary", type: "text", data: { text: "Safe" } }] }} />);
  expect(html.toLowerCase()).not.toContain("tool trace");
});

test("renders entity results as allowlisted profile cards", () => {
  const html = render(<ResponseBlocks message={{ blocks: [{
    id: "employees", type: "entity_cards", title: "Employees",
    data: { total: 1, entity_kind: "employee", items: [{
      id: "employee-1", display_name: "Gopal Vaarma", display_meta: "Manager",
      status: "active", profile_ref: { kind: "employee", id: "employee-1" },
      selection_ref: { kind: "employee", id: "employee-1" }, confidence: 100,
    }] },
  }] }} onSelectEntity={() => {}} />);
  expect(html).toContain("Gopal Vaarma");
  expect(html).toContain("Open profile");
  expect(html).toContain('/app/team/employee-1');
  expect(html).toContain("Use this record");
  expect(html).not.toContain("profile_ref");
  expect(html).not.toContain("confidence");
});

test("collapses catalog and stock-level matches into one product profile", () => {
  const catalogRef = { kind: "catalog", id: "product-1" };
  const html = render(<ResponseBlocks message={{ blocks: [{
    id: "product", type: "entity_cards", title: "Matching business records",
    data: { total: 3, items: [
      { id: "product-1", kind: "catalog", display_name: "Whey Protein 1 kg", display_meta: "WHEY-1", status: "active", profile_ref: catalogRef },
      { id: "stock-1", kind: "inventory", display_name: "Whey Protein 1 kg", status: "low", profile_ref: catalogRef, snapshot: { quantity_milli: 3000 } },
      { id: "stock-2", kind: "inventory", display_name: "Whey Protein 1 kg", status: "available", profile_ref: catalogRef, snapshot: { quantity_milli: 18000 } },
    ] },
  }] }} />);

  expect(html.match(/Open profile/g)).toHaveLength(1);
  expect(html).toContain("1 found");
  expect(html).toContain("21");
  expect(html).toContain('/app/catalog/product-1');
});

test("measures only cards in the first visual row", () => {
  expect(measureFirstRow([
    { offsetTop: 0, offsetHeight: 120 },
    { offsetTop: 0, offsetHeight: 132 },
    { offsetTop: 144, offsetHeight: 120 },
  ])).toEqual({ visibleCount: 2, rowHeight: 132 });
});

test("offers query-backed view all without requiring a live session", () => {
  const html = render(<ResponseBlocks message={{ blocks: [{
    id: "clients", type: "entity_cards", title: "Clients",
    data: {
      total: 3,
      query_spec: { engine: "local_v1", subject: "clients" },
      items: [
        { id: "1", display_name: "One", profile_ref: { kind: "client", id: "1" } },
        { id: "2", display_name: "Two", profile_ref: { kind: "client", id: "2" } },
      ],
    },
  }] }} onViewAll={() => {}} onPin={() => {}} />);

  expect(html).toContain("View all");
  expect(html).not.toContain("Pin");
});

test("does not hide candidate cards when no result drawer can be opened", () => {
  const html = render(<ResponseBlocks message={{ blocks: [{
    id: "candidates", type: "entity_cards", title: "Choose a record",
    data: { total: 2, items: [
      { id: "1", display_name: "First candidate" },
      { id: "2", display_name: "Second candidate" },
    ] },
  }] }} />);

  expect(html).toContain("First candidate");
  expect(html).toContain("Second candidate");
  expect(html).not.toContain("View all");
});
