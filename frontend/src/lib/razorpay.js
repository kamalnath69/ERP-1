let checkoutLoader;

export function loadRazorpayCheckout() {
  if (window.Razorpay) return Promise.resolve();
  if (checkoutLoader) return checkoutLoader;
  checkoutLoader = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const timeout = window.setTimeout(() => {
      checkoutLoader = undefined;
      script.remove();
      reject(new Error("Razorpay checkout took too long to load"));
    }, 12000);
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => {
      window.clearTimeout(timeout);
      if (window.Razorpay) resolve();
      else {
        checkoutLoader = undefined;
        reject(new Error("Razorpay checkout did not initialize"));
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
