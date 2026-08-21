let checkoutLoader;

function waitForHostDialogRelease() {
  return new Promise((resolve) => {
    const schedule = typeof window.requestAnimationFrame === "function"
      ? window.requestAnimationFrame.bind(window)
      : (callback) => window.setTimeout(callback, 0);
    // Radix releases its body-level pointer lock in an effect after the dialog closes.
    schedule(() => schedule(() => resolve()));
  });
}

export function loadCashfreeCheckout() {
  if (typeof window.Cashfree === "function") return Promise.resolve(window.Cashfree);
  if (checkoutLoader) return checkoutLoader;
  checkoutLoader = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const timeout = window.setTimeout(() => {
      checkoutLoader = undefined;
      script.remove();
      reject(new Error("Cashfree checkout took too long to load"));
    }, 12000);
    script.src = "https://sdk.cashfree.com/js/v3/cashfree.js";
    script.async = true;
    script.onload = () => {
      window.clearTimeout(timeout);
      if (typeof window.Cashfree === "function") resolve(window.Cashfree);
      else {
        checkoutLoader = undefined;
        reject(new Error("Cashfree checkout did not initialize"));
      }
    };
    script.onerror = () => {
      window.clearTimeout(timeout);
      checkoutLoader = undefined;
      reject(new Error("The secure payment window could not be loaded"));
    };
    document.body.appendChild(script);
  });
  return checkoutLoader;
}

export async function openCashfreeModal(cashfree, paymentSessionId, lifecycle = {}) {
  lifecycle.beforeOpen?.();
  await waitForHostDialogRelease();
  try {
    return await cashfree.checkout({
      paymentSessionId,
      redirectTarget: "_modal",
    });
  } finally {
    lifecycle.afterClose?.();
  }
}
