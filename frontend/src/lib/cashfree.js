let checkoutLoader;

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
