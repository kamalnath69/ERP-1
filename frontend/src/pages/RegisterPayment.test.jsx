import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";

import RegisterPayment from "./RegisterPayment";

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  delete global.IS_REACT_ACT_ENVIRONMENT;
});

test("legacy payment URLs redirect to inline registration recovery", () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  act(() => {
    root.render(<MemoryRouter initialEntries={["/register/payment/checkout-1?returned=1"]}><Routes>
      <Route path="/register/payment/:checkoutId" element={<RegisterPayment />} />
      <Route path="/register" element={<PaymentReturnProbe />} />
    </Routes></MemoryRouter>);
  });

  expect(container.textContent).toBe("checkout-1");
  act(() => root.unmount());
  container.remove();
});

function PaymentReturnProbe() {
  const [params] = useSearchParams();
  return params.get("payment_return") || "missing";
}
