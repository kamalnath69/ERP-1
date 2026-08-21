import { openCashfreeModal } from "./cashfree";

test("releases the host dialog before opening Cashfree and restores it afterward", async () => {
  const events = [];
  let completeCheckout;
  const checkout = vi.fn(() => new Promise((resolve) => {
    completeCheckout = resolve;
  }));
  const cashfree = { checkout };
  const existingAnimationFrame = window.requestAnimationFrame;
  window.requestAnimationFrame = (callback) => {
    callback(0);
    return 1;
  };

  try {
    const result = openCashfreeModal(cashfree, "payment-session-1", {
      beforeOpen: () => events.push("host-closed"),
      afterClose: () => events.push("host-restored"),
    });
    await Promise.resolve();

    expect(events).toEqual(["host-closed"]);
    expect(checkout).toHaveBeenCalledWith({
      paymentSessionId: "payment-session-1",
      redirectTarget: "_modal",
    });

    completeCheckout({ paymentDetails: { paymentMessage: "Payment finished" } });
    await expect(result).resolves.toEqual({
      paymentDetails: { paymentMessage: "Payment finished" },
    });
    expect(events).toEqual(["host-closed", "host-restored"]);
  } finally {
    if (existingAnimationFrame) window.requestAnimationFrame = existingAnimationFrame;
    else delete window.requestAnimationFrame;
  }
});

test("restores the host dialog when the Cashfree SDK rejects", async () => {
  const afterClose = vi.fn();
  const existingAnimationFrame = window.requestAnimationFrame;
  window.requestAnimationFrame = (callback) => {
    callback(0);
    return 1;
  };

  try {
    await expect(openCashfreeModal(
      { checkout: vi.fn().mockRejectedValue(new Error("provider unavailable")) },
      "payment-session-2",
      { afterClose },
    )).rejects.toThrow("provider unavailable");
    expect(afterClose).toHaveBeenCalledOnce();
  } finally {
    if (existingAnimationFrame) window.requestAnimationFrame = existingAnimationFrame;
    else delete window.requestAnimationFrame;
  }
});
