import React, { act } from "react";
import { createRoot } from "react-dom/client";

import { Button } from "./button";

test("promise-returning actions are single-flight and expose a stable busy state", async () => {
  let resolve;
  const action = vi.fn(() => new Promise((done) => { resolve = done; }));
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  global.IS_REACT_ACT_ENVIRONMENT = true;

  await act(async () => { root.render(<Button onClick={action} loadingText="Saving...">Save</Button>); });
  const button = container.querySelector("button");
  await act(async () => { button.click(); button.click(); });

  expect(action).toHaveBeenCalledTimes(1);
  expect(button.disabled).toBe(true);
  expect(button.getAttribute("aria-busy")).toBe("true");
  expect(button.textContent).toContain("Saving...");

  await act(async () => { resolve(); await Promise.resolve(); });
  expect(button.disabled).toBe(false);
  expect(button.getAttribute("aria-busy")).toBeNull();

  await act(async () => { root.unmount(); });
  container.remove();
});
