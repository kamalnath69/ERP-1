import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";

import ResponseBlocks from "./ResponseBlocks";
import { baseApi } from "@/store/api/baseApi";

const store = configureStore({
  reducer: { [baseApi.reducerPath]: baseApi.reducer },
  middleware: (getDefault) => getDefault().concat(baseApi.middleware),
});
const render = (children) => renderToStaticMarkup(
  <Provider store={store}><MemoryRouter>{children}</MemoryRouter></Provider>,
);

const studentPresentation = {
  layout: "cards",
  entity: "student",
  preview_limit: 4,
  fields: [
    { key: "name", label: "Student name", format: "text", group: "Identity", role: "title", priority: 0 },
    { key: "program", label: "Program", format: "relation", group: "Enrollment", role: "subtitle", priority: 10 },
    { key: "status", label: "Status", format: "status", group: "Identity", role: "badge", priority: 5 },
    { key: "cgpa", label: "Current CGPA", format: "decimal", group: "Academics", role: "metric", priority: 10 },
    { key: "attendance_percent", label: "Attendance", format: "percent", group: "Attendance", role: "metric", priority: 20 },
  ],
};

test("renders four record cards and opens complete pagination without a table", () => {
  const items = ["Kamal", "Asha", "Bala", "Deepa", "Eshan"].map((name, index) => ({
    name, cgpa: 8.7 - index / 10, profile_ref: { kind: "client", id: `client-${index}` },
  }));
  const html = render(<ResponseBlocks message={{ artifacts: [{
    id: "students", type: "records", title: "Matching students",
    presentation: studentPresentation,
    data: {
      total: 12, has_more: true, result_session_id: "result-1",
      query: { goal: "list", entity: "student" }, items,
    },
  }] }} onViewAll={() => {}} onPin={() => {}} />);

  expect(html).toContain("Kamal");
  expect(html).toContain("Deepa");
  expect(html).not.toContain("Eshan");
  expect(html).toContain("View all 12");
  expect(html).not.toContain("<table");
});

test("renders a human profile with safe relations and a working client link", () => {
  const relationId = "f94d1b70-cf8e-42e4-8177-6781a6de3602";
  const html = render(<ResponseBlocks message={{ artifacts: [{
    id: "profile", type: "profile", title: "Lokesh Menon",
    presentation: { ...studentPresentation, layout: "profile" },
    data: {
      id: "student-internal",
      name: "Lokesh Menon",
      status: "active",
      cgpa: 7.03,
      attendance_percent: 84,
      program: { id: relationId, name: "B.Sc. Computer Science", code: "BSC-CS" },
      profile_ref: { kind: "client", id: "client-lokesh" },
    },
  }] }} />);

  expect(html).toContain("Verified profile");
  expect(html).toContain("Lokesh Menon");
  expect(html).toContain("B.Sc. Computer Science (BSC-CS)");
  expect(html).toContain('href="/app/clients/client-lokesh"');
  expect(html).toContain("Open full profile");
  expect(html).not.toContain(relationId);
  expect(html).not.toContain("student-internal");
});

test("does not render an inert profile action for a semantic student reference", () => {
  const html = render(<ResponseBlocks message={{ artifacts: [{
    id: "profile", type: "profile", title: "Lokesh Menon",
    presentation: { ...studentPresentation, layout: "profile" },
    data: { name: "Lokesh Menon", profile_ref: { kind: "student", id: "student-1" } },
  }] }} />);

  expect(html).not.toContain("Open full profile");
});

test("renders canonical ambiguity choices without a synthetic query", () => {
  const html = render(<ResponseBlocks message={{ artifacts: [{
    id: "clarification", type: "clarification", title: "Which student did you mean?",
    data: {
      clarification_id: "clarify-1",
      options: [{ label: "Kamal Raj", entity: { kind: "student", id: "student-7", label: "Kamal Raj" } }],
    },
  }] }} onSelectEntity={() => {}} />);

  expect(html).toContain("Choose one");
  expect(html).toContain("Kamal Raj");
  expect(html).not.toContain("Tell me about");
});

test("labels contextual suggestions and keeps evidence secondary", () => {
  const html = render(<ResponseBlocks message={{
    artifacts: [],
    suggestions: [{ id: "next", label: "Academic history", prompt: "Show academic history" }],
    evidence: [{
      source: "Edvatiq College records",
      authorized_scope: "your 34 authorized records",
      sample_size: 34,
      coverage_percent: 88,
      definitions: { high: "CGPA at least 8.0" },
    }],
  }} onSuggestion={() => {}} />);

  expect(html).toContain("You could also ask");
  expect(html).toContain("Academic history");
  expect(html).toContain("Evidence and scope");
  expect(html).toContain("your 34 authorized records");
});
