import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { FormProvider, useForm } from "react-hook-form";

import { Button } from "./button";

function ValidatedForm() {
  const form = useForm({ mode: "onChange", defaultValues: { name: "" } });
  return <FormProvider {...form}><form><input {...form.register("name", { required: true })} /><button type="button" data-fill onClick={() => form.setValue("name", "Ready", { shouldValidate: true })}>Fill</button><Button type="submit">Save</Button></form></FormProvider>;
}

function FailedLogin({ onRetry }) {
  const form = useForm({ mode: "onChange", defaultValues: { email: "owner@example.com" } });
  React.useEffect(() => {
    form.setError("root.server", { type: "server", message: "Invalid credentials" });
  }, [form.setError]);
  return <FormProvider {...form}><form onSubmit={(event) => event.preventDefault()}><input {...form.register("email", { required: true })} /><Button type="submit" onClick={onRetry}>Sign in</Button></form></FormProvider>;
}

test("promise-returning actions are single-flight and expose a stable busy state", async () => {
  let resolve;
  const action = vi.fn(() => new Promise((done) => { resolve = done; }));
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  global.IS_REACT_ACT_ENVIRONMENT = true;

  await act(async () => { root.render(<React.StrictMode><Button onClick={action} loadingText="Saving...">Save</Button></React.StrictMode>); });
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

test("resolver-backed submit buttons stay disabled until the form is valid", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  global.IS_REACT_ACT_ENVIRONMENT = true;

  await act(async () => { root.render(<ValidatedForm />); await Promise.resolve(); });
  const button = container.querySelector('button[type="submit"]');
  expect(button.disabled).toBe(true);

  await act(async () => {
    container.querySelector("[data-fill]").click();
    await Promise.resolve();
  });
  expect(button.disabled).toBe(false);

  await act(async () => { root.unmount(); });
  container.remove();
});

test("a server error releases the submit button for an immediate retry", async () => {
  const retry = vi.fn();
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  global.IS_REACT_ACT_ENVIRONMENT = true;

  await act(async () => { root.render(<FailedLogin onRetry={retry} />); await Promise.resolve(); });
  const button = container.querySelector('button[type="submit"]');
  expect(button.disabled).toBe(false);

  await act(async () => button.click());
  expect(retry).toHaveBeenCalledOnce();

  await act(async () => { root.unmount(); });
  container.remove();
});
