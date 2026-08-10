import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { baseApi } from "@/store/api/baseApi";
import { SearchResults } from "./AppLayout";

const store = configureStore({
  reducer: { [baseApi.reducerPath]: baseApi.reducer },
  middleware: (getDefault) => getDefault().concat(baseApi.middleware),
});

function render(component) {
  return renderToStaticMarkup(<Provider store={store}><MemoryRouter>{component}</MemoryRouter></Provider>);
}

test("renders ranked search results as profile rows with avatars above page content", () => {
  const html = render(<SearchResults close={() => {}} results={{
    clients: [{
      id: "client-1", display_name: "Kavinraj", display_meta: "9000012345",
      status: "active", avatar_url: "/clients/client-1/photo?v=1",
    }],
    employees: [],
    catalog: [],
  }} />);

  expect(html).toContain("Kavinraj");
  expect(html).toContain("9000012345");
  expect(html).toContain("/app/clients/client-1");
  expect(html).toContain("z-[100]");
});

test("shows a stable search loading state", () => {
  const html = render(<SearchResults close={() => {}} loading results={{ clients: [], employees: [], catalog: [] }} />);
  expect(html).toContain("Searching");
  expect(html).not.toContain("No matching clients");
});
