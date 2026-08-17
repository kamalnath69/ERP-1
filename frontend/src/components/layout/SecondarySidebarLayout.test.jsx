import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";

import { routeForPath } from "@/app/routeManifest";
import SecondarySidebarLayout, { SecondarySidebarTrigger } from "./SecondarySidebarLayout";
import { List } from "@phosphor-icons/react";

test("renders a reusable edge-aligned sidebar and content workspace", () => {
  const html = renderToStaticMarkup(<SecondarySidebarLayout
    ariaLabel="Example sections"
    sidebarWidthClassName="w-[17rem]"
    sidebar={<nav>Secondary navigation</nav>}
  ><main>Workspace content</main></SecondarySidebarLayout>);

  expect(html).toContain('data-secondary-sidebar-layout="true"');
  expect(html).toContain('aria-label="Example sections"');
  expect(html).toContain("w-[17rem]");
  expect(html.indexOf("Secondary navigation")).toBeLessThan(html.indexOf("Workspace content"));
});

test("defaults to an expanded rail narrower than the 232px primary sidebar", () => {
  const html = renderToStaticMarkup(<SecondarySidebarLayout
    sidebar={<nav>Secondary navigation</nav>}
  ><main>Workspace content</main></SecondarySidebarLayout>);

  expect(html).toContain("w-[208px]");
  expect(html).not.toContain("w-60");
});

test("settings, placement, and chat explicitly opt into secondary workspace layouts", () => {
  expect(routeForPath("/app/settings").layout).toBe("secondary");
  expect(routeForPath("/app/college", "college").layout).toBe("secondary");
  expect(routeForPath("/app/ai").layout).toBe("secondary-fixed");
  expect(routeForPath("/app/clients").layout).toBeUndefined();
});

test("uses the shared mobile trigger to open secondary navigation", () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => root.render(<SecondarySidebarLayout
    sidebar={<div>Desktop navigation</div>}
    mobileSidebar={({ closeSidebar }) => <button type="button" onClick={closeSidebar}>Mobile navigation</button>}
    mobileTitle="Sections"
  >{({ openSidebar }) => <SecondarySidebarTrigger compact icon={List} label="sections" onClick={openSidebar} />}</SecondarySidebarLayout>));

  act(() => container.querySelector("button").click());
  expect(document.body.textContent).toContain("Mobile navigation");

  const close = [...document.body.querySelectorAll("button")].find((button) => button.textContent === "Mobile navigation");
  act(() => close.click());
  act(() => root.unmount());
  container.remove();
  delete global.IS_REACT_ACT_ENVIRONMENT;
});
