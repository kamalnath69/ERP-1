let checkoutLoader;

export function loadCashfreeCheckout() {
  if (window.Cashfree) return Promise.resolve(window.Cashfree);
  if (checkoutLoader) return checkoutLoader;
  checkoutLoader = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://sdk.cashfree.com/js/v3/cashfree.js";
    script.async = true;
    script.onload = () => resolve(window.Cashfree);
    script.onerror = () => reject(new Error("The secure payment window could not be loaded"));
    document.body.appendChild(script);
  });
  return checkoutLoader;
}
